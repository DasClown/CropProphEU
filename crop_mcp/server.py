#!/usr/bin/env python3
"""
crop-mcp: EU Crop Intelligence for AI Agents
==============================================
MCP Server exposing agronomic intelligence tools.

Usage:
  python3 server.py              # Start MCP stdio server
  python3 server.py --test       # Self-test
  python3 server.py --list-tools # Show available tools
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

from .core.regions import REGIONS, CROPS, get_region, get_crop, list_regions, list_crops
from .sources.weather import (
    get_forecast,
    get_historical,
    analyze_growing_season,
    calc_gdd,
    drought_index,
)
from .sources.power import season_solar_and_soil, season_gdd_precip_power

# Market prices (€/t) for revenue calculation
try:
    from .market_prices import get_market_price, calculate_revenue, REFERENCE_PRICES
    _HAS_MARKET_PRICES = True
except Exception:
    _HAS_MARKET_PRICES = False

# Feature Cache (sub-second historische Vergleiche)
try:
    from .feature_cache import get as _cache_get
    _HAS_CACHE = True
except Exception:
    _HAS_CACHE = False

# V3: Analog-year yield simulator
from .simulate_yield import simulate_yield, YIELDS as _YIELDS

# European yield model (15 countries)
try:
    from .europe_model_api import predict_europe_yield, get_available_countries
    _HAS_EUROPE_MODEL = True
except Exception:
    _HAS_EUROPE_MODEL = False

# NDVI (optional — Planetary Computer API may be unavailable)
try:
    from .sources.ndvi import get_ndvi as _get_ndvi
    _HAS_NDVI = True
except Exception:
    _HAS_NDVI = False

# NDVI Correction (adjusts model predictions with satellite data)
try:
    from .ndvi_correction import compute_ndvi_correction as _ndvi_correct
    _HAS_NDVI_CORRECTION = True
except Exception:
    _HAS_NDVI_CORRECTION = False

_start_time = time.time()

# Server-level language setting (from config or CLI)
_DEFAULT_LANGUAGE = os.environ.get("CROP_LANGUAGE", "de")

# ─────────────────────────────────────────────────────────────
# Language utilities
# ─────────────────────────────────────────────────────────────

def _detect_language(kwargs: dict) -> str:
    """Detect language from tool arguments or fall back to server default.
    Accepts 'language' param in kwargs, otherwise uses _DEFAULT_LANGUAGE.
    If the crop name is in English and no language is specified, stays with default.
    """
    lang = kwargs.get("language", _DEFAULT_LANGUAGE)
    if lang not in ("de", "en"):
        lang = _DEFAULT_LANGUAGE
    return lang

# ─────────────────────────────────────────────────────────────
# NDVI Correction for Predictions
# ─────────────────────────────────────────────────────────────

def _apply_ndvi_correction(result: dict, region_code: str, lat: float, lon: float, crop: str) -> dict:
    """Apply NDVI correction to a prediction result (mutates in-place)."""
    if not _HAS_NDVI_CORRECTION or not _HAS_NDVI:
        result["ndvi_correction"] = {"applied": False, "reason": "ndvi_module_unavailable"}
        return result
    
    model_yield = result.get("predicted_yield_t_ha", result.get("yield_t_ha"))
    if model_yield is None:
        return result
    
    # Import here to avoid circular issues
    from .sources import ndvi as _ndvi_mod
    
    correction = _ndvi_correct(
        model_prediction=model_yield,
        region_code=region_code,
        lat=lat,
        lon=lon,
        crop=crop,
        ndvi_module=_ndvi_mod,
    )
    
    if correction.get("note") == "ok":
        result["predicted_yield_t_ha"] = correction["corrected_yield_t_ha"]
        result["model_yield_before_ndvi"] = correction["model_yield_t_ha"]
        result["ndvi_correction"] = {
            "applied": True,
            "factor": correction["correction_factor"],
            "ndvi_current": correction["ndvi"]["current"],
            "ndvi_expected": correction["ndvi"]["expected"],
            "ndvi_anomaly": correction["ndvi"]["anomaly"],
            "sensitivity": correction["sensitivity"],
            "satellite_date": correction["ndvi"]["date"],
        }
        # Also update risk range proportionally
        for key in ["p10", "p50", "p90", "min", "max"]:
            if key in result:
                result[key] = round(result[key] * correction["correction_factor"], 3)
        # Regenerate risk range
        if "p10" in result and "p90" in result:
            result["risk_range_t_ha"] = round(result["p90"] - result["p10"], 2)
    else:
        result["ndvi_correction"] = {
            "applied": False,
            "reason": correction.get("note", "unknown"),
        }
    
    return result

def _describe_gdd_en(gdd: float, crop: str) -> str:
    norms = {"wheat": (1800, 2800), "corn": (2200, 3200), "barley": (1500, 2500)}
    lo, hi = norms.get(crop, (1500, 2800))
    if gdd < lo * 0.7:
        return f"cool ({gdd:.0f}°C GDD)"
    if gdd < lo:
        return f"slightly cool ({gdd:.0f}°C GDD)"
    if gdd > hi * 1.2:
        return f"very warm ({gdd:.0f}°C GDD)"
    if gdd > hi:
        return f"warm ({gdd:.0f}°C GDD)"
    return f"normal ({gdd:.0f}°C GDD)"

def _describe_precip_en(precip_mm: float, crop: str) -> str:
    norms = {"wheat": (300, 550), "corn": (350, 600), "barley": (250, 450)}
    lo, hi = norms.get(crop, (300, 550))
    if precip_mm < lo * 0.6:
        return f"too dry ({precip_mm:.0f} mm)"
    if precip_mm < lo:
        return f"slightly dry ({precip_mm:.0f} mm)"
    if precip_mm > hi * 1.3:
        return f"very wet ({precip_mm:.0f} mm)"
    if precip_mm > hi:
        return f"wet ({precip_mm:.0f} mm)"
    return lang

def _describe_gdd_en(gdd: float, crop: str) -> str:
    norms = {"wheat": (1800, 2800), "corn": (2200, 3200), "barley": (1500, 2500)}
    lo, hi = norms.get(crop, (1500, 2800))
    if gdd < lo * 0.7:
        return f"cool ({gdd:.0f}°C GDD)"
    if gdd < lo:
        return f"slightly cool ({gdd:.0f}°C GDD)"
    if gdd > hi * 1.2:
        return f"very warm ({gdd:.0f}°C GDD)"
    if gdd > hi:
        return f"warm ({gdd:.0f}°C GDD)"
    return f"normal ({gdd:.0f}°C GDD)"

def _describe_precip_en(precip_mm: float, crop: str) -> str:
    norms = {"wheat": (300, 550), "corn": (350, 600), "barley": (250, 450)}
    lo, hi = norms.get(crop, (300, 550))
    if precip_mm < lo * 0.6:
        return f"too dry ({precip_mm:.0f} mm)"
    if precip_mm < lo:
        return f"slightly dry ({precip_mm:.0f} mm)"
    if precip_mm > hi * 1.3:
        return f"very wet ({precip_mm:.0f} mm)"
    if precip_mm > hi:
        return f"wet ({precip_mm:.0f} mm)"
    return f"adequate ({precip_mm:.0f} mm)"


# ─────────────────────────────────────────────────────────────
# V4.7: Frost Outlook Analysis
# ─────────────────────────────────────────────────────────────

def _analyze_frost_outlook(forecast_days: list, frost_sensitive: bool,
                           ref_date: date) -> dict:
    """
    Analyze the 16-day forecast for frost events (t_min < 0°C).
    Returns structured frost outlook for crop_forecast output.
    """
    import math
    frost_days = []
    for day in forecast_days:
        t_min = day.get("t_min")
        day_date_str = day.get("date", "")
        if t_min is not None and t_min < 0 and day_date_str:
            frost_days.append({
                "date": day_date_str,
                "t_min_c": round(t_min, 1),
            })

    next_frost = frost_days[0] if frost_days else None
    frost_count_5d = sum(1 for d in frost_days
                         if d["date"] <= (ref_date + timedelta(days=5)).isoformat())

    # Risk assessment
    risk = "none"
    if frost_sensitive and frost_days:
        if frost_count_5d >= 2:
            risk = "high"
        elif frost_count_5d >= 1:
            risk = "moderate"
        elif len(frost_days) >= 3:
            risk = "low"
    elif not frost_sensitive and frost_days:
        risk = "low"  # Frost-hardy crops (winter wheat, barley) can tolerate some frost

    # Critical period check (flowering/early growth)
    critical = False
    if frost_sensitive and next_frost:
        # Corn emergence is most critical (May-June)
        # For now, flag if frost is in the forecast at all for sensitive crops
        critical = frost_sensitive and frost_count_5d > 0

    return {
        "forecast_frost_days": len(frost_days),
        "frost_days_detail": frost_days[:5],  # Show next 5
        "next_frost_date": next_frost["date"] if next_frost else None,
        "next_frost_temp_c": next_frost["t_min_c"] if next_frost else None,
        "frost_in_5_days": frost_count_5d,
        "risk_level": risk,
        "critical_period_alert": critical,
    }

# ─────────────────────────────────────────────────────────────
# Pydantic Models (Agent-facing schemas)
# ─────────────────────────────────────────────────────────────

class WeatherOutlookInput(BaseModel):
    """Get weather forecast for a specific EU region."""
    region: str = Field(
        ...,
        min_length=4,
        max_length=5,
        description="NUTS2 region code (e.g. 'FRF2' for Picardie, 'DEE0' for Sachsen-Anhalt). "
                    "Use list_regions to discover available codes.",
    )
    days: int = Field(
        default=7,
        ge=1,
        le=16,
        description="Number of forecast days (1-16)",
    )


class CropForecastInput(BaseModel):
    """Generate a crop-specific forecast for a region combining weather + history."""
    crop: str = Field(
        ...,
        pattern=r"^(wheat|corn|rapeseed|sunflower|barley)$",
        description="Crop type. Use list_crops for details on each.",
    )
    region: str = Field(
        ...,
        min_length=4,
        max_length=5,
        description="NUTS2 region code",
    )
    as_of_date: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Optional reference date (YYYY-MM-DD) for rolling forecasts. "
                    "Default: today. Use to simulate what you'd have known on a past date.",
    )
    reference_years: int = Field(
        default=30,
        ge=5,
        le=40,
        description="Number of historical years for anomaly comparison (5-40, default 30)",
    )


class SeasonComparisonInput(BaseModel):
    """Compare current season weather to historical averages for a region."""
    crop: str = Field(
        ...,
        pattern=r"^(wheat|corn|rapeseed|sunflower|barley)$",
        description="Crop type to analyze",
    )
    region: str = Field(
        ...,
        min_length=4,
        max_length=5,
        description="NUTS2 region code",
    )
    reference_years: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Number of historical years to compare against (1-10)",
    )


class ListRegionsInput(BaseModel):
    """List available EU agricultural regions, optionally filtered by country."""
    country: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        pattern=r"^[A-Z]{2}$",
        description="ISO country code filter (e.g. 'DE', 'FR', 'PL'). Omit for all regions.",
    )


class ListCropsInput(BaseModel):
    """List all supported crop types with agronomic parameters."""
    pass


# ─────────────────────────────────────────────────────────────
# Tool Handlers
# ─────────────────────────────────────────────────────────────

def _get_season_dates(crop_name: str, year: int) -> tuple[str, str]:
    """
    Determine the growing season date range for a crop.
    Winter crops start in previous year.
    """
    crop = get_crop(crop_name)
    if crop.planting_month > crop.harvest_month:
        # Winter crop: starts in YYYY-10, ends in YYYY+1-07
        start = date(year - 1, crop.planting_month, 1)
        end = date(year, crop.harvest_month, 28)
    else:
        # Summer crop: starts and ends in same year
        start = date(year, crop.planting_month, 1)
        end = date(year, crop.harvest_month, 28)
    return start.isoformat(), end.isoformat()


def _handle_weather_outlook(**kwargs: Any) -> list[types.TextContent]:
    """16-day weather forecast for a region."""
    validated = WeatherOutlookInput(**kwargs)
    region = get_region(validated.region)
    forecast = get_forecast(region.latitude, region.longitude, region.altitude)

    # Trim to requested days
    forecast["forecast"] = forecast["forecast"][:validated.days]
    forecast["days_forecast"] = len(forecast["forecast"])
    forecast["region"] = {"code": region.code, "name": region.name, "country": region.country}

    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "data": forecast,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))]


def _handle_crop_forecast(**kwargs: Any) -> list[types.TextContent]:
    """
    V2: Synthesize a crop forecast from weather + POWER satellite + historical data.
    Combines: weather, GDD, precipitation, solar radiation, soil moisture, 30yr normals.
    """
    validated = CropForecastInput(**kwargs)
    crop = get_crop(validated.crop)
    region = get_region(validated.region)

    ref_date = date.fromisoformat(validated.as_of_date) if validated.as_of_date else date.today()
    current_year = ref_date.year

    # Determine the current growing season
    season_start, season_end = _get_season_dates(validated.crop, current_year)

    # 1. Analyze current season weather (up to ref_date)
    # Try Open-Meteo first (daily precision), fall back to NASA POWER (monthly, no rate limits)
    season = {}
    season_data_source = "power"
    season_retrieved = False
    try:
        season = analyze_growing_season(
            region.latitude, region.longitude,
            crop.gdd_base,
            season_start, min(season_end, ref_date.isoformat()),
        )
        season_retrieved = True
        season_data_source = "open-meteo"
    except Exception:
        pass

    if not season_retrieved or not season.get("gdd", {}).get("accumulated"):
        # POWER fallback: monthly averages (no rate limits)
        if date.fromisoformat(season_start) <= ref_date:
            # Determine cutoff date for partial season
            cut_month = ref_date.month
            cut_day = ref_date.day
            power_season = season_gdd_precip_power(
                region.latitude, region.longitude,
                current_year, crop.planting_month, crop.harvest_month,
                gdd_base=crop.gdd_base,
                cut_off_month=cut_month, cut_off_day=cut_day,
            )
            season = {
                "gdd": {"accumulated": power_season["gdd_accumulated"], "forecast_16d": 0.0},
                "precipitation_mm": {"accumulated": power_season["precip_mm_accumulated"], "forecast_16d": 0.0},
                "extremes": {"hot_days_gt_30c": None, "frost_days_lt_0c": None, "rainy_days_gt_5mm": None},
                "elapsed_days": power_season["months_count"] * 30,
            }
            season_data_source = "power"
        else:
            season = {
                "gdd": {"accumulated": 0.0, "forecast_16d": 0.0},
                "precipitation_mm": {"accumulated": 0.0, "forecast_16d": 0.0},
                "extremes": {"hot_days_gt_30c": 0, "frost_days_lt_0c": 0, "rainy_days_gt_5mm": 0},
                "elapsed_days": 0,
            }

    # 2. Get 16-day forecast
    forecast = {}
    try:
        forecast = get_forecast(region.latitude, region.longitude, region.altitude)
    except Exception:
        forecast = {"forecast": [], "current": {}, "days_forecast": 0}

    # 3. Historical comparison (30-year by default, same relative progress)
    current_season_start = date.fromisoformat(season_start)
    days_elapsed = (ref_date - current_season_start).days
    hist_years = min(validated.reference_years, current_year - 2000)  # don't go before 2000
    hist_start = current_year - hist_years

    historical_gdd = []
    historical_precip = []
    for y in range(hist_start, current_year):
        hs, he = _get_season_dates(validated.crop, y)
        hs_obj = date.fromisoformat(hs)
        he_obj = date.fromisoformat(he)
        period_end = hs_obj + timedelta(days=days_elapsed)
        actual_end = min(period_end, he_obj).isoformat()
        if actual_end <= hs:
            continue
        try:
            h = get_historical(region.latitude, region.longitude, hs, actual_end)
            gdd_sum = 0.0
            precip_sum = 0.0
            for day in h["days"]:
                if day["t_max"] is not None and day["t_min"] is not None:
                    gdd_sum += calc_gdd(day["t_max"], day["t_min"], crop.gdd_base)
                if day["precipitation_mm"] is not None:
                    precip_sum += day["precipitation_mm"]
            historical_gdd.append({"year": y, "gdd": round(gdd_sum, 1), "precipitation_mm": round(precip_sum, 1)})
        except Exception:
            continue

    avg_gdd = sum(h["gdd"] for h in historical_gdd) / len(historical_gdd) if historical_gdd else 0
    avg_precip = sum(h["precipitation_mm"] for h in historical_gdd) / len(historical_gdd) if historical_gdd else 0
    current_gdd = season["gdd"]["accumulated"]

    gdd_vs_avg = round(((current_gdd - avg_gdd) / avg_gdd) * 100, 1) if avg_gdd > 0 else 0
    precip_vs_avg = round(((season["precipitation_mm"]["accumulated"] - avg_precip) / avg_precip) * 100, 1) if avg_precip > 0 else 0

    # 4. POWER data: solar radiation + soil moisture
    power = {}
    try:
        power = season_solar_and_soil(
            region.latitude, region.longitude, current_year,
            crop.planting_month, crop.harvest_month,
        )
    except Exception:
        power = {"solar_radiation_kwh_m2_day": {}, "soil_moisture_root_zone": {}}

    # 5. Drought assessment (uses both weather-based + soil moisture)
    tmax_avg = 0.0
    tmax_count = 0
    try:
        h_data = get_historical(region.latitude, region.longitude, season_start, ref_date.isoformat())
        for day in h_data.get("days", []):
            if day["t_max"] is not None:
                tmax_avg += day["t_max"]
                tmax_count += 1
    except Exception:
        pass
    tmax_avg = tmax_avg / tmax_count if tmax_count > 0 else 15.0

    drought_wx = drought_index(season["precipitation_mm"]["accumulated"], tmax_avg)
    soil_m = power.get("soil_moisture_root_zone", {}).get("current", 0.5)
    drought_soil = max(0.0, min(1.0, 1.0 - (soil_m - 0.2) / 0.6)) if soil_m > 0 else 0.5
    drought_combined = max(drought_wx * 0.4 + drought_soil * 0.6, 0.0)

    # 5b. NDVI (optional — gracefully degrades if unavailable)
    ndvi_data = {}
    if _HAS_NDVI:
        try:
            ndvi_result = _get_ndvi(region.latitude, region.longitude, max_lookback_days=60)
            if ndvi_result.get("status") == "ok" and ndvi_result.get("latest"):
                ndvi_data = {
                    "ndvi": ndvi_result["latest"]["ndvi"],
                    "date": ndvi_result["latest"]["date"],
                    "cloud_cover_pct": ndvi_result["latest"]["cloud_cover_pct"],
                    "interpretation": ndvi_result.get("interpretation"),
                }
        except Exception:
            pass

    # 6. GDD progress
    gdd_progress = min(100.0, round((current_gdd / crop.gdd_optimum) * 100, 1))

    # 7. Yield outlook signals
    yield_signals = []
    
    # Weather-based
    if drought_wx > 0.6:
        yield_signals.append("drought_stress")
    if drought_soil > 0.6 and soil_m < 0.35:
        yield_signals.append("soil_moisture_deficit")
    if gdd_vs_avg < -10:
        yield_signals.append("cool_season")
    elif gdd_vs_avg > 15:
        yield_signals.append("warm_season")
    if season.get("extremes", {}).get("frost_days_lt_0c", 0) > 3 and crop.frost_sensitive:
        yield_signals.append("frost_damage_risk")
    if season.get("extremes", {}).get("hot_days_gt_30c", 0) > 5:
        yield_signals.append("heat_stress")
    if season["precipitation_mm"]["accumulated"] < avg_precip * 0.6 and avg_precip > 0:
        yield_signals.append("precipitation_deficit")
    elif season["precipitation_mm"]["accumulated"] > avg_precip * 1.4:
        yield_signals.append("excess_moisture")
    
    # POWER-based
    solar_anom = power.get("solar_radiation_kwh_m2_day", {}).get("anomaly_vs_same_months_pct", 0)
    if solar_anom and solar_anom < -15:
        yield_signals.append("low_solar_radiation")
    elif solar_anom and solar_anom > 20:
        yield_signals.append("high_solar_radiation")

    # V4.7: Frost warning from forecast
    frost_outlook = _analyze_frost_outlook(forecast.get("forecast", []),
                                            crop.frost_sensitive, ref_date)
    if frost_outlook["critical_period_alert"]:
        yield_signals.append("frost_warning_next_5_days")
    elif frost_outlook["risk_level"] == "high":
        yield_signals.append("frost_warning")

    # 8. Confidence
    season_days_total = (date.fromisoformat(season_end) - date.fromisoformat(season_start)).days
    season_days_elapsed = (ref_date - date.fromisoformat(season_start)).days
    season_progress = min(100.0, round((season_days_elapsed / max(season_days_total, 1)) * 100, 1))
    # POWER data is monthly averages (less precise); adjust confidence
    power_only = season_data_source == "power" and season.get("extremes", {}).get("hot_days_gt_30c") is None
    confidence = "low" if season_progress < 25 else "medium" if season_progress < 60 else "high"
    if power_only and confidence == "high":
        confidence = "medium"  # POWER monthly data is less precise than daily
    data_sources_list = ["nasa-power"]  # POWER always works
    if season_data_source == "open-meteo":
        data_sources_list.append("open-meteo")
    if ndvi_data:
        data_sources_list.append("sentinel-2-ndvi")

    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "data": {
            "crop": {"name": crop.name, "name_de": crop.name_de},
            "region": {"code": region.code, "name": region.name, "country": region.country},
            "reference_date": ref_date.isoformat(),
            "season": {
                "start": season_start,
                "end": season_end,
                "progress_pct": season_progress,
            },
            "gdd": {
                "base_temp": crop.gdd_base,
                "optimum": crop.gdd_optimum,
                "accumulated": current_gdd,
                "progress_pct": gdd_progress,
                f"vs_{hist_years}yr_avg_pct": gdd_vs_avg,
                "forecast_16d": season["gdd"]["forecast_16d"],
            },
            "precipitation_mm": {
                "accumulated": season["precipitation_mm"]["accumulated"],
                f"vs_{hist_years}yr_avg_pct": precip_vs_avg,
                "forecast_16d": season["precipitation_mm"]["forecast_16d"],
            },
            "solar_radiation": power.get("solar_radiation_kwh_m2_day", {}),
            "soil_moisture": power.get("soil_moisture_root_zone", {}),
            "ndvi": ndvi_data,
            "drought_index": {
                "weather_based": round(drought_wx, 2),
                "soil_moisture_based": round(drought_soil, 2),
                "combined": round(drought_combined, 2),
            },
            "extremes": season.get("extremes", {
                "hot_days_gt_30c": 0, "frost_days_lt_0c": 0, "rainy_days_gt_5mm": 0
            }),
            # V4.7: Frost analysis from 16-day forecast (reuses computed frost_outlook)
            "frost_outlook": frost_outlook,
            "historical": historical_gdd[-5:] if len(historical_gdd) > 5 else historical_gdd,
            "signals": yield_signals,
            "confidence": confidence,
            "data_sources": data_sources_list,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))]


def _handle_season_comparison(**kwargs: Any) -> list[types.TextContent]:
    """Compare current season to historical years. Uses cache for sub-second response on wheat."""
    validated = SeasonComparisonInput(**kwargs)
    crop = get_crop(validated.crop)
    region = get_region(validated.region)

    today = date.today()
    current_year = today.year

    years_data = []
    # Cache kann nur für Weizen genutzt werden (fest codierte Saisonparameter)
    use_cache = _HAS_CACHE and validated.crop == "wheat"

    for y in range(current_year - validated.reference_years, current_year + 1):
        season_start, season_end = _get_season_dates(validated.crop, y)
        end_date = min(date.fromisoformat(season_end), today).isoformat()

        try:
            if use_cache and y < current_year:
                # Sub-second: aus dem Cache
                cached = _cache_get(region.code, y, region.latitude, region.longitude,
                                    crop.planting_month, crop.harvest_month, crop.gdd_base)
                if cached:
                    # Aus Cache: nur GDD + Precip (keine Frost-/Hitzetage)
                    years_data.append({
                        "year": y,
                        "gdd": cached["gdd"],
                        "precipitation_mm": cached["precip_mm"],
                        "solar_kwh": cached["solar_kwh"],
                        "soil_moisture": cached["soil_moisture"],
                        "frost_days": None,  # nicht gecached
                        "heat_days": None,   # nicht gecached
                        "days_recorded": 365,
                        "source": "cache",
                    })
                    continue
            
            # Live: Open-Meteo (für aktuelles Jahr + andere Kulturen)
            h = get_historical(region.latitude, region.longitude, season_start, end_date)
            gdd_sum = 0.0
            precip_sum = 0.0
            frost = 0
            heat = 0
            for day in h["days"]:
                if day["t_max"] is not None and day["t_min"] is not None:
                    gdd_sum += calc_gdd(day["t_max"], day["t_min"], crop.gdd_base)
                if day["precipitation_mm"] is not None:
                    precip_sum += day["precipitation_mm"]
                if day["t_min"] is not None and day["t_min"] < 0:
                    frost += 1
                if day["t_max"] is not None and day["t_max"] > 30:
                    heat += 1

            years_data.append({
                "year": y,
                "gdd": round(gdd_sum, 1),
                "precipitation_mm": round(precip_sum, 1),
                "frost_days": frost,
                "heat_days": heat,
                "days_recorded": len(h["days"]),
                "source": "open-meteo",
            })
        except Exception:
            continue

    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "data": {
            "crop": {"name": crop.name, "name_de": crop.name_de},
            "region": {"code": region.code, "name": region.name, "country": region.country},
            "comparison": years_data,
            "cache_hit_ratio": f"{sum(1 for y in years_data if y.get('source') == 'cache')}/{len(years_data)}",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))]


class RegionHealthInput(BaseModel):
    """Get comprehensive health overview for a region across all supported crops."""
    region: str = Field(
        ...,
        min_length=4,
        max_length=5,
        description="NUTS2 region code",
    )


def _handle_region_health(**kwargs: Any) -> list[types.TextContent]:
    """Comprehensive health overview: all crops, weather, soil, solar — in one call."""
    validated = RegionHealthInput(**kwargs)
    region = get_region(validated.region)
    today = date.today()

    crops_health = []
    for crop_name in ["wheat", "corn", "rapeseed", "sunflower", "barley"]:
        if crop_name not in region.major_crops:
            continue
        try:
            result = _handle_crop_forecast(crop=crop_name, region=region.code)
            data = json.loads(result[0].text)
            crops_health.append(data["data"])
        except Exception:
            continue

    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "data": {
            "region": {"code": region.code, "name": region.name, "country": region.country},
            "date": today.isoformat(),
            "crops": crops_health,
            "crops_count": len(crops_health),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))]


class YieldForecastInput(BaseModel):
    """Predict crop yield using analog-year matching."""
    crop: str = Field(
        ...,
        pattern=r"^(wheat|corn|rapeseed|sunflower|barley)$",
        description="Crop type. Use list_crops for available options.",
    )
    region: str = Field(
        ...,
        min_length=4,
        max_length=5,
        description="NUTS2 region code (e.g. 'DEE0' for Sachsen-Anhalt)",
    )
    as_of_date: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Optional reference date (YYYY-MM-DD). Default: today. "
                    "Earlier dates = lower confidence but useful for backtesting.",
    )


def _handle_yield_forecast(**kwargs: Any) -> list[types.TextContent]:
    """Yield forecast using analog-year matching against 25-year climate library."""
    validated = YieldForecastInput(**kwargs)
    
    ref_date = date.today()
    if validated.as_of_date:
        ref_date = date.fromisoformat(validated.as_of_date)
    
    result = simulate_yield(
        validated.region, validated.crop,
        ref_date.year, ref_date.month, ref_date.day,
    )
    
    if "error" in result:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "message": result["error"],
        }))]
    
    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "data": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))]


class EuropeanYieldForecastInput(BaseModel):
    """Predict crop yield for EU countries using Eurostat-verified data."""
    crop: str = Field(
        ...,
        pattern=r"^(wheat|corn|barley|rapeseed|sunflower)$",
        description="Crop type. Verified crops: wheat (C1100), corn (C1500), barley (C1300), rapeseed (C2000), sunflower (C2200).",
    )
    region: str = Field(
        ...,
        min_length=4,
        max_length=5,
        description="NUTS2 region code (e.g. 'DEE0' for Sachsen-Anhalt, 'FRF2' for Picardie)",
    )
    gdd: float | None = Field(
        default=None,
        description="Optional GDD override. If omitted, uses crop_forecast data.",
    )
    precipitation_mm: float | None = Field(
        default=None,
        description="Optional precipitation override.",
    )


# ── V4.4 Climate What-If ──

class ClimateScenarioInput(BaseModel):
    """Climate scenario analysis: What if temperature/precipitation changes?"""
    crop: str = Field(
        ...,
        pattern=r"^(wheat|corn|barley|rapeseed|sunflower)$",
        description="Crop to analyze (verified: wheat, corn, barley, rapeseed, sunflower)",
    )
    region: str = Field(
        ...,
        min_length=4,
        max_length=5,
        description="NUTS2 region code",
    )
    temp_shift_C: float = Field(
        default=1.0,
        description="Temperature shift in °C (positive = warming). Applied to GDD.",
    )
    precip_shift_pct: float = Field(
        default=0.0,
        description="Precipitation shift in percent (e.g., -20 = 20% drier, +20 = 20% wetter)",
    )
    scenario_name: str = Field(
        default=None,
        description="Optional label for this scenario (e.g. '+2°C dry')",
    )
    as_of_date: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Optional reference date. Default: today.",
    )


def _handle_europe_yield_forecast(**kwargs: Any) -> list[types.TextContent]:
    """European yield forecast using Random Forest (3 verified crops, real Eurostat data)."""
    if not _HAS_EUROPE_MODEL:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "message": "European model not loaded. Run build_europe_fast.py first.",
        }))]
    
    validated = EuropeanYieldForecastInput(**kwargs)
    
    try:
        region = get_region(validated.region)
        country = region.country
    except KeyError:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "message": f"Unknown region: {validated.region}",
        }))]
    
    # Get features from crop_forecast if not explicitly provided
    if validated.gdd is not None and validated.precipitation_mm is not None:
        gdd = validated.gdd
        precip = validated.precipitation_mm
        solar = 5.0  # default
        soil_m = 0.5  # default
    else:
        try:
            fc = _handle_crop_forecast(crop=validated.crop, region=validated.region)
            fc_data = json.loads(fc[0].text).get("data", {})
            gdd = fc_data.get("gdd", {}).get("accumulated", 1300)
            precip = fc_data.get("precipitation_mm", {}).get("accumulated", 350)
            solar = fc_data.get("solar_radiation", {}).get("current", 5.0) or 5.0
            soil_m = fc_data.get("soil_moisture", {}).get("current", 0.5) or 0.5
        except Exception:
            gdd, precip, solar, soil_m = 1300, 350, 5.0, 0.5
    
    available = get_available_countries()
    result = predict_europe_yield(validated.region, country, crop=validated.crop,
                                  gdd=gdd, precip_mm=precip, solar_kwh=solar,
                                  soil_moisture=soil_m)
    
    result["available_countries"] = available
    result["features_used"] = {
        "gdd": round(gdd, 1),
        "precipitation_mm": round(precip, 1),
        "solar_kwh": round(solar, 2),
        "soil_moisture": round(soil_m, 3),
    }
    
    # V5.1: NDVI satellite correction (adjusts prediction in-place)
    try:
        _apply_ndvi_correction(result, validated.region, region.latitude, region.longitude, validated.crop)
    except Exception:
        result["ndvi_correction"] = {"applied": False, "reason": "exception_during_correction"}
    
    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "data": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))]


# ── V4.4 Climate What-If ──

def _handle_climate_scenario(**kwargs: Any) -> list[types.TextContent]:
    """Climate scenario analysis: what if temperature/precipitation changed?"""
    if not _HAS_EUROPE_MODEL:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "message": "European model not loaded. Run train_europe.py first.",
        }))]

    validated = ClimateScenarioInput(**kwargs)

    try:
        region = get_region(validated.region)
        country = region.country
        crop = get_crop(validated.crop)
    except KeyError as e:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error", "message": str(e),
        }))]

    # Get current season features
    try:
        fc = _handle_crop_forecast(crop=validated.crop, region=validated.region)
        fc_data = json.loads(fc[0].text).get("data", {})
        gdd = fc_data.get("gdd", {}).get("accumulated", 1300)
        precip = fc_data.get("precipitation_mm", {}).get("accumulated", 350)
        solar = fc_data.get("solar_radiation", {}).get("current", 5.0) or 5.0
        soil_m = fc_data.get("soil_moisture", {}).get("current", 0.5) or 0.5
    except Exception:
        gdd, precip, solar, soil_m = 1300, 350, 5.0, 0.5

    # Apply climate shifts
    from datetime import date as _date
    _today = _date.today()
    _season_progress = min(1.0, (_today - _date(_today.year, 1, 1)).days / 365.0)

    # GDD shift: temp_shift_C * days_remaining * season_progress_factor
    # For winter wheat (Oct-Jul): ~270 days of growing season
    season_days = 270
    days_so_far = season_days * _season_progress
    days_remaining = season_days - days_so_far
    gdd_shift = validated.temp_shift_C * days_remaining  # Each degree C adds ~1 GDD per day
    gdd_scenario = gdd + max(0, gdd_shift)

    # Precip shift
    precip_scenario = precip * (1 + validated.precip_shift_pct / 100.0)

    # Base prediction (current)
    base = predict_europe_yield(
        validated.region, country, crop=validated.crop,
        gdd=gdd, precip_mm=precip, solar_kwh=solar, soil_moisture=soil_m
    )

    # Scenario prediction
    scenario = predict_europe_yield(
        validated.region, country, crop=validated.crop,
        gdd=gdd_scenario, precip_mm=precip_scenario, solar_kwh=solar, soil_moisture=soil_m
    )

    # Calculate impact
    impact = round(scenario["predicted_yield_t_ha"] - base["predicted_yield_t_ha"], 2)

    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "data": {
            "region": validated.region,
            "country": country,
            "crop": validated.crop,
            "scenario": {
                "name": validated.scenario_name or f"{validated.temp_shift_C:+.0f}°C, {validated.precip_shift_pct:+.0f}% precip",
                "temp_shift_C": validated.temp_shift_C,
                "precip_shift_pct": validated.precip_shift_pct,
            },
            "current": {
                "gdd": round(gdd, 1),
                "precipitation_mm": round(precip, 1),
                "predicted_yield_t_ha": base["predicted_yield_t_ha"],
                "p10": base["p10"],
                "p90": base["p90"],
            },
            "scenario_outcome": {
                "gdd": round(gdd_scenario, 1),
                "precipitation_mm": round(precip_scenario, 1),
                "predicted_yield_t_ha": scenario["predicted_yield_t_ha"],
                "p10": scenario["p10"],
                "p90": scenario["p90"],
            },
            "impact": {
                "yield_change_t_ha": impact,
                "yield_change_pct": round(impact / max(base["predicted_yield_t_ha"], 0.01) * 100, 1),
                "direction": "increase" if impact > 0 else "decrease" if impact < 0 else "no change",
            },
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))]



# ── V4.6 Market Value + Human-Readable Output ──

CROP_NAMES_DE = {"wheat": "Weizen", "corn": "Mais", "barley": "Gerste"}
CROP_NAMES = {"de": {"wheat": "Weizen", "corn": "Mais", "barley": "Gerste"},
              "en": {"wheat": "Wheat", "corn": "Corn", "barley": "Barley"}}

# Cache for training data (loaded once per crop)
_TRAINING_CACHE: dict = {}

def _load_training_cached(crop: str) -> list:
    if crop not in _TRAINING_CACHE:
        import os as _os
        base = "/home/j/crop-mcp/data"
        if crop == "wheat":
            path = _os.path.join(base, "europe_training_data.json")
        else:
            path = _os.path.join(base, f"europe_training_data_{crop}.json")
        if _os.path.exists(path):
            with open(path) as _f:
                _TRAINING_CACHE[crop] = json.load(_f)
        else:
            _TRAINING_CACHE[crop] = []
    return _TRAINING_CACHE[crop]

def _get_crop_comparison(crop: str, region: str) -> dict:
    data = _load_training_cached(crop)
    region_samples = [s for s in data if s.get("region") == region]
    if not region_samples:
        # Fallback: use country-level
        country = data[0].get("country","DE") if data else "DE"
        region_samples = [s for s in data if s.get("country") == country]
    if not region_samples:
        return {"status": "no_data"}
    
    sorted_samples = sorted(region_samples, key=lambda x: x.get("year",0))
    all_yields = [s["yield_t_ha"] for s in sorted_samples]
    
    # Previous year
    last = sorted_samples[-1]
    prev_year_yield = last["yield_t_ha"]
    prev_year = last["year"]
    
    # Last 5 years
    last5 = sorted_samples[-5:]
    last5_yields = [s["yield_t_ha"] for s in last5]
    mean5 = sum(last5_yields) / len(last5_yields)
    min5 = min(last5_yields)
    max5 = max(last5_yields)
    
    return {
        "previous_year": {"year": prev_year, "yield_t_ha": prev_year_yield},
        "last_5_years_mean": round(mean5, 2),
        "last_5_years_range": {"min": round(min5, 2), "max": round(max5, 2)},
        "last_5_years_detail": [{s["year"]: round(s["yield_t_ha"], 2)} for s in last5],
        "all_years_available": sorted_samples[0]["year"],
    }

def _describe_gdd(gdd: float, crop: str) -> str:
    norms = {"wheat": (1800, 2800), "corn": (2200, 3200), "barley": (1500, 2500)}
    lo, hi = norms.get(crop, (1500, 2800))
    if gdd < lo * 0.7:
        return f"kühl ({gdd:.0f}°C Wärmesumme)"
    if gdd < lo:
        return f"eher kühl ({gdd:.0f}°C Wärmesumme)"
    if gdd > hi * 1.2:
        return f"sehr warm ({gdd:.0f}°C Wärmesumme)"
    if gdd > hi:
        return f"warm ({gdd:.0f}°C Wärmesumme)"
    return f"normal ({gdd:.0f}°C Wärmesumme)"

def _describe_precip(precip_mm: float, crop: str) -> str:
    norms = {"wheat": (300, 550), "corn": (350, 600), "barley": (250, 450)}
    lo, hi = norms.get(crop, (300, 550))
    if precip_mm < lo * 0.6:
        return f"zu trocken ({precip_mm:.0f} mm)"
    if precip_mm < lo:
        return f"eher trocken ({precip_mm:.0f} mm)"
    if precip_mm > hi * 1.3:
        return f"sehr nass ({precip_mm:.0f} mm)"
    if precip_mm > hi:
        return f"nass ({precip_mm:.0f} mm)"
    return f"ausreichend ({precip_mm:.0f} mm)"

# Dispatch tables for language-aware text generation
_DESCRIBE_GDD = {"de": _describe_gdd, "en": _describe_gdd_en}
_DESCRIBE_PRECIP = {"de": _describe_precip, "en": _describe_precip_en}

def _build_human_summary(result: dict, language: str = "de") -> str:
    if not result or result.get("status") == "error":
        if language == "en":
            return "No data available."
        return "Keine Daten verfuegbar."
    d = result.get("data", result)
    crop_de = CROP_NAMES.get(language, CROP_NAMES["de"]).get(d.get("crop", ""), d.get("crop", ""))
    region = d.get("region", "?")
    ctry = d.get("country", "?")
    pred = d.get("predicted_yield_t_ha", 0)
    p10 = d.get("p10", 0)
    p90 = d.get("p90", 0)
    
    if language == "en":
        lines = [f"**{crop_de} – Region {region} ({ctry})**"]
        lines.append(f"Yield: {pred:.2f} t/ha (range {p10:.2f}–{p90:.2f})")
        f = d.get("features_used", {})
        if f:
            lines.append(f"Temperature: {_DESCRIBE_GDD.get(language, _describe_gdd_en)(f.get('gdd',0), d.get('crop',''))}")
            lines.append(f"Precipitation: {_DESCRIBE_PRECIP.get(language, _describe_precip_en)(f.get('precipitation_mm',0), d.get('crop',''))}")
            s = f.get('soil_moisture', 0.5)
            lines.append(f"Soil Moisture: {'wet' if s>0.6 else 'moist' if s>0.4 else 'dry'} ({s:.0%})")
        m = d.get("model_info", {})
        if m:
            mae_pct = m.get('cv_mae_pct', 0)
            lines.append(f"Model error: ±{mae_pct:.1f}% ({m.get('n_samples','?')} samples, {m.get('countries_trained','?')} EU countries)")
        
        # Historical comparison
        comp = d.get("comparison", {})
        if comp and comp.get("status") != "no_data":
            prev = comp.get("previous_year", {})
            mean5 = comp.get("last_5_years_mean", 0)
            if prev:
                py_yield = prev.get("yield_t_ha", 0)
                py_year = prev.get("year", "?")
                diff = pred - py_yield
                lines.append(f"\nvs {py_year}: {diff:+.2f} t/ha ({'above' if diff>0 else 'below'} last year)")
            if mean5:
                diff5 = pred - mean5
                tag = "above" if diff5 > 0.5 else "below" if diff5 < -0.5 else "within"
                lines.append(f"vs 5-yr avg ({mean5:.2f} t/ha): {diff5:+.2f} t/ha ({tag} of range)")
        
        mv = d.get("market_value", {})
        if mv and mv.get("revenue_eur_per_ha"):
            rev = mv["revenue_eur_per_ha"]
            lines.append(f"\nRevenue: {rev:,.0f} €/ha (at {mv.get('price_eur_per_t','?')} €/t)")
            mg = mv.get("margin_eur_per_ha")
            if mg is not None:
                lines.append(f"Margin: {mg:,.0f} €/ha")
            lines.append(f"Price basis: {mv.get('price_source','Reference')}")
        return "\n".join(lines)
    
    # German (default)
    lines = [f"**{crop_de.capitalize()} – Region {region} ({ctry})**"]
    lines.append(f"Ertrag: {pred:.2f} t/ha (Spanne {p10:.2f}–{p90:.2f})")
    f = d.get("features_used", {})
    if f:
        lines.append(f"Temperatur: {_DESCRIBE_GDD.get('de', _describe_gdd)(f.get('gdd',0), d.get('crop',''))}")
        lines.append(f"Niederschlag: {_DESCRIBE_PRECIP.get('de', _describe_precip)(f.get('precipitation_mm',0), d.get('crop',''))}")
        s = f.get('soil_moisture', 0.5)
        lines.append(f"Bodenfeuchte: {'nass' if s>0.6 else 'feucht' if s>0.4 else 'trocken'} ({s:.0%})")
    m = d.get("model_info", {})
    if m:
        mae_pct = m.get('cv_mae_pct', 0)
        lines.append(f"Modellabweichung: ±{mae_pct:.1f}% (aus {m.get('n_samples','?')} Datensätzen, {m.get('countries_trained','?')} EU-Ländern)")
    
    # Historical comparison
    comp = d.get("comparison", {})
    if comp and comp.get("status") != "no_data":
        prev = comp.get("previous_year", {})
        mean5 = comp.get("last_5_years_mean", 0)
        if prev:
            py_yield = prev.get("yield_t_ha", 0)
            py_year = prev.get("year", "?")
            diff = pred - py_yield
            lines.append(f"\nVergleich zu {py_year}: {diff:+.2f} t/ha ({'über' if diff>0 else 'unter'} Vorjahr)")
        if mean5:
            diff5 = pred - mean5
            lines.append(f"Vergleich zu 5-J-Mittel ({mean5:.2f} t/ha): {diff5:+.2f} t/ha ({'über' if diff5>0.5 else 'unter' if diff5<-0.5 else 'im Rahmen'} des Mittels)")
    
    mv = d.get("market_value", {})
    if mv and mv.get("revenue_eur_per_ha"):
        rev = mv["revenue_eur_per_ha"]
        lines.append(f"\nErlös: {rev:,.0f} €/ha (bei {mv.get('price_eur_per_t','?')} €/t)")
        mg = mv.get("margin_eur_per_ha")
        if mg is not None:
            lines.append(f"Deckungsbeitrag: {mg:,.0f} €/ha")
        lines.append(f"Preisbasis: {mv.get('price_source','Referenz')}")
    return "\n".join(lines)

class YieldAndValueInput(BaseModel):
    crop: str = Field(..., pattern=r"^(wheat|corn|barley|rapeseed|sunflower)$", description="Crop (verified: wheat, corn, barley, rapeseed, sunflower)")
    region: str = Field(..., min_length=4, max_length=5, description="NUTS2 code (e.g. DEE0)")
    gdd: float | None = Field(default=None, description="Optional GDD (growing degree days)")
    precipitation_mm: float | None = Field(default=None, description="Optional precipitation in mm")
    language: str | None = Field(default=None, description="Output language: 'de' (German, default) or 'en' (English). Auto-detected if omitted.")


class CompareRegionsInput(BaseModel):
    regions: str = Field(..., description="Comma-separated NUTS2 codes (e.g. 'DEE0,FR10,PL22'). Minimum 2. Max 20.")
    crops: str = Field(..., description="Comma-separated crop names (e.g. 'wheat,corn,barley'). Options: wheat, corn, barley, rapeseed, sunflower.")
    year: int = Field(default=2025, description="Target year for predictions")
    language: str | None = Field(default=None, description="Output language: 'de' or 'en'")


def _handle_yield_and_value(**kwargs: Any) -> list[types.TextContent]:
    v = YieldAndValueInput(**kwargs)
    if not _HAS_EUROPE_MODEL:
        return [types.TextContent(type="text", text=json.dumps({"status":"error","message":"Model not loaded."}))]
    try:
        reg = get_region(v.region)
        cnt = reg.country
    except KeyError:
        return [types.TextContent(type="text", text=json.dumps({"status":"error","message":f"Unknown region: {v.region}"}))]
    gdd = v.gdd
    pr = v.precipitation_mm
    if gdd is None or pr is None:
        try:
            fc = _handle_crop_forecast(crop=v.crop, region=v.region)
            j = json.loads(fc[0].text).get("data", {})
            if gdd is None: gdd = j.get("gdd",{}).get("accumulated", 1300)
            if pr is None: pr = j.get("precipitation_mm",{}).get("accumulated", 350)
        except Exception:
            gdd = gdd or 1300; pr = pr or 350
    solar, soil_m = 5.0, 0.5
    r = predict_europe_yield(v.region, cnt, crop=v.crop, gdd=gdd, precip_mm=pr, solar_kwh=solar, soil_moisture=soil_m)
    if _HAS_MARKET_PRICES:
        r["market_value"] = calculate_revenue(r.get("predicted_yield_t_ha",0), v.crop)
    r["features_used"] = {"gdd":round(gdd,1),"precipitation_mm":round(pr,1),"solar_kwh":round(solar,2),"soil_moisture":round(soil_m,3)}
    r["region"] = v.region
    r["country"] = cnt
    r["crop"] = v.crop

    # V5.1: NDVI satellite correction (adjusts prediction in-place)
    try:
        _apply_ndvi_correction(r, v.region, reg.latitude, reg.longitude, v.crop)
        # Recalculate market value with corrected yield
        if _HAS_MARKET_PRICES and r.get("ndvi_correction", {}).get("applied"):
            r["market_value"] = calculate_revenue(r.get("predicted_yield_t_ha", 0), v.crop)
    except Exception:
        r["ndvi_correction"] = {"applied": False, "reason": "exception_during_correction"}

    # V4.7: Frost outlook for yield_and_value
    try:
        fc = get_forecast(reg.latitude, reg.longitude, reg.altitude)
        r["frost_outlook"] = _analyze_frost_outlook(
            fc.get("forecast", []),
            get_crop(v.crop).frost_sensitive,
            date.fromisoformat(v.as_of_date) if v.as_of_date else date.today()
        )
    except Exception:
        r["frost_outlook"] = {"forecast_frost_days": 0, "risk_level": "unknown"}

    # Historical comparison
    r["comparison"] = _get_crop_comparison(v.crop, v.region)
    r["country"] = cnt
    r["crop"] = v.crop
    lang = v.language or _DEFAULT_LANGUAGE
    summary = _build_human_summary({"data": r}, language=lang)
    return [types.TextContent(type="text", text=json.dumps({
        "status":"ok", "data":r, "summary":summary, "language":lang,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))]


def _handle_compare_regions(**kwargs: Any) -> list[types.TextContent]:
    """Compare multiple regions × crops — find the best combination."""
    v = CompareRegionsInput(**kwargs)
    if not _HAS_EUROPE_MODEL:
        return [types.TextContent(type="text", text=json.dumps({"status":"error","message":"Model not loaded."}))]
    
    region_list = [r.strip().upper() for r in v.regions.split(",") if r.strip()]
    crop_list = [c.strip().lower() for c in v.crops.split(",") if c.strip()]
    
    if len(region_list) < 2:
        return [types.TextContent(type="text", text=json.dumps({"status":"error","message":"At least 2 regions required."}))]
    if len(region_list) > 20:
        return [types.TextContent(type="text", text=json.dumps({"status":"error","message":"Max 20 regions."}))]
    
    results = []
    errors = []
    
    for region_code in region_list:
        try:
            reg = get_region(region_code)
            country = reg.country
        except KeyError:
            errors.append({"region": region_code, "error": "unknown_region"})
            continue
        
        for crop in crop_list:
            try:
                # Default weather parameters for the target year
                gdd = 1400 if crop in ("wheat", "barley") else 1600 if crop == "corn" else 1200
                precip = 350
                
                r = predict_europe_yield(region_code, country, crop=crop,
                                         gdd=gdd, precip_mm=precip)
                
                y = r.get("predicted_yield_t_ha", 0)
                p10 = r.get("p10", y * 0.8)
                p90 = r.get("p90", y * 1.2)
                baseline = r.get("model_info", {}).get("baseline_yield_t_ha", y)
                mae_pct = r.get("model_info", {}).get("cv_mae_pct", 15)
                samples = r.get("model_info", {}).get("n_samples", 0)
                
                # Try NDVI correction
                try:
                    reg_obj = get_region(region_code)
                    _apply_ndvi_correction(r, region_code, reg_obj.latitude, reg_obj.longitude, crop)
                    y_corrected = r.get("predicted_yield_t_ha", y)
                    ndvi_info = r.get("ndvi_correction", {})
                except Exception:
                    y_corrected = y
                    ndvi_info = {"applied": False}
                
                # Market value — calculate_revenue returns a dict
                market_val = None
                if _HAS_MARKET_PRICES:
                    try:
                        from .market_prices import calculate_revenue as _calc_rev
                        _rev = _calc_rev(y_corrected, crop)
                        if isinstance(_rev, dict):
                            market_val = _rev.get("revenue_eur_per_ha")
                    except Exception:
                        pass
                
                results.append({
                    "region": region_code,
                    "region_name": reg_obj.name if 'reg_obj' in dir() else reg.name,
                    "country": country,
                    "crop": crop,
                    "predicted_yield_t_ha": round(y_corrected, 3),
                    "risk_range_t_ha": [round(p10, 3), round(p90, 3)],
                    "baseline_t_ha": round(baseline, 3),
                    "mae_pct": mae_pct,
                    "n_training_samples": samples,
                    "market_value_eur_per_ha": market_val,
                    "ndvi_correction_applied": ndvi_info.get("applied", False),
                })
            except Exception as e:
                errors.append({"region": region_code, "crop": crop, "error": str(e)[:100]})
    
    # Sort by yield descending
    results.sort(key=lambda x: x["predicted_yield_t_ha"], reverse=True)
    
    lang = v.language or _DEFAULT_LANGUAGE
    summary_parts = []
    if results:
        best = results[0]
        summary_parts.append(f"Best: {best['crop']} in {best['region']} ({best['region_name']}) — {best['predicted_yield_t_ha']:.2f} t/ha" +
                            (f" — {best['market_value_eur_per_ha']:.0f}€/ha" if best['market_value_eur_per_ha'] else ""))
        if len(results) > 1:
            worst = results[-1]
            summary_parts.append(f"Worst: {worst['crop']} in {worst['region']} ({worst['region_name']}) — {worst['predicted_yield_t_ha']:.2f} t/ha")
    
    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "results": results,
        "errors": errors,
        "summary": "; ".join(summary_parts),
        "parameters": {
            "regions": region_list,
            "crops": crop_list,
            "year": v.year,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, indent=2))]


def _handle_list_regions(**kwargs: Any) -> list[types.TextContent]:
    """List available regions, optionally filtered by country."""
    validated = ListRegionsInput(**kwargs)
    regions = list_regions(validated.country)
    result = []
    for code, r in sorted(regions.items()):
        result.append({
            "code": code,
            "name": r.name,
            "country": r.country,
            "crops": r.major_crops,
            "area_km2": r.area_km2,
            "latitude": r.latitude,
            "longitude": r.longitude,
        })
    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "count": len(result),
        "regions": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))]


def _handle_list_crops(**kwargs: Any) -> list[types.TextContent]:
    """List all supported crops with agronomic parameters."""
    crops = list_crops()
    result = []
    for name, c in sorted(crops.items()):
        result.append({
            "name": c.name,
            "name_de": c.name_de,
            "gdd_base_temp": c.gdd_base,
            "gdd_optimum": c.gdd_optimum,
            "planting_month": c.planting_month,
            "harvest_month": c.harvest_month,
            "frost_sensitive": c.frost_sensitive,
            "water_sensitivity": c.water_sensitivity,
            "description": c.description,
        })
    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "count": len(result),
        "crops": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))]


# ─────────────────────────────────────────────────────────────
# Tool Registry
# ─────────────────────────────────────────────────────────────

TOOLS = {
    "weather_outlook": {
        "handler": _handle_weather_outlook,
        "description": (
            "16-day weather forecast for an EU agricultural region. Returns "
            "temperature, precipitation, and wind data. Call this before making "
            "crop forecasts to understand immediate weather conditions."
        ),
        "input_schema": WeatherOutlookInput.model_json_schema(),
    },
    "crop_forecast": {
        "handler": _handle_crop_forecast,
        "description": (
            "Crop-specific yield outlook for a region. Combines current weather, "
            "historical comparison, and crop phenology models. Returns GDD "
            "accumulation, precipitation, drought index, and yield signals. "
            "This is the primary intelligence tool — use it to assess crop "
            "health and expected yield relative to historical averages."
        ),
        "input_schema": CropForecastInput.model_json_schema(),
    },
    "season_comparison": {
        "handler": _handle_season_comparison,
        "description": (
            "Compare the current growing season to historical years for a "
            "specific crop and region. Returns GDD, precipitation, frost days, "
            "and heat days for each year. Use to detect trends and anomalies."
        ),
        "input_schema": SeasonComparisonInput.model_json_schema(),
    },
    "list_regions": {
        "handler": _handle_list_regions,
        "description": (
            "List available EU agricultural regions with their NUTS2 codes, "
            "coordinates, and major crops. Filter by country code (e.g. 'FR', "
            "'DE', 'PL'). Call this first to discover valid region codes."
        ),
        "input_schema": ListRegionsInput.model_json_schema(),
    },
    "list_crops": {
        "handler": _handle_list_crops,
        "description": (
            "List all supported crop types with their agronomic parameters "
            "(GDD base temperature, growing season, water sensitivity). "
            "Use this to understand which crops are available and their "
            "biological requirements."
        ),
        "input_schema": ListCropsInput.model_json_schema(),
    },
    "region_health": {
        "handler": _handle_region_health,
        "description": (
            "Comprehensive health overview for an entire agricultural region. "
            "Returns crop_forecast for ALL crops grown in the region — GDD, "
            "precipitation, soil moisture, solar radiation, and yield signals "
            "in a single call. Use this for a complete regional assessment."
        ),
        "input_schema": RegionHealthInput.model_json_schema(),
    },
    "yield_forecast": {
        "handler": _handle_yield_forecast,
        "description": (
            "Predict crop yield in t/ha using analog-year matching. "
            "Compares current season's weather (GDD, precipitation, solar radiation, "
            "soil moisture) to 25 years of historical data, finds the most similar "
            "years, and projects their yields. Returns mean, min, max, and top analogs. "
            "Confidence increases as the season progresses."
        ),
        "input_schema": YieldForecastInput.model_json_schema(),
    },
    "europe_yield_forecast": {
        "handler": _handle_europe_yield_forecast,
        "description": (
            "Pan-European yield forecast for 5 verified crops (wheat, corn, barley, rapeseed, sunflower). "
            "Uses Random Forest trained on Eurostat yield data (C1100/C1300/C1500/C2000/C2200) "
            "across 25 EU countries. Combines weather + 7 soil features + yield-at-risk."
        ),
        "input_schema": EuropeanYieldForecastInput.model_json_schema(),
    },
    "climate_scenario": {
        "handler": _handle_climate_scenario,
        "description": (
            "Climate What-If scenario analysis for EU crop yields. "
            "Use this to answer 'What if May-June is 2°C warmer?' or "
            "'What if we get 20% less rain?'"
        ),
        "input_schema": ClimateScenarioInput.model_json_schema(),
    },
    "yield_and_value": {
        "handler": _handle_yield_and_value,
        "description": (
            "Combined yield forecast + market value estimation. "
            "Returns yield in t/ha AND expected revenue in EUR/ha at current market prices. "
            "Output includes a plain-language summary in German (default) or English. "
            "Set language='en' for English output, language='de' for German. "
            "Auto-detects from the language parameter if provided. "
            "Verified crops: wheat, corn, barley, rapeseed, sunflower."
        ),
        "input_schema": YieldAndValueInput.model_json_schema(),
    },
    "compare_regions": {
        "handler": _handle_compare_regions,
        "description": (
            "Compare crop yields across multiple EU regions in a single call. "
            "Input comma-separated NUTS2 region codes and crop names. "
            "Returns a sorted table of predicted yields, risk ranges, and market values. "
            "Use this to find the best region×crop combination for investment decisions. "
            "Example: compare_regions(regions='DEE0,FR10,HU10', crops='wheat,corn')"
        ),
        "input_schema": CompareRegionsInput.model_json_schema(),
    },
}


# ─────────────────────────────────────────────────────────────
# MCP Server
# ─────────────────────────────────────────────────────────────

server = Server("crop-mcp")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=name,
            description=meta["description"],
            inputSchema=meta["input_schema"],
        )
        for name, meta in TOOLS.items()
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    meta = TOOLS.get(name)
    if not meta:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "error_code": "UNKNOWN_TOOL",
            "message": f"Tool '{name}' not found. Available: {list(TOOLS.keys())}",
        }))]
    try:
        return meta["handler"](**(arguments or {}))
    except KeyError as e:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "error_code": "UNKNOWN_KEY",
            "message": str(e),
        }))]
    except ValueError as e:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "message": str(e),
        }))]
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "error_code": "TOOL_ERROR",
            "message": str(e),
            "traceback": tb.split("\n")[-6:] if "--debug" in sys.argv else "Use --debug for traceback",
        }))]


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="crop-mcp",
                server_version="4.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def self_test() -> int:
    """Run self-test on all tools."""
    print("=== crop-mcp Self-Test ===\n")

    tests = [
        ("list_crops", {}),
        ("list_regions", {}),
        ("list_regions", {"country": "DE"}),
        ("weather_outlook", {"region": "FRF2", "days": 3}),
        ("crop_forecast", {"crop": "wheat", "region": "DEE0"}),
        ("season_comparison", {"crop": "wheat", "region": "FRF2", "reference_years": 3}),
    ]

    all_passed = True
    for name, args in tests:
        try:
            result = TOOLS[name]["handler"](**args)
            payload = json.loads(result[0].text)
            status = payload.get("status", "?")
            emoji = "✅" if status == "ok" else "❌"
            preview = json.dumps(payload, indent=2)[:150]
            print(f"  {emoji} {name}({json.dumps(args)})")
            all_passed = all_passed and (status == "ok")
        except Exception as e:
            print(f"  ❌ {name}({json.dumps(args)}) → {e}")
            all_passed = False

    print(f"\n{'✅ All tests passed!' if all_passed else '❌ Some tests failed.'}")
    return 0 if all_passed else 1


# ─────────────────────────────────────────────────────────────
# Hot-Reload (--reload flag)
# ─────────────────────────────────────────────────────────────

def _run_with_reload() -> None:
    """
    Run the server with auto-reload on file changes.
    Spawns the server as a subprocess, watches .py files, and restarts on change.
    No external dependencies needed — uses os.stat + polling.
    """
    import os
    import subprocess
    import time

    watch_dirs = {
        os.path.dirname(os.path.abspath(__file__)),  # project root
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"),
    }
    watch_exts = {".py"}

    def _get_mtimes() -> dict:
        mtimes = {}
        for d in watch_dirs:
            if not os.path.isdir(d):
                continue
            for fname in os.listdir(d):
                if any(fname.endswith(ext) for ext in watch_exts):
                    fpath = os.path.join(d, fname)
                    try:
                        mtimes[fpath] = os.path.getmtime(fpath)
                    except OSError:
                        pass
        return mtimes

    server_script = os.path.abspath(__file__)
    print(f"[reload] Starting crop-mcp with hot-reload...")
    print(f"[reload] Watching {len(watch_dirs)} directories for .py changes")

    last_mtimes = _get_mtimes()
    proc = None

    def _start_server():
        nonlocal proc
        proc = subprocess.Popen(
            [sys.executable, server_script],
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        print(f"[reload] Server started (PID {proc.pid})")

    _start_server()

    try:
        while True:
            time.sleep(2)
            current_mtimes = _get_mtimes()
            changed = []
            for fpath, mtime in current_mtimes.items():
                old = last_mtimes.get(fpath)
                if old is not None and mtime > old:
                    changed.append(os.path.basename(fpath))
                last_mtimes[fpath] = mtime

            if changed:
                print(f"[reload] 🔄 Detected changes in: {', '.join(changed)}")
                print(f"[reload] Restarting server...")
                if proc:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                _start_server()
                last_mtimes = _get_mtimes()

    except KeyboardInterrupt:
        print(f"\n[reload] Shutting down...")
        if proc:
            proc.terminate()
            proc.wait()
        sys.exit(0)




# ── Public API for CLI ──

def run_stdio():
    """Start the MCP server in stdio mode (default)."""
    import asyncio
    asyncio.run(main())

async def run_http(host: str = "0.0.0.0", port: int = 8080):
    """Start the MCP server in HTTP/SSE mode."""
    try:
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route
    except ImportError:
        print("HTTP mode requires: pip install mcp[httpx] uvicorn")
        sys.exit(1)

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            read_stream, write_stream = streams
            await server.run(read_stream, write_stream, server.create_initialization_options())

    async def handle_root(request):
        from starlette.responses import JSONResponse
        return JSONResponse({
            "server": "crop-mcp",
            "version": "4.6.0",
            "description": "EU Crop Intelligence MCP Server — Yield forecasts, market values & risk analysis for EU agriculture. 10 tools, 120+ NUTS2 regions, 5 crops, 25-year climate library.",
            "tools": list(TOOLS.keys()),
            "docs": "https://github.com/DasClown/CropProphEU",
            "endpoints": {
                "sse": "/sse",
                "server_card": "/.well-known/mcp/server-card.json",
                "config_schema": "/.well-known/mcp/config-schema.json",
            }
        })

    async def handle_server_card(request):
        from starlette.responses import JSONResponse
        from copy import deepcopy
        tools_list = []
        for name, meta in TOOLS.items():
            tools_list.append({
                "name": name,
                "description": meta["description"],
                "inputSchema": meta["input_schema"],
            })
        return JSONResponse({
            "serverInfo": {"name": "crop-mcp", "version": "4.6.0"},
            "description": "EU Crop Intelligence MCP Server. Combines NASA POWER (weather), Open-Meteo, Eurostat (yields), SoilGrids (soil), and Yahoo Finance (market prices) into comprehensive crop intelligence for AI agents. Output in German or English.",
            "homepage": "https://github.com/DasClown/CropProphEU",
            "license": "MIT",
            "author": {
                "name": "CropProphEU",
                "email": "",
                "url": "https://github.com/DasClown",
            },
            "iconUrl": "https://raw.githubusercontent.com/DasClown/CropProphEU/main/static/icon.svg",
            "capabilities": {
                "tools": {"total": len(tools_list), "list": [t["name"] for t in tools_list]},
                "resources": {"total": 2, "list": ["crops://parameters", "regions://list"]},
                "prompts": {"total": 3, "list": ["analyze-region", "compare-regions", "market-overview"]},
            },
            "dataSources": [
                {"name": "NASA POWER", "type": "weather", "url": "https://power.larc.nasa.gov/"},
                {"name": "Open-Meteo", "type": "weather", "url": "https://open-meteo.com/"},
                {"name": "Eurostat", "type": "yield", "url": "https://ec.europa.eu/eurostat/"},
                {"name": "SoilGrids", "type": "soil", "url": "https://soilgrids.org/"},
                {"name": "Yahoo Finance", "type": "market", "url": "https://finance.yahoo.com/"},
                {"name": "CBOT", "type": "market", "url": "https://www.cmegroup.com/markets/agriculture/"},
            ],
            "tools": tools_list,
            "resources": [
                {
                    "name": "Crop Parameters",
                    "uri": "crops://parameters",
                    "description": "Agronomische Parameter aller unterstützten Kulturen: GDD-Basistemperatur, Wachstumsperiode, Wasserbedarf",
                    "mimeType": "application/json",
                },
                {
                    "name": "Region List",
                    "uri": "regions://list",
                    "description": "Alle verfügbaren EU NUTS2-Regionen mit Koordinaten, Ländern und Hauptkulturen",
                    "mimeType": "application/json",
                },
            ],
            "prompts": [
                {
                    "name": "analyze-region",
                    "description": "Complete health check for a region: yield forecast + market value + weather for all crops",
                    "arguments": [
                        {"name": "region", "description": "NUTS2 region code", "required": True},
                    ],
                },
                {
                    "name": "compare-regions",
                    "description": "Compare two EU regions across all metrics for a specific crop",
                    "arguments": [
                        {"name": "crop", "description": "Crop name (wheat, corn, rapeseed, sunflower, barley)", "required": True},
                        {"name": "region_a", "description": "First NUTS2 region", "required": True},
                        {"name": "region_b", "description": "Second NUTS2 region", "required": True},
                    ],
                },
                {
                    "name": "market-overview",
                    "description": "Current market prices and yield outlook for top EU producers",
                    "arguments": [
                        {"name": "crop", "description": "Crop to analyze", "required": True},
                    ],
                },
            ],
        })

    async def handle_config_schema(request):
        from starlette.responses import JSONResponse
        return JSONResponse({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "default_region": {
                    "type": "string",
                    "title": "Standard-Region",
                    "default": "DEE0",
                    "description": "NUTS2-Region für Standard-Abfragen (z.B. DEE0 = Sachsen-Anhalt)",
                    "examples": ["DEE0", "FRF2", "HU21"],
                    "pattern": "^[A-Z]{2}[A-Z0-9]{2,3}$",
                },
                "language": {
                    "type": "string",
                    "title": "Language",
                    "default": "de",
                    "enum": ["de", "en"],
                    "description": "Output language for summaries: 'de' (German) or 'en' (English)",
                },
                "confidence_threshold": {
                    "type": "number",
                    "title": "Konfidenz-Schwelle",
                    "default": 0.3,
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Minimale Konfidenz für Ertragsprognosen (0.0 = alle anzeigen, 1.0 = nur sichere)",
                },
            },
            "required": [],
        })

    app = Starlette(
        routes=[
            Route("/", endpoint=handle_root),
            Route("/.well-known/mcp/server-card.json", endpoint=handle_server_card),
            Route("/.well-known/mcp/config-schema.json", endpoint=handle_config_schema),
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )
    import uvicorn
    config = uvicorn.Config(app, host=host, port=port)
    srv = uvicorn.Server(config)
    print(f"🌾 crop-mcp HTTP server on http://{host}:{port}/sse")
    await srv.serve()


if __name__ == "__main__":
    if "--reload" in sys.argv:
        _run_with_reload()
    elif "--test" in sys.argv:
        sys.exit(self_test())
    elif "--list-tools" in sys.argv:
        print(json.dumps([{"name": n, "description": t["description"][:80]}
                          for n, t in TOOLS.items()], indent=2))
    else:
        # Parse --language from CLI args before starting
        for i, arg in enumerate(sys.argv):
            if arg == "--language" and i + 1 < len(sys.argv):
                _DEFAULT_LANGUAGE = sys.argv[i + 1]
                break
        import asyncio
        asyncio.run(main())
