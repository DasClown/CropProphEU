#!/usr/bin/env python3
"""Build Ukraine training data for crop yield models."""
import json, sys, os, time
sys.path.insert(0, '/home/j/crop-mcp')
from crop_mcp.core.regions import REGIONS, get_crop, get_region
from crop_mcp.sources.faostat import fetch_ukraine_yield, compile_ukraine_data
from crop_mcp.sources.power import season_solar_and_soil, get_power_data
from crop_mcp.sources.power import SOLAR_PARAM, SOIL_M1, T2M_MAX, T2M_MIN, PRECIP

RATE_LIMIT_DELAY = 0.2

def get_power_weather(lat, lon, year, plant_m, harvest_m, gdd_base):
    """Get weather features for a season."""
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
    
    import calendar
    gdd = 0.0; precip = 0.0; solar_sum = 0.0; soil_sum = 0.0
    n_soil = 0; n_solar = 0
    
    for m in months:
        ym = fetch_start if m >= plant_m and plant_m > harvest_m else fetch_end
        tmax = raw.get(T2M_MAX, {}).get(m)
        tmin = raw.get(T2M_MIN, {}).get(m)
        pr = raw.get(PRECIP, {}).get(m)
        sol = raw.get(SOLAR_PARAM, {}).get(m)
        soil = raw.get(SOIL_M1, {}).get(m)
        days = calendar.monthrange(ym, m)[1]
        
        if tmax is not None and tmin is not None:
            gdd += max(0, ((tmax + tmin) / 2) - gdd_base) * days
        if pr is not None:
            precip += pr * days
        if sol is not None:
            solar_sum += sol; n_solar += 1
        if soil is not None:
            soil_sum += soil; n_soil += 1
    
    return {
        'gdd': round(gdd, 1),
        'precip_mm': round(precip, 1),
        'solar_kwh': round(solar_sum / n_solar, 2) if n_solar else None,
        'soil_moisture': round(soil_sum / n_soil, 3) if n_soil else None,
    }

def main():
    crops = ["wheat", "sunflower"]
    
    for crop_name in crops:
        print(f"\n{'='*50}")
        print(f"📦 Ukraine build for {crop_name}")
        
        yields = fetch_ukraine_yield(crop_name)
        if not yields:
            print(f"  ❌ No yield data for {crop_name}")
            continue
        
        years = sorted(yields.keys())
        print(f"  Yields: {len(years)} yr ({years[0]}-{years[-1]})")
        
        # Ukraine NUTS2 regions
        ua_regions = sorted([c for c, r in REGIONS.items() if r.country == "UA"])
        print(f"  Regions: {len(ua_regions)} ({', '.join(ua_regions)})")
        
        crop = get_crop(crop_name)
        samples = []
        
        for reg_code in ua_regions:
            reg = get_region(reg_code)
            for year in years:
                weather = get_power_weather(reg.latitude, reg.longitude, year,
                                           crop.planting_month, crop.harvest_month, crop.gdd_base)
                if weather is None:
                    print(f"  ⏳ {reg_code} {year}: weather failed")
                    continue
                
                ss = season_solar_and_soil(reg.latitude, reg.longitude, year,
                                          crop.planting_month, crop.harvest_month)
                
                samples.append({
                    'country': 'UA', 'region': reg_code, 'year': year,
                    'gdd': weather['gdd'], 'precip_mm': weather['precip_mm'],
                    'solar_kwh': weather['solar_kwh'], 'soil_moisture': weather['soil_moisture'],
                    'solar_anom_pct': ss['solar_radiation_kwh_m2_day'].get('anomaly_vs_same_months_pct', 0),
                    'soil_anom_pct': ss['soil_moisture_root_zone'].get('anomaly_vs_same_months_pct', 0),
                    'yield_t_ha': yields[year],
                })
                time.sleep(RATE_LIMIT_DELAY)
            
            print(f"  ✅ {reg_code}: done ({len([s for s in samples if s['region']==reg_code])} samples)")
        
        # Save
        out_path = f"/home/j/crop-mcp/europe_training_data_ukraine_{crop_name}.json"
        with open(out_path, 'w') as f:
            json.dump(samples, f, indent=2)
        
        countries = sorted(set(s['country'] for s in samples))
        print(f"\n✅ Saved: {len(samples)} samples → {out_path}")
        print(f"   Countries: {countries}")
        print(f"   Regions: {len(set(s['region'] for s in samples))}")
        print(f"   Years: {min(s['year'] for s in samples)}-{max(s['year'] for s in samples)}")
        
        # Also append to existing wheat/sunflower data
        existing_path = f"/home/j/crop-mcp/data/europe_training_data_{crop_name}.json"
        if os.path.exists(existing_path):
            with open(existing_path) as f:
                existing = json.load(f)
            combined = existing + samples
            combined_path = f"/home/j/crop-mcp/data/europe_training_data_{crop_name}_with_ua.json"
            with open(combined_path, 'w') as f:
                json.dump(combined, f, indent=2)
            print(f"   Merged with existing: {len(combined)} total")

if __name__ == "__main__":
    main()
