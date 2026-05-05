#!/usr/bin/env python3
"""Build UK + Ukraine training data — sequential, no interruptions."""
import json, sys, os, time

sys.path.insert(0, '/home/j/crop-mcp')
from crop_mcp.core.regions import REGIONS, get_crop, get_region
from crop_mcp.sources.power import season_solar_and_soil, get_power_data
from crop_mcp.sources.power import SOLAR_PARAM, SOIL_M1, T2M_MAX, T2M_MIN, PRECIP
from build_europe import fetch_eurostat

RATE = 0.2

def weather(lat, lon, year, plant_m, harvest_m, gdd_base):
    if plant_m > harvest_m:
        months = list(range(plant_m, 13)) + list(range(1, harvest_m + 1))
        fs = year - 1; fe = year
    else:
        months = list(range(plant_m, harvest_m + 1))
        fs = year; fe = year
    import calendar
    raw = get_power_data(lat, lon, fs, fe, [SOLAR_PARAM, SOIL_M1, T2M_MAX, T2M_MIN, PRECIP])
    if raw is None: return None
    g=0; p=0; ss=0; sm=0; ns=0; nm=0
    for m in months:
        ym = fs if (m >= plant_m and plant_m > harvest_m) else fe
        d = calendar.monthrange(ym, m)[1]
        tmax = raw.get(T2M_MAX, {}).get(m); tmin = raw.get(T2M_MIN, {}).get(m)
        pr = raw.get(PRECIP, {}).get(m); sol = raw.get(SOLAR_PARAM, {}).get(m); soi = raw.get(SOIL_M1, {}).get(m)
        if tmax is not None and tmin is not None: g += max(0, ((tmax+tmin)/2)-gdd_base)*d
        if pr is not None: p += pr*d
        if sol is not None: ss += sol; ns += 1
        if soi is not None: sm += soi; nm += 1
    return {
        'gdd': round(g,1), 'precip_mm': round(p,1),
        'solar_kwh': round(ss/ns,2) if ns else None,
        'soil_moisture': round(sm/nm,3) if nm else None,
    }

def build_country(cntry, crop_name):
    """Build training samples for one country + crop."""
    crop = get_crop(crop_name)
    code_map = {"wheat":"C1100","barley":"C1300","corn":"C1500","rapeseed":"C2000","sunflower":"C2200"}
    
    # Get yields
    yields = fetch_eurostat(cntry, code_map[crop_name])
    if not yields:
        print(f"  ⚠️ {cntry}: no Eurostat yield data for {crop_name}")
        return []
    
    years = sorted(yields.keys())
    regions = sorted([c for c, r in REGIONS.items() if r.country == cntry])
    print(f"  {cntry} {crop_name}: {len(regions)} regions × {len(years)} years = {len(regions)*len(years)}")
    
    samples = []
    for reg_code in regions:
        reg = get_region(reg_code)
        for year in years:
            w = weather(reg.latitude, reg.longitude, year, crop.planting_month, crop.harvest_month, crop.gdd_base)
            if w is None:
                print(f"    ⏳ {reg_code} {year}: weather fail")
                continue
            ss = season_solar_and_soil(reg.latitude, reg.longitude, year, crop.planting_month, crop.harvest_month)
            samples.append({
                'country': cntry, 'region': reg_code, 'year': year,
                'gdd': w['gdd'], 'precip_mm': w['precip_mm'],
                'solar_kwh': w['solar_kwh'], 'soil_moisture': w['soil_moisture'],
                'solar_anom_pct': ss['solar_radiation_kwh_m2_day'].get('anomaly_vs_same_months_pct', 0),
                'soil_anom_pct': ss['soil_moisture_root_zone'].get('anomaly_vs_same_months_pct', 0),
                'soc_g_kg': 15.0, 'ph': 6.5, 'clay_pct': 25.0, 'sand_pct': 40.0, 'silt_pct': 35.0,
                'nitrogen_g_kg': 1.5, 'cec_cmol_kg': 18.0, 'bdod_kg_dm3': 1.35, 'cfvo_pct': 5.0, 'coarse_pct': 5.0, 'awc_mm_m': 150.0,
                'yield_t_ha': yields[year],
            })
            time.sleep(RATE)
        print(f"    ✅ {reg_code}: {len([s for s in samples if s['region']==reg_code])}")
    return samples

