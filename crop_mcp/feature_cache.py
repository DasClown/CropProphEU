#!/usr/bin/env python3
"""
Feature Cache für crop-mcp Server.
Ermöglicht sub-second Tool-Calls für historische Jahre.

Cache-Struktur: feature_cache/{region}_{year}.json
Nicht-vorhandene Einträge werden live berechnet und gecached.
"""
import json, os, sys
from datetime import date

# Pfad relativ zum Skript-Verzeichnis
CACHE_DIR = "/home/j/crop-mcp/feature_cache"

# POWER-Konstanten (lazy import)
T2M_MAX = T2M_MIN = PRECIP = SOLAR_PARAM = SOIL_M1 = None
DAYS_IN_MONTH = {1:31,2:28,3:31,4:30,5:31,6:30,7:31,8:31,9:30,10:31,11:30,12:31}

def _ensure_power():
    """Lazy-Import POWER-Konstanten."""
    global T2M_MAX, T2M_MIN, PRECIP, SOLAR_PARAM, SOIL_M1
    if T2M_MAX is None:
        from .sources.power import T2M_MAX as _T, T2M_MIN as _N, PRECIP as _P, SOLAR_PARAM as _S, SOIL_M1 as _G
        T2M_MAX, T2M_MIN, PRECIP, SOLAR_PARAM, SOIL_M1 = _T, _N, _P, _S, _G


def get(region_code: str, year: int, lat: float, lon: float,
        plant_month: int = 10, harvest_month: int = 7, gdd_base: float = 0.0) -> dict | None:
    """
    Hole Features für eine Region×Jahr-Kombination.
    - Wenn im Cache: sofort zurück
    - Wenn nicht: live berechnen (NASA POWER), cachen, zurück
    - Gibt None bei Fehler
    
    Für die AKTUELLE Saison (year == dieses Jahr): immer live berechnen,
      da sich Wetterdaten ändern.
    """
    current_year = date.today().year
    is_current_season = (year == current_year)
    
    cache_path = os.path.join(CACHE_DIR, f'{region_code}_{year}.json')
    
    # Cache lesen (nur für abgeschlossene Saisons)
    if not is_current_season and os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                return json.load(f)
        except Exception:
            pass  # Kaputter Cache-Eintrag → neu berechnen
    
    # Live berechnen via NASA POWER
    return _compute_and_cache(region_code, year, lat, lon,
                              plant_month, harvest_month, gdd_base,
                              cache_path if not is_current_season else None)


def _compute_and_cache(region_code, year, lat, lon,
                       plant_m, harvest_m, gdd_base, cache_path):
    """Berechne Features live und speichere im Cache (für historische Jahre)."""
    _ensure_power()
    
    if plant_m > harvest_m:
        months = list(range(plant_m, 13)) + list(range(1, harvest_m + 1))
        fetch_start = year - 1
    else:
        months = list(range(plant_m, harvest_m + 1))
        fetch_start = year
    
    try:
        from .sources.power import get_power_data
        data = get_power_data(lat, lon, fetch_start, year,
                              params=[T2M_MAX, T2M_MIN, PRECIP, SOLAR_PARAM, SOIL_M1])
    except Exception:
        return None
    
    total_gdd = total_precip = 0.0
    solar_sum = soil_sum = 0.0
    data_months = 0
    
    for m in months:
        tmax = tmin = precip_mm = solar = soil = None
        for k in [f"{year - 1}{str(m).zfill(2)}", f"{year}{str(m).zfill(2)}"]:
            if k in data.get(T2M_MAX, {}):
                tmax = data[T2M_MAX][k]
                tmin = data[T2M_MIN].get(k)
                precip_mm = data[PRECIP].get(k)
                solar = data[SOLAR_PARAM].get(k)
                soil = data[SOIL_M1].get(k)
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
        return None
    
    result = {
        "region": region_code,
        "year": year,
        "gdd": round(total_gdd, 1),
        "precip_mm": round(total_precip, 1),
        "solar_kwh": round(solar_sum / data_months, 2),
        "soil_moisture": round(soil_sum / data_months, 3),
    }
    
    # Ins Cache schreiben (nur für abgeschlossene Saisons)
    if cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        try:
            with open(cache_path, 'w') as f:
                json.dump(result, f)
        except Exception:
            pass
    
    return result


def get_current_season_features(region_code: str, lat: float, lon: float,
                                 plant_month: int = 10, harvest_month: int = 7,
                                 gdd_base: float = 0.0) -> dict | None:
    """
    Berechne Features für die LAUFENDE Saison (vom letzten planting bis heute).
    Nutzt Open-Meteo für aktuelle Tagesdaten + NASA POWER für den September-Teil.
    """
    today = date.today()
    current_year = today.year
    
    # Berechne Saison-Start (z.B. Oktober letztes Jahr für Winterweizen)
    if plant_month > harvest_month:
        season_start = date(current_year - 1, plant_month, 1)
    else:
        season_start = date(current_year, plant_month, 1)
    
    try:
        from .sources.weather import get_historical, calc_gdd
        
        # Open-Meteo für tagesgenaue Daten (vom Saison-Start bis heute)
        hist = get_historical(lat, lon, season_start.isoformat(), today.isoformat())
        
        if not hist or not hist.get("days"):
            return None
        
        gdd = precip = 0.0
        solar = soil = 5.0  # Standardwerte für laufende Saison
        
        for day in hist.get("days", []):
            if day["t_max"] is not None and day["t_min"] is not None:
                gdd += calc_gdd(day["t_max"], day["t_min"], gdd_base)
            if day["precipitation_mm"] is not None:
                precip += day["precipitation_mm"]
        
        # POWER für Solar + Bodenfeuchte (monatliche Daten, falls verfügbar)
        try:
            pf = get(current_year, lat, lon, plant_month, harvest_month, gdd_base)
            if pf:
                solar = pf["solar_kwh"]
                soil = pf["soil_moisture"]
        except Exception:
            pass
        
        return {
            "region": region_code,
            "year": current_year,
            "gdd": round(gdd, 1),
            "precip_mm": round(precip, 1),
            "solar_kwh": round(solar, 2),
            "soil_moisture": round(soil, 3),
            "days_observed": len(hist.get("days", [])),
            "season_start": season_start.isoformat(),
            "data_source": "open-meteo_daily",
        }
    except Exception:
        return None


if __name__ == '__main__':
    # Test
    import sys; sys.path.insert(0, os.path.dirname(__file__))
    
    # Test historischer Cache (DE, 2020)
    r = get('DEE0', 2020, 51.5, 11.5)
    if r:
        print(f'✅ Cache DE 2020: GDD={r["gdd"]}, Precip={r["precip_mm"]}mm')
    else:
        print('❌ Cache DE 2020 fehlgeschlagen')
    
    # Test aktuelle Saison
    r = get_current_season_features('DEE0', 51.5, 11.5)
    if r:
        print(f'✅ Aktuelle Saison: GDD={r["gdd"]}, Precip={r["precip_mm"]}mm ({r.get("days_observed", 0)} Tage)')
    else:
        print('❌ Aktuelle Saison fehlgeschlagen')
