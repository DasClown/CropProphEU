"""
LUCAS Soil + SoilGrids integration for European crop yield model.
Provides static soil properties per NUTS2 region centroid.

Data sources:
  - LUCAS Texture: point measurements of clay/sand/silt (2018)
  - SoilGrids v2.0 (ISRIC): SOC, pH, CEC, Nitrogen at 250m resolution
  - European Soil Database (ESDB) fallback

All values are per-NUTS2-region averages (static, no year-to-year variation).
"""

import json, os, time, math, sys
from typing import Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# LUCAS texture data path
LUCAS_TEXTURE_PATH = '/tmp/LUCAS_Text_All_10032025.csv'

# SoilGrids API
SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"

# Cache to avoid repeated API calls
_soil_cache: Dict[str, Dict] = {}

# LUCAS point data (lazy loaded)
_lucas_points: List[Dict] = None

# Soil properties we use (SoilGrids property names)
# V4.7: Added bdod (bulk density) and cfvo (coarse fragments volume)
SOIL_PROPERTIES = ["soc", "phh2o", "nitrogen", "cec", "clay", "sand", "silt",
                    "bdod", "cfvo"]
SOIL_DEPTH = "0-5cm"  # Topsoil — most relevant for agriculture

# ──────────────────────────────────────────────
# SoilGrids API
# ──────────────────────────────────────────────

def _query_soilgrids(lat: float, lon: float) -> Optional[Dict]:
    """Query SoilGrids for soil properties at a point. Returns dict of property→mean_value."""
    cache_key = f"{lat:.2f}_{lon:.2f}"
    if cache_key in _soil_cache:
        return _soil_cache[cache_key]

    params = f"lon={lon}&lat={lat}"
    for p in SOIL_PROPERTIES:
        params += f"&property={p}"
    params += f"&depth={SOIL_DEPTH}&value=mean"

    url = f"{SOILGRIDS_URL}?{params}"
    try:
        req = Request(url, headers={"User-Agent": "crop-mcp/4.0"})
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())

        result = {}
        layers = data.get("properties", {}).get("layers", [])
        for layer in layers:
            name = layer["name"]
            depths = layer.get("depths", [])
            for d in depths:
                if d["label"] == "0-5cm":
                    vals = d.get("values", {})
                    mean = vals.get("mean")
                    if mean is not None:
                        result[name] = mean
                    break

        # Convert to SI units
        if "phh2o" in result:
            result["phh2o"] = result["phh2o"] / 10.0  # dg → actual pH
        if "soc" in result:
            result["soc"] = result["soc"] / 10.0  # dg/kg → g/kg
        if "nitrogen" in result:
            result["nitrogen"] = result["nitrogen"] / 100.0  # cg/kg → g/kg
        if "cec" in result:
            result["cec"] = result["cec"] / 10.0  # mmol(c)/kg → cmol(c)/kg
        if "bdod" in result:
            result["bdod"] = result["bdod"] / 100.0  # cg/cm³ → kg/dm³ (g/cm³)
        if "cfvo" in result:
            result["cfvo"] = result["cfvo"] / 10.0  # cm³/dm³ → % (vol%)

        _soil_cache[cache_key] = result
        time.sleep(1)  # Rate limit: 1 req/s
        return result

    except HTTPError as e:
        if e.code == 429:
            time.sleep(5)  # Retry after backoff
            return _query_soilgrids(lat, lon)
        return None
    except Exception:
        return None


# ──────────────────────────────────────────────
# LUCAS Texture (from point measurements)
# ──────────────────────────────────────────────

def _load_lucas_texture() -> List[Dict]:
    """Load LUCAS texture points into memory."""
    global _lucas_points
    if _lucas_points is not None:
        return _lucas_points

    if not os.path.exists(LUCAS_TEXTURE_PATH):
        _lucas_points = []
        return []

    import csv
    points = []
    with open(LUCAS_TEXTURE_PATH) as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Only include points with valid texture data
            if row.get("PSDAvailable", "").strip().upper() == "YES":
                points.append({
                    "country": row.get("NUTS_0", ""),
                    "clay": float(row.get("Clay", 0) or 0),
                    "sand": float(row.get("Sand", 0) or 0),
                    "silt": float(row.get("Silt", 0) or 0),
                    "coarse": float(row.get("Coarse", 0) or 0),
                })

    _lucas_points = points
    return points


