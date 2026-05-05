"""
NDVI Correction Module — adjusts model predictions based on satellite vegetation index.

The core idea: NDVI anomaly (current vs. expected for the region/season) provides
a real-time signal that the model can't capture (it only knows historical weather).

Correction logic:
  ndvi_anomaly = current_ndvi - expected_ndvi (for this region in this month)
  correction_factor = 1.0 + (ndvi_anomaly * NDVI_SENSITIVITY[crop])
  
  corrected_yield = model_prediction * correction_factor

Sensitivity calibrated from literature:
  - Wheat: NDVI explains ~40% of yield variability (Becker-Reshef + Vermote, 2010)
  - Corn/Maize: ~35% (Mkhabela et al., 2011)
  - Barley: ~30%
  - Rapeseed: ~25%
  - Sunflower: ~25%
"""
import json
import os
import time
from datetime import date, timedelta
from typing import Dict, Optional

# Crop-specific NDVI sensitivity (how much yield changes per 0.1 NDVI anomaly)
# Higher = more sensitive to NDVI changes
NDVI_SENSITIVITY = {
    "wheat": 0.25,      # 0.1 NDVI → ±2.5% yield
    "barley": 0.20,
    "corn": 0.22,
    "rapeseed": 0.18,
    "sunflower": 0.18,
}

# Historical NDVI references per region (compiled from Sentinel-2 2017-2024)
# Format: {region_code: {month: mean_ndvi}}
# Fallback: use 0.6 (typical peak for European agriculture)
_NDVI_REFERENCE_CACHE = {}
_NDVI_REF_PATH = None  # Set by init


def _compute_expected_ndvi(region_code: str, month: int) -> float:
    """Get expected NDVI for a region in a given month (historical average)."""
    # Check cache first
    if region_code in _NDVI_REFERENCE_CACHE:
        refs = _NDVI_REFERENCE_CACHE[region_code]
        if month in refs:
            return refs[month]
    
    # Fallbacks by month (European growing season typical values)
    # These are derived from literature averages for temperate agriculture
    monthly_fallback = {
        1: 0.35, 2: 0.35, 3: 0.40, 4: 0.50,
        5: 0.60, 6: 0.65, 7: 0.60, 8: 0.55,
        9: 0.50, 10: 0.45, 11: 0.40, 12: 0.35,
    }
    return monthly_fallback.get(month, 0.50)


def compute_ndvi_correction(
    model_prediction: float,
    region_code: str,
    lat: float,
    lon: float,
    crop: str,
    reference_date: Optional[str] = None,
    ndvi_module=None,
) -> Dict:
    """
    Compute NDVI-corrected yield.
    
    Args:
        model_prediction: Raw model output (t/ha)
        region_code: NUTS2 code
        lat, lon: Coordinates for satellite fetch
        crop: Crop name (must be in NDVI_SENSITIVITY)
        reference_date: ISO date (default: today)
        ndvi_module: The ndvi.py module (imported externally to avoid circular)
    
    Returns:
        dict with correction details
    """
    if ndvi_module is None:
        return {
            "corrected_yield_t_ha": model_prediction,
            "correction_factor": 1.0,
            "ndvi": None,
            "ndvi_expected": None,
            "note": "ndvi_module_not_available",
        }
    
    if crop not in NDVI_SENSITIVITY:
        return {
            "corrected_yield_t_ha": model_prediction,
            "correction_factor": 1.0,
            "ndvi": None,
            "ndvi_expected": None,
            "note": f"crop '{crop}' not in sensitivity table",
        }
    
    ref = date.fromisoformat(reference_date) if reference_date else date.today()
    month = ref.month
    
    # Get current NDVI
    try:
        ndvi_result = ndvi_module.get_ndvi(lat, lon, ref.isoformat(), max_lookback_days=45)
        if ndvi_result.get("status") != "ok" or not ndvi_result.get("latest"):
            return {
                "corrected_yield_t_ha": model_prediction,
                "correction_factor": 1.0,
                "ndvi": None,
                "ndvi_expected": _compute_expected_ndvi(region_code, month),
                "note": "ndvi_fetch_failed",
            }
        current_ndvi = ndvi_result["latest"]["ndvi"]
        ndvi_date = ndvi_result["latest"]["date"]
        cloud_pct = ndvi_result["latest"]["cloud_cover_pct"]
    except Exception:
        return {
            "corrected_yield_t_ha": model_prediction,
            "correction_factor": 1.0,
            "ndvi": None,
            "ndvi_expected": None,
            "note": "ndvi_exception",
        }
    
    # NDVI < 0.05 is not reliable — likely no valid satellite data
    if current_ndvi < 0.05:
        return {
            "corrected_yield_t_ha": model_prediction,
            "correction_factor": 1.0,
            "ndvi": None,
            "ndvi_expected": _compute_expected_ndvi(region_code, month),
            "note": f"ndvi_too_low_{current_ndvi}",
        }
    
    # Get expected NDVI for this region/month
    expected_ndvi = _compute_expected_ndvi(region_code, month)
    
    # Correction
    anomaly = current_ndvi - expected_ndvi
    sensitivity = NDVI_SENSITIVITY.get(crop, 0.20)
    correction = 1.0 + (anomaly / 0.1) * sensitivity * 0.1  # normalize
    
    # Clamp correction to reasonable range (±30%)
    correction = max(0.70, min(1.30, correction))
    
    corrected = round(model_prediction * correction, 3)
    
    return {
        "corrected_yield_t_ha": corrected,
        "model_yield_t_ha": round(model_prediction, 3),
        "correction_factor": round(correction, 4),
        "ndvi": {
            "current": current_ndvi,
            "expected": round(expected_ndvi, 3),
            "anomaly": round(anomaly, 3),
            "date": ndvi_date,
            "cloud_cover_pct": cloud_pct,
        },
        "sensitivity": sensitivity,
        "note": "ok",
    }
