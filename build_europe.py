#!/usr/bin/env python3
"""
European-scale yield model — NASA POWER based (no rate limits).
Builds features for ALL 59 NUTS2 regions across 15 EU countries.
"""
import json, urllib.request, sys, time, os, random
from datetime import date

sys.path.insert(0, '/home/j/crop-mcp')
from crop_mcp.core.regions import REGIONS, get_region, get_crop
from crop_mcp.sources.weather import get_historical, calc_gdd
from crop_mcp.sources.power import season_solar_and_soil, get_power_data
from crop_mcp.sources.power import SOLAR_PARAM, SOIL_M1, T2M_MAX, T2M_MIN, PRECIP

CHECKPOINT = '/home/j/crop-mcp/europe_checkpoint.json'
OUTPUT = '/home/j/crop-mcp/europe_training_data.json'
RATE_LIMIT_DELAY = 0.2  # Between samples (POWER has no rate limit)

# Crop-specific paths (set in main)
CROP_CHECKPOINT = None
CROP_OUTPUT = None

COUNTRIES = ["DE", "FR", "PL", "RO", "HU", "ES", "IT", "DK", "NL", "BE", "AT", "CZ", "SK", "BG", "SE",
             # V4.2 EU27 expansion
             "PT", "EL", "IE", "HR", "SI", "LT", "LV", "EE", "FI", "CY", "MT"]

# Pre-build country→region map
countries_with_regions = {}
for code, r in REGIONS.items():
    countries_with_regions.setdefault(r.country, []).append(code)

# Global: populated after Step 1
country_yields = {}

# Eurostat crop codes (verified data sources)
# C1100 = Common wheat + spelt → wheat
# C1300 = Barley
# C1500 = Grain maize → corn
# I1110 = Rape and turnip rape seeds (wir haben hier fälschlich C2000 = Rice verwendet!)
# I1120 = Sunflower seed (C2200 = Rice Japonica — falscher Code!)
EUROSTAT_CROP_CODES = {
    "wheat": "C1100",
    "barley": "C1300",
    "corn": "C1500",
    "rapeseed": "I1110",
    "sunflower": "I1120",
}

# Crop-specific country lists (only countries with verified Eurostat yield data)
CROP_COUNTRIES = {
    "wheat": COUNTRIES + ["UA"],
    "barley": COUNTRIES + ["UK"],
    "corn": COUNTRIES + ["UK"],
    "rapeseed": COUNTRIES + ["UK"],
    "sunflower": ["FR", "RO", "HU", "ES", "IT", "BG", "PT", "EL"] + ["UA"],
}

DAYS_IN_MONTH = {1:31,2:28,3:31,4:30,5:31,6:30,7:31,8:31,9:30,10:31,11:30,12:31}