def get_region_texture(country: str) -> Dict:
    """Get country-average soil texture from LUCAS points.
    V4.7: Also returns coarse fragments and derived AWC."""
    points = _load_lucas_texture()
    country_points = [p for p in points if p["country"] == country]

    if not country_points:
        return {"clay_pct": 25.0, "sand_pct": 40.0, "silt_pct": 35.0,
                "coarse_pct": 5.0, "awc_mm_m": 150.0,
                "source": "default_european_loam"}

    clay = sum(p["clay"] for p in country_points) / len(country_points)
    sand = sum(p["sand"] for p in country_points) / len(country_points)
    silt = sum(p["silt"] for p in country_points) / len(country_points)
    coarse = sum(p["coarse"] for p in country_points) / len(country_points)

    # Compute Available Water Capacity (AWC) via Saxton pedotransfer function
    # AWC = θ_fc - θ_pwp, derived from clay + sand + bulk density
    # Simplified: AWC (mm/m) ≈ 250 - 1.5*sand_pct + 2.5*clay_pct
    awc = 250.0 - 1.5 * sand + 2.5 * clay
    awc = max(50.0, min(300.0, awc))  # Clamp to realistic range

    return {
        "clay_pct": round(clay, 1),
        "sand_pct": round(sand, 1),
        "silt_pct": round(silt, 1),
        "coarse_pct": round(coarse, 1),
        "awc_mm_m": round(awc, 1),
        "source": f"lucas_2018_texture_{len(country_points)}_points"
    }


# ──────────────────────────────────────────────
# Combined soil profile per region
# ──────────────────────────────────────────────

def get_soil_profile(lat: float, lon: float, country: str,
                     region_code: str = "") -> Dict:
    """
    Get complete soil profile for a region: SoilGrids chemistry + LUCAS texture.
    Returns static features (soil doesn't change year-to-year).
    """
    # Try SoilGrids first
    sg = _query_soilgrids(lat, lon)

    if sg and sg.get("soc") and sg["soc"] > 0:
        profile = {
            "soc_g_kg": round(sg.get("soc", 15.0), 1),
            "ph": round(sg.get("phh2o", 6.5), 1),
            "nitrogen_g_kg": round(sg.get("nitrogen", 1.5), 2),
            "cec_cmol_kg": round(sg.get("cec", 20.0), 1),
            "bdod_kg_dm3": round(sg.get("bdod", 1.3), 2),
            "cfvo_pct": round(sg.get("cfvo", 5.0), 1),
            "soil_source": "soilgrids_v2",
        }
    else:
        # Fallback: country averages from literature
        profile = _country_soil_fallback(country)
        profile["soil_source"] = "country_fallback"

    # Add texture from LUCAS (doesn't overwrite chemistry keys)
    texture = get_region_texture(country)
    profile["clay_pct"] = texture["clay_pct"]
    profile["sand_pct"] = texture["sand_pct"]
    profile["silt_pct"] = texture["silt_pct"]
    profile["coarse_pct"] = texture["coarse_pct"]
    profile["awc_mm_m"] = texture["awc_mm_m"]
    profile["texture_source"] = texture["source"]

    return profile


