"""Weather and crop forecast handler functions for crop-mcp."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

import mcp.types as types

from crop_mcp.core.regions import get_region, get_crop
from crop_mcp.sources.weather import (
    get_forecast,
    get_historical,
    analyze_growing_season,
    calc_gdd,
    drought_index,
)
from crop_mcp.sources.power import season_solar_and_soil, season_gdd_precip_power
from crop_mcp.tools.helpers import (
    _get_season_dates,
    _analyze_frost_outlook,
    _detect_language,
)

# Optional: NDVI
_HAS_NDVI = False
try:
    from crop_mcp.sources.ndvi import get_ndvi as _get_ndvi
    _HAS_NDVI = True
except Exception:
    pass

# Optional: Cache
_HAS_CACHE = False
try:
    from crop_mcp.feature_cache import get as _cache_get
    _HAS_CACHE = True
except Exception:
    pass


def _handle_weather_outlook(**kwargs: Any) -> list[types.TextContent]:
    """16-day weather forecast for a region."""
    # Local import to avoid circular dependency on server models
    from crop_mcp.server import WeatherOutlookInput
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
    """V2: Synthesize a crop forecast from weather + POWER satellite + historical data."""
    from crop_mcp.server import CropForecastInput
    validated = CropForecastInput(**kwargs)
    crop = get_crop(validated.crop)
    region = get_region(validated.region)

    ref_date = date.fromisoformat(validated.as_of_date) if validated.as_of_date else date.today()
    current_year = ref_date.year

    # Determine the current growing season
    season_start, season_end = _get_season_dates(validated.crop, current_year)

    # 1. Analyze current season weather (up to ref_date)
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
        if date.fromisoformat(season_start) <= ref_date:
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

    # 3. Historical comparison
    current_season_start = date.fromisoformat(season_start)
    days_elapsed = (ref_date - current_season_start).days
    hist_years = min(validated.reference_years, current_year - 2000)
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

    # 5. Drought assessment
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

    # 5b. NDVI
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

    solar_anom = power.get("solar_radiation_kwh_m2_day", {}).get("anomaly_vs_same_months_pct", 0)
    if solar_anom and solar_anom < -15:
        yield_signals.append("low_solar_radiation")
    elif solar_anom and solar_anom > 20:
        yield_signals.append("high_solar_radiation")

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
    power_only = season_data_source == "power" and season.get("extremes", {}).get("hot_days_gt_30c") is None
    confidence = "low" if season_progress < 25 else "medium" if season_progress < 60 else "high"
    if power_only and confidence == "high":
        confidence = "medium"
    data_sources_list = ["nasa-power"]
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
    from crop_mcp.server import SeasonComparisonInput
    validated = SeasonComparisonInput(**kwargs)
    crop = get_crop(validated.crop)
    region = get_region(validated.region)

    today = date.today()
    current_year = today.year

    years_data = []
    use_cache = _HAS_CACHE and validated.crop == "wheat"

    for y in range(current_year - validated.reference_years, current_year + 1):
        season_start, season_end = _get_season_dates(validated.crop, y)
        end_date = min(date.fromisoformat(season_end), today).isoformat()

        try:
            if use_cache and y < current_year:
                cached = _cache_get(region.code, y, region.latitude, region.longitude,
                                    crop.planting_month, crop.harvest_month, crop.gdd_base)
                if cached:
                    years_data.append({
                        "year": y,
                        "gdd": cached["gdd"],
                        "precipitation_mm": cached["precip_mm"],
                        "solar_kwh": cached["solar_kwh"],
                        "soil_moisture": cached["soil_moisture"],
                        "frost_days": None,
                        "heat_days": None,
                        "days_recorded": 365,
                        "source": "cache",
                    })
                    continue

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


def _handle_region_health(**kwargs: Any) -> list[types.TextContent]:
    """Comprehensive health overview: all crops, weather, soil, solar — in one call."""
    from crop_mcp.server import RegionHealthInput
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