def fetch_eurostat(country_code, crop_code="C1100"):
    """Fetch crop yields from Eurostat. Returns {year: yield_t_ha}."""
    url = f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/apro_cpshr?format=JSON&lang=EN&crops={crop_code}&strucpro=YI_HU_EU&geo={country_code}"
    req = urllib.request.Request(url, headers={"User-Agent": "crop-mcp/4.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        d = json.loads(resp.read().decode())
    vals = d.get("value", {})
    time_idx = d.get("dimension",{}).get("time",{}).get("category",{}).get("index",{})
    time_pos = {v: k for k, v in time_idx.items()}
    return {int(time_pos.get(int(pos_str), "?")): float(val) for pos_str, val in vals.items()}


def get_power_weather(lat, lon, year, plant_m, harvest_m, gdd_base):
    """
    Calculate full-season features from NASA POWER monthly data.
    Returns (gdd, precip_mm, solar_kwh, soil_moisture)
    or (None, ...) on failure. Anomalies computed separately.
    """
    params = [SOLAR_PARAM, SOIL_M1, T2M_MAX, T2M_MIN, PRECIP]
    
    # Season months (winter wheat: Oct Y-1 to Jul Y)
    if plant_m > harvest_m:
        months = list(range(plant_m, 13)) + list(range(1, harvest_m + 1))
        fetch_start = year - 1
    else:
        months = list(range(plant_m, harvest_m + 1))
        fetch_start = year
    
    data = get_power_data(lat, lon, fetch_start, year, params=params)
    
    total_gdd = total_precip = 0.0
    solar_sum = soil_sum = 0.0
    data_months = 0
    
    for m in months:
        key_candidates = [f"{year - 1}{str(m).zfill(2)}", f"{year}{str(m).zfill(2)}"]
        tmax = tmin = precip_mm = solar = soil = None
        for k in key_candidates:
            if k in data.get(T2M_MAX, {}):
                tmax = data[T2M_MAX][k]
                tmin = data[T2M_MIN].get(k) if T2M_MIN in data else None
                precip_mm = data[PRECIP].get(k) if PRECIP in data else None
                solar = data[SOLAR_PARAM].get(k) if SOLAR_PARAM in data else None
                soil = data[SOIL_M1].get(k) if SOIL_M1 in data else None
                break
        
        if tmax is not None and tmin is not None:
            days = DAYS_IN_MONTH[m]
            daily_gdd = max(0, (tmax + tmin) / 2 - gdd_base)
            total_gdd += daily_gdd * days
        
        if precip_mm is not None:
            total_precip += precip_mm * DAYS_IN_MONTH[m]
        
        if solar is not None:
            solar_sum += solar
        if soil is not None:
            soil_sum += soil
        data_months += 1
    
    if data_months == 0 or total_gdd == 0:
        return None, None, None, None
    
    return total_gdd, total_precip, solar_sum / data_months, soil_sum / data_months


def build_one_sample(cntry, reg_code, year, crop):
    """Build features for one region-year from NASA POWER."""
    try:
        region = get_region(reg_code)
        season_start = date(year - 1, crop.planting_month, 1)
        ref_date = date(year, 5, 1)
        
        if ref_date < season_start:
            return None
        
        # NASA POWER features (primary)
        gdd, precip, solar_kwh, soil_m = get_power_weather(
            region.latitude, region.longitude, year,
            crop.planting_month, crop.harvest_month, crop.gdd_base
        )
        
        # Fallback: Open-Meteo daily data
        if gdd is None or gdd == 0:
            try:
                season_end = date(year, crop.harvest_month, 28)
                actual_end = min(ref_date, season_end)
                hist = get_historical(region.latitude, region.longitude,
                                      season_start.isoformat(), actual_end.isoformat())
                if hist and hist.get("days"):
                    gdd = 0.0
                    precip = 0.0
                    solar_kwh = 5.0
                    soil_m = 0.5
                    for day in hist["days"]:
                        if day["t_max"] is not None and day["t_min"] is not None:
                            gdd += calc_gdd(day["t_max"], day["t_min"], crop.gdd_base)
                        if day["precipitation_mm"] is not None:
                            precip += day["precipitation_mm"]
            except Exception:
                pass
        
        if gdd is None or gdd == 0:
            return None
        
        yield_val = country_yields.get(cntry, {}).get(year)
        if yield_val is None:
            return None
        
        # Static soil features from SoilGrids + LUCAS Texture (V4.1)
        soil_cache_path = '/home/j/crop-mcp/soil_cache.json'
        _soil = {}
        if os.path.exists(soil_cache_path):
            with open(soil_cache_path) as _f:
                _soil = json.load(_f).get(reg_code, {})

        return {
            "region": reg_code,
            "country": cntry,
            "year": year,
            "gdd": round(gdd, 1),
            "precip_mm": round(precip, 1),
            "solar_kwh": round(solar_kwh, 2),
            "solar_anom_pct": 0.0,
            "soil_moisture": round(soil_m, 3),
            "soil_anom_pct": 0.0,
            # V4.1 Soil features (static per region)
            "soc_g_kg": round(_soil.get("soc_g_kg", 15.0), 1),
            "ph": round(_soil.get("ph", 6.5), 1),
            "clay_pct": round(_soil.get("clay_pct", 25.0), 1),
            "sand_pct": round(_soil.get("sand_pct", 40.0), 1),
            "silt_pct": round(_soil.get("silt_pct", 35.0), 1),
            "nitrogen_g_kg": round(_soil.get("nitrogen_g_kg", 1.5), 2),
            "cec_cmol_kg": round(_soil.get("cec_cmol_kg", 18.0), 1),
            # V4.7 Soil-Tiefe Features: Bulk Density, Coarse Fragments, AWC
            "bdod_kg_dm3": round(_soil.get("bdod_kg_dm3", 1.35), 2),
            "cfvo_pct": round(_soil.get("cfvo_pct", 5.0), 1),
            "coarse_pct": round(_soil.get("coarse_pct", 5.0), 1),
            "awc_mm_m": round(_soil.get("awc_mm_m", 150.0), 1),
            "yield_t_ha": yield_val,
        }
    except Exception:
        return None


def load_checkpoint():
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT) as f:
            cp = json.load(f)
        return cp["all_features"], cp.get("processed_countries", [])
    return [], []


def save_checkpoint(features, processed):
    with open(CHECKPOINT, 'w') as f:
        json.dump({"all_features": features, "processed_countries": list(processed)}, f)


# ── MAIN ──
if __name__ == '__main__':
    import sys as _sys
    
    # Support --crop argument → use separate checkpoint/output per crop
    _crop_name = "wheat"
    for i, arg in enumerate(_sys.argv):
        if arg == "--crop" and i + 1 < len(_sys.argv):
            _crop_name = _sys.argv[i + 1]
    
    if _crop_name != "wheat":
        CHECKPOINT = f'/home/j/crop-mcp/europe_checkpoint_{_crop_name}.json'
        OUTPUT = f'/home/j/crop-mcp/europe_training_data_{_crop_name}.json'
    
    # Verify Eurostat data source exists for this crop
    _eurostat_code = EUROSTAT_CROP_CODES.get(_crop_name)
    if not _eurostat_code:
        print(f"\n❌ ERROR: No verified Eurostat yield data for '{_crop_name}'.")
        print(f"   Available crops: {list(EUROSTAT_CROP_CODES.keys())}")
        sys.exit(1)
    
    # Use crop-specific country list
    _crop_countries = CROP_COUNTRIES.get(_crop_name, COUNTRIES)

    all_features, processed_countries = load_checkpoint()
    crop = get_crop(_crop_name)

    print(f"🔄 Resume: {len(all_features)} samples done, processed: {processed_countries}")

    # Step 1: Download yields for ALL countries (including processed, for yield lookup)
    print(f"\n=== Step 1: Country yields ({len(_crop_countries)} countries) ===")
    for c in _crop_countries:
        try:
            country_yields[c] = fetch_eurostat(c, _eurostat_code)
            print(f"  {c}: {len(country_yields[c])} years")
            time.sleep(0.2)
        except Exception as e:
            print(f"  {c}: ERROR — {str(e)[:50]}")

    # Step 2: Generate features per country
    print("\n=== Step 2: Feature generation ===")
    for cntry in _crop_countries:
        if cntry in processed_countries:
            n = len([s for s in all_features if s['country'] == cntry])
            print(f"  {cntry}: ✓ already done ({n} samples)")
            continue
        
        yields = country_yields.get(cntry, {})
        regions = countries_with_regions.get(cntry, [])
        
        if not regions:
            print(f"  {cntry}: 0 regions mapped ✗")
            processed_countries.append(cntry)
            save_checkpoint(all_features, processed_countries)
            continue
        
        if not yields:
            print(f"  {cntry}: no yield data ✗")
            processed_countries.append(cntry)
            save_checkpoint(all_features, processed_countries)
            continue
        
        total_pairs = len(regions) * len(yields)
        print(f"  {cntry}: {len(regions)} regions × {len(yields)} years = {total_pairs}")
        
        successes = 0
        failures = 0
        
        for reg_code in regions:
            for year in sorted(yields.keys()):
                sample = build_one_sample(cntry, reg_code, year, crop)
                if sample:
                    all_features.append(sample)
                    successes += 1
                else:
                    failures += 1
                
                time.sleep(RATE_LIMIT_DELAY)
                
                if len(all_features) % 30 == 0:
                    save_checkpoint(all_features, processed_countries)
                    print(f"    ... {len(all_features)} total (✓{successes} ✗{failures}) — checkpoint")
        
        processed_countries.append(cntry)
        save_checkpoint(all_features, processed_countries)
        print(f"  ✅ {cntry}: {successes} ok, {failures} failed (total: {len(all_features)})")
    
    # Final save
    with open(OUTPUT, 'w') as f:
        json.dump(all_features, f, indent=2)
    
    countries_ok = sorted(set(s['country'] for s in all_features))
    print(f"\n{'='*50}")
    print(f"✅ COMPLETE! {len(all_features)} samples → {OUTPUT}")
    print(f"   Countries with data: {countries_ok}")
    
    # Cleanup
    os.remove(CHECKPOINT)
    print("   Checkpoint cleaned up ✓")