def _country_soil_fallback(country: str) -> Dict:
    """Soil defaults by country based on literature.
    V4.7: Added bdod (bulk density) and cfvo (coarse fragments)."""
    defaults = {
        "DE": {"soc_g_kg": 16.0, "ph": 6.2, "nitrogen_g_kg": 1.6, "cec_cmol_kg": 18.0,
               "bdod_kg_dm3": 1.45, "cfvo_pct": 3.5},
        "FR": {"soc_g_kg": 18.0, "ph": 6.8, "nitrogen_g_kg": 1.8, "cec_cmol_kg": 15.0,
               "bdod_kg_dm3": 1.40, "cfvo_pct": 8.0},
        "PL": {"soc_g_kg": 14.0, "ph": 5.8, "nitrogen_g_kg": 1.3, "cec_cmol_kg": 12.0,
               "bdod_kg_dm3": 1.50, "cfvo_pct": 4.0},
        "RO": {"soc_g_kg": 22.0, "ph": 6.5, "nitrogen_g_kg": 2.0, "cec_cmol_kg": 24.0,
               "bdod_kg_dm3": 1.35, "cfvo_pct": 2.0},
        "HU": {"soc_g_kg": 20.0, "ph": 7.0, "nitrogen_g_kg": 1.9, "cec_cmol_kg": 22.0,
               "bdod_kg_dm3": 1.38, "cfvo_pct": 2.5},
        "ES": {"soc_g_kg": 12.0, "ph": 7.5, "nitrogen_g_kg": 1.1, "cec_cmol_kg": 14.0,
               "bdod_kg_dm3": 1.50, "cfvo_pct": 12.0},
        "IT": {"soc_g_kg": 15.0, "ph": 7.2, "nitrogen_g_kg": 1.4, "cec_cmol_kg": 20.0,
               "bdod_kg_dm3": 1.42, "cfvo_pct": 10.0},
        "DK": {"soc_g_kg": 20.0, "ph": 6.0, "nitrogen_g_kg": 1.8, "cec_cmol_kg": 16.0,
               "bdod_kg_dm3": 1.48, "cfvo_pct": 1.0},
        "NL": {"soc_g_kg": 22.0, "ph": 5.5, "nitrogen_g_kg": 2.0, "cec_cmol_kg": 20.0,
               "bdod_kg_dm3": 1.35, "cfvo_pct": 1.5},
        "BE": {"soc_g_kg": 16.0, "ph": 6.2, "nitrogen_g_kg": 1.6, "cec_cmol_kg": 14.0,
               "bdod_kg_dm3": 1.40, "cfvo_pct": 5.0},
        "AT": {"soc_g_kg": 18.0, "ph": 6.5, "nitrogen_g_kg": 1.7, "cec_cmol_kg": 18.0,
               "bdod_kg_dm3": 1.38, "cfvo_pct": 15.0},
        "CZ": {"soc_g_kg": 16.0, "ph": 6.0, "nitrogen_g_kg": 1.5, "cec_cmol_kg": 16.0,
               "bdod_kg_dm3": 1.45, "cfvo_pct": 3.0},
        "SK": {"soc_g_kg": 16.0, "ph": 6.0, "nitrogen_g_kg": 1.5, "cec_cmol_kg": 16.0,
               "bdod_kg_dm3": 1.45, "cfvo_pct": 3.0},
        "BG": {"soc_g_kg": 18.0, "ph": 6.8, "nitrogen_g_kg": 1.6, "cec_cmol_kg": 22.0,
               "bdod_kg_dm3": 1.35, "cfvo_pct": 2.0},
        "SE": {"soc_g_kg": 14.0, "ph": 5.5, "nitrogen_g_kg": 1.2, "cec_cmol_kg": 14.0,
               "bdod_kg_dm3": 1.30, "cfvo_pct": 20.0},
    }
    return defaults.get(country, {"soc_g_kg": 15.0, "ph": 6.5,
                                   "nitrogen_g_kg": 1.5, "cec_cmol_kg": 18.0,
                                   "bdod_kg_dm3": 1.40, "cfvo_pct": 5.0})


# ──────────────────────────────────────────────
# Fast batch: pre-compute for all NUTS2 regions
# ──────────────────────────────────────────────

def precompute_all_soil() -> Dict[str, Dict]:
    """
    Pre-compute soil profiles for ALL NUTS2 regions.
    Returns dict of {region_code: soil_profile}.
    Caches to JSON for fast loading.
    """
    cache_path = '/home/j/crop-mcp/soil_cache.json'
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)

    # Lazy import to avoid circular imports at module level
    from crop_mcp.core.regions import REGIONS

    soil_data = {}
    total = len(REGIONS)
    for i, (code, region) in enumerate(sorted(REGIONS.items())):
        if region.country in ("UA", "UK"):
            continue  # Skip non-EU countries with limited data
        print(f"  [{i+1}/{total}] {code} ({region.country})...", end=" ")
        profile = get_soil_profile(region.latitude, region.longitude,
                                   region.country, code)
        soil_data[code] = profile
        print(f"SOC={profile.get('soc_g_kg','?')} pH={profile.get('ph','?')}")

    # Cache to disk
    with open(cache_path, 'w') as f:
        json.dump(soil_data, f, indent=2)
    print(f"✅ Soil cache saved: {cache_path} ({len(soil_data)} regions)")

    return soil_data


# ──────────────────────────────────────────────
# Quick test
# ──────────────────────────────────────────────

if __name__ == "__main__":
    profile = get_soil_profile(51.9, 11.7, "DE", "DEE0")
    print(f"DEE0 (Sachsen-Anhalt): {json.dumps(profile, indent=2)}")
