#!/usr/bin/env python3
"""
Feature Cache Builder — berechnet alle historischen Region×Jahr-Kombinationen vor.
Der Server nutzt diesen Cache statt Live-APIs für alles außer der aktuellen Saison.

Cache-Struktur: /home/j/crop-mcp/feature_cache/
  {region}_{year}.json → {gdd, precip_mm, solar_kwh, soil_moisture}

Nutzt NASA POWER (kein Rate-Limiting). Einmaliger Build, danach nur Updates für neue Jahre.
"""
import json, os, sys, time
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, '/home/j/crop-mcp')
from crop_mcp.core.regions import REGIONS, get_crop
from crop_mcp.sources.power import get_power_data
from crop_mcp.sources.power import SOLAR_PARAM, SOIL_M1, T2M_MAX, T2M_MIN, PRECIP

CACHE_DIR = '/home/j/crop-mcp/feature_cache'
DAYS_IN_MONTH = {1:31,2:28,3:31,4:30,5:31,6:30,7:31,8:31,9:30,10:31,11:30,12:31}
MAX_WORKERS = 4  # NASA POWER toleriert 4 parallele Calls

# Winter wheat parameter
PLANT_M = 10
HARVEST_M = 7
GDD_BASE = 0.0

def get_features_for_region_year(region_code, lat, lon, year):
    """Berechne Features für eine Region×Jahr-Kombination."""
    if plant_m > harvest_m:
        months = list(range(PLANT_M, 13)) + list(range(1, HARVEST_M + 1))
        fetch_start = year - 1
    else:
        months = list(range(PLANT_M, HARVEST_M + 1))
        fetch_start = year
    
    try:
        data = get_power_data(lat, lon, fetch_start, year,
                              params=[T2M_MAX, T2M_MIN, PRECIP, SOLAR_PARAM, SOIL_M1])
    except Exception:
        return None
    
    total_gdd = total_precip = 0.0
    solar_sum = soil_sum = 0.0
    data_months = 0
    
    for m in months:
        for k in [f"{year - 1}{str(m).zfill(2)}", f"{year}{str(m).zfill(2)}"]:
            tmax = data.get(T2M_MAX, {}).get(k)
            tmin = data.get(T2M_MIN, {}).get(k)
            precip_mm = data.get(PRECIP, {}).get(k)
            solar = data.get(SOLAR_PARAM, {}).get(k)
            soil = data.get(SOIL_M1, {}).get(k)
            if tmax is not None:
                break
        
        if tmax is not None and tmin is not None:
            days = DAYS_IN_MONTH[m]
            daily_gdd = max(0, (tmax + tmin) / 2 - GDD_BASE)
            total_gdd += daily_gdd * days
        
        if precip_mm is not None:
            total_precip += precip_mm * DAYS_IN_MONTH[m]
        if solar is not None:
            solar_sum += solar
        if soil is not None:
            soil_sum += soil
        data_months += 1
    
    if data_months == 0 or total_gdd == 0:
        return None
    
    return {
        "region": region_code,
        "year": year,
        "gdd": round(total_gdd, 1),
        "precip_mm": round(total_precip, 1),
        "solar_kwh": round(solar_sum / data_months, 2),
        "soil_moisture": round(soil_sum / data_months, 3),
        "plant_month": PLANT_M,
        "harvest_month": HARVEST_M,
    }


# ── MAIN ──
os.makedirs(CACHE_DIR, exist_ok=True)
crop = get_crop("wheat")
plant_m, harvest_m = crop.planting_month, crop.harvest_month

# Bestimme zu berechnende Jahre (2000–2024)
current_year = date.today().year
years = list(range(2000, current_year))  # Alle abgeschlossenen Jahre

# Sammle alle Tasks
tasks = []
for code, r in REGIONS.items():
    if r.country not in ['AT', 'BG', 'CZ', 'DE', 'DK', 'ES', 'FR', 'HU', 'IT', 'PL', 'RO']:
        continue  # Nur Länder mit Eurostat-Daten
    for year in years:
        cache_path = os.path.join(CACHE_DIR, f"{code}_{year}.json")
        if os.path.exists(cache_path):
            continue  # Bereits gecached
        tasks.append((code, r.latitude, r.longitude, year, cache_path))

print(f"🏗️  Feature Cache Builder")
print(f"   Regionen: {len([c for c in set(t[0] for t in tasks)])}")
print(f"   Fehlende Cache-Einträge: {len(tasks)}")
print(f"   Parallele Threads: {MAX_WORKERS}")

if not tasks:
    print("   ✅ Bereits vollständig!")
    sys.exit(0)

# Baue Cache parallel
done = 0
errors = 0
start = time.time()

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {
        executor.submit(get_features_for_region_year, code, lat, lon, year): (code, year, path)
        for code, lat, lon, year, path in tasks
    }
    
    for future in as_completed(futures):
        code, year, path = futures[future]
        result = future.result()
        
        if result:
            with open(path, 'w') as f:
                json.dump(result, f)
            done += 1
        else:
            errors += 1
        
        if (done + errors) % 50 == 0:
            elapsed = time.time() - start
            rate = (done + errors) / elapsed if elapsed > 0 else 0
            print(f"   [{done+errors}/{len(tasks)}] ✅ {done} ❌ {errors} — {rate:.1f}/s")

elapsed = time.time() - start
print(f"\n{'='*50}")
print(f"✅ CACHE BUILD FINISHED")
print(f"   Neu gecached: {done}")
print(f"   Fehlgeschlagen: {errors}")
print(f"   Dauer: {elapsed:.0f}s ({done/elapsed:.1f}/s)")
print(f"   Cache: {CACHE_DIR}/")