def main():
    # UK — barley + corn
    for crop in ["barley", "corn"]:
        print(f"\n{'='*50}")
        print(f"🇬🇧 UK — {crop}")
        samples = build_country("UK", crop)
        if samples:
            # Append to existing
            ex_path = f"/home/j/crop-mcp/data/europe_training_data_{crop}.json"
            with open(ex_path) as f:
                existing = json.load(f)
            combined = existing + samples
            out_path = f"/home/j/crop-mcp/data/europe_training_data_{crop}_with_uk.json"
            with open(out_path, 'w') as f:
                json.dump(combined, f, indent=2)
            print(f"  ✅ UK {crop}: {len(samples)} samples → merged ({len(combined)} total)")
    
    # Ukraine — wheat + sunflower (using compiled FAO data)
    print(f"\n{'='*50}")
    print(f"🇺🇦 Ukraine — wheat + sunflower")
    from crop_mcp.sources.faostat import compile_ukraine_data
    ua_yields = compile_ukraine_data()
    
    for crop in ["wheat", "sunflower"]:
        yields = ua_yields[crop]
        years = sorted(yields.keys())
        regions = sorted([c for c, r in REGIONS.items() if r.country == "UA"])
        print(f"  UA {crop}: {len(regions)} regions × {len(years)} years = {len(regions)*len(years)}")
        
        c = get_crop(crop)
        samples = []
        for reg_code in regions:
            reg = get_region(reg_code)
            for year in years:
                w = weather(reg.latitude, reg.longitude, year, c.planting_month, c.harvest_month, c.gdd_base)
                if w is None: continue
                ss = season_solar_and_soil(reg.latitude, reg.longitude, year, c.planting_month, c.harvest_month)
                samples.append({
                    'country': 'UA', 'region': reg_code, 'year': year,
                    'gdd': w['gdd'], 'precip_mm': w['precip_mm'],
                    'solar_kwh': w['solar_kwh'], 'soil_moisture': w['soil_moisture'],
                    'solar_anom_pct': ss['solar_radiation_kwh_m2_day'].get('anomaly_vs_same_months_pct', 0),
                    'soil_anom_pct': ss['soil_moisture_root_zone'].get('anomaly_vs_same_months_pct', 0),
                    'soc_g_kg': 15.0, 'ph': 6.5, 'clay_pct': 25.0, 'sand_pct': 40.0, 'silt_pct': 35.0,
                    'nitrogen_g_kg': 1.5, 'cec_cmol_kg': 18.0, 'bdod_kg_dm3': 1.35, 'cfvo_pct': 5.0, 'coarse_pct': 5.0, 'awc_mm_m': 150.0,
                    'yield_t_ha': yields[year],
                })
                time.sleep(RATE)
            print(f"    ✅ {reg_code}: done")
        
        # Save Ukraine data
        out_f = f"/home/j/crop-mcp/europe_training_data_ua_{crop}.json"
        with open(out_f, 'w') as f:
            json.dump(samples, f, indent=2)
        print(f"  ✅ UA {crop}: {len(samples)} samples saved")
        
        # Merge with existing  
        ex_path = f"/home/j/crop-mcp/data/europe_training_data_{crop}.json"
        if os.path.exists(ex_path):
            with open(ex_path) as f:
                existing = json.load(f)
            combined = existing + samples
            with open(f"/home/j/crop-mcp/data/europe_training_data_{crop}_with_ua.json", 'w') as f:
                json.dump(combined, f, indent=2)
            print(f"     Merged: {len(combined)} total")

if __name__ == "__main__":
    main()
    print("\n✅ ALL DONE")
