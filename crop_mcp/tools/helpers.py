"""Shared utility functions for crop-mcp MCP tools."""

from __future__ import annotations

import os
from datetime import date, timedelta

from crop_mcp.core.regions import get_crop

_DEFAULT_LANGUAGE = os.environ.get("CROP_LANGUAGE", "de")


# ─────────────────────────────────────────────────────────────
# Language utilities
# ─────────────────────────────────────────────────────────────

def _detect_language(kwargs: dict) -> str:
    """Detect language from tool arguments or fall back to server default."""
    lang = kwargs.get("language", _DEFAULT_LANGUAGE)
    if lang not in ("de", "en"):
        lang = _DEFAULT_LANGUAGE
    return lang


# ─────────────────────────────────────────────────────────────
# NDVI Correction for Predictions
# ─────────────────────────────────────────────────────────────

def _apply_ndvi_correction(result: dict, region_code: str, lat: float, lon: float, crop: str) -> dict:
    """Apply NDVI correction to a prediction result (mutates in-place)."""
    _HAS_NDVI_CORRECTION = False
    _HAS_NDVI = False
    try:
        from crop_mcp.ndvi_correction import compute_ndvi_correction as _ndvi_correct
        _HAS_NDVI_CORRECTION = True
    except Exception:
        pass
    try:
        from crop_mcp.sources import ndvi as _ndvi_mod_check
        _HAS_NDVI = True
    except Exception:
        pass

    if not _HAS_NDVI_CORRECTION or not _HAS_NDVI:
        result["ndvi_correction"] = {"applied": False, "reason": "ndvi_module_unavailable"}
        return result

    model_yield = result.get("predicted_yield_t_ha", result.get("yield_t_ha"))
    if model_yield is None:
        return result

    # Import here to avoid circular issues
    from crop_mcp.sources import ndvi as _ndvi_mod
    from crop_mcp.ndvi_correction import compute_ndvi_correction as _ndvi_correct

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


# ─────────────────────────────────────────────────────────────
# GDD description (German + English)
# ─────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────
# Season dates
# ─────────────────────────────────────────────────────────────

def _get_season_dates(crop_name: str, year: int) -> tuple[str, str]:
    """Determine the growing season date range for a crop."""
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


# ─────────────────────────────────────────────────────────────
# Frost Outlook Analysis
# ─────────────────────────────────────────────────────────────

def _analyze_frost_outlook(forecast_days: list, frost_sensitive: bool,
                           ref_date: date) -> dict:
    """Analyze the 16-day forecast for frost events (t_min < 0°C)."""
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
        risk = "low"

    # Critical period check
    critical = False
    if frost_sensitive and next_frost:
        critical = frost_sensitive and frost_count_5d > 0

    return {
        "forecast_frost_days": len(frost_days),
        "frost_days_detail": frost_days[:5],
        "next_frost_date": next_frost["date"] if next_frost else None,
        "next_frost_temp_c": next_frost["t_min_c"] if next_frost else None,
        "frost_in_5_days": frost_count_5d,
        "risk_level": risk,
        "critical_period_alert": critical,
    }


# ─────────────────────────────────────────────────────────────
# Crop cost helper (for portfolio optimizer)
# ─────────────────────────────────────────────────────────────

def _get_crop_cost(crop: str, country: str = None) -> int:
    """Get production cost for a crop, country-specific if possible."""
    try:
        from crop_mcp.market_prices import get_production_cost as _gpc
        info = _gpc(crop, country)
        return info["eur_per_ha"]
    except Exception:
        return {
            "wheat": 650, "barley": 600, "corn": 700,
            "rapeseed": 780, "sunflower": 650,
        }.get(crop, 700)
