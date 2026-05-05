#!/usr/bin/env python3
"""Build UK-only training data and merge with existing."""
import json, sys, os, time
sys.path.insert(0, '/home/j/crop-mcp')
from crop_mcp.core.regions import REGIONS, get_crop, get_region
from crop_mcp.sources.weather import get_historical, calc_gdd
from crop_mcp.sources.power import season_solar_and_soil, get_power_data
from crop_mcp.sources.power import SOLAR_PARAM, SOIL_M1, T2M_MAX, T2M_MIN, PRECIP

RATE_LIMIT_DELAY = 0.2

def fetch_uk_yield(crop_code="C1300"):
    """Fetch UK yield from Eurostat."""
    import urllib.request
    url = f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/apro_cpshr?format=JSON&lang=EN&crops={crop_code}&strucpro=YI_HU_EU&geo=UK"
    req = urllib.request.Request(url, headers={"User-Agent": "crop-mcp/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        d = json.loads(resp.read().decode())
    vals = d.get("value", {})
    time_idx = d.get("dimension",{}).get("time",{}).get("category",{}).get("index",{})
    time_pos = {v: k for k, v in time_idx.items()}
    data = {}
    for pos_str, val in vals.items():
        year = time_pos.get(int(pos_str), "?")
        data[year] = val
    return {int(y): v for y, v in data.items() if str(y).isdigit() and v > 0}

def get_power_weather(lat, lon, year, plant_m, harvest_m, gdd_base):
    """Get weather features for a season."""
    from crop_mcp.sources.power import get_power_data
    if plant_m > harvest_m:
        months = list(range(plant_m, 13)) + list(range(1, harvest_m + 1))
        fetch_start = year - 1
        fetch_end = year
    else:
        months = list(range(plant_m, harvest_m + 1))
        fetch_start = year
        fetch_end = year
    
    params = [SOLAR_PARAM, SOIL_M1, T2M_MAX, T2M_MIN, PRECIP]
    raw = get_power_data(lat, lon, fetch_start, fetch_end, params)
    if raw is None:
        return None
    
    gdd = 0.0
    precip = 0.0
    solar_sum = 0.0
    soil_sum = 0.0
    n_soil = 0
    n_solar = 0
    
    for m in months:
        ym = fetch_start if m >= plant_m and plant_m > harvest_m else fetch_end
        tmax = raw.get(T2M_MAX, {}).get(m)
        tmin = raw.get(T2M_MIN, {}).get(m)
        pr = raw.get(PRECIP, {}).get(m)
        sol = raw.get(SOLAR_PARAM, {}).get(m)
        soil = raw.get(SOIL_M1, {}).get(m)
        
        import calendar
        days = calendar.monthrange(ym, m)[1]
        
        if tmax is not None and tmin is not None:
            gdd += max(0, ((tmax + tmin) / 2) - gdd_base) * days
        if pr is not None:
            precip += pr * days
        if sol is not None:
            solar_sum += sol
            n_solar += 1
        if soil is not None:
            soil_sum += soil
            n_soil += 1
    
    return {
        'gdd': round(gdd, 1),
        'precip_mm': round(precip, 1),
        'solar_kwh': round(solar_sum / n_solar, 2) if n_solar else None,
        'soil_moisture': round(soil_sum / n_soil, 3) if n_soil else None,
    }

def build_one_sample(cntry, reg_code, year, crop):
    """Build a single feature sample."""
    reg = get_region(reg_code)
    if not reg:
        return None
    
    lat, lon = reg.latitude, reg.longitude
    weather = get_power_weather(lat, lon, year, crop.planting_month, crop.harvest_month, crop.gdd_base)
    if weather is None:
        return None
    
    # Solar + soil anomalies
    ss = season_solar_and_soil(lat, lon, year, crop.planting_month, crop.harvest_month)
    
    return {
        'country': cntry,
        'region': reg_code,
        'year': year,
        'gdd': weather['gdd'],
        'precip_mm': weather['precip_mm'],
        'solar_kwh': weather['solar_kwh'],
        'soil_moisture': weather['soil_moisture'],
        'solar_anom_pct': ss['solar_radiation_kwh_m2_day'].get('anomaly_vs_same_months_pct', 0),
        'soil_anom_pct': ss['soil_moisture_root_zone'].get('anomaly_vs_same_months_pct', 0),
        'yield_t_ha': None,
    }

def main():
    crops_map = {"barley": "C1300", "corn": "C1500"}
    
    for crop_name, crop_code in crops_map.items():
        print(f"\n{'='*50}")
        print(f"📦 UK build for {crop_name}")
        print(f"{'='*50}")
        
        # Fetch UK yields
        yields = fetch_uk_yield(crop_code)
        print(f"UK {crop_name}: {len(yields)} years")
        for y in sorted(yields.keys()):
            print(f"  {y}: {yields[y]:.2f} t/ha")
        
        # Find UK regions
        uk_regions = [c for c, r in REGIONS.items() if r.country == "UK"]
        print(f"UK regions: {uk_regions}")
        
        crop = get_crop(crop_name)
        
        # Build features
        uk_samples = []
        for reg_code in uk_regions:
            for year in sorted(yields.keys()):
                sample = build_one_sample("UK", reg_code, year, crop)
                if sample:
                    sample['yield_t_ha'] = yields[year]
                    uk_samples.append(sample)
                    print(f"  ✅ {reg_code} {year}: {yields[year]:.2f} t/ha")
                else:
                    print(f"  ❌ {reg_code} {year}: weather fetch failed")
                time.sleep(RATE_LIMIT_DELAY)
        
        # Load existing data
        existing_path = f"/home/j/crop-mcp/data/europe_training_data_{crop_name}.json"
        with open(existing_path) as f:
            existing = json.load(f)
        
        # Merge
        existing.extend(uk_samples)
        
        # Save merged
        merged_path = f"/home/j/crop-mcp/europe_training_data_{crop_name}_uk.json"
        with open(merged_path, 'w') as f:
            json.dump(existing, f, indent=2)
        
        print(f"\n✅ Merged: {len(existing)} total ({len(existing)-len(uk_samples)} existing + {len(uk_samples)} UK)")
        print(f"   Saved to: {merged_path}")

if __name__ == "__main__":
    main()
