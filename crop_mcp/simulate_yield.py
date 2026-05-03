#!/usr/bin/env python3
"""
V3b: Analog-Year Simulator + Yield Prediction

Instead of ML on limited data, uses the full 30-year historical record to find
the most similar historical years and projects their final yields.

Approach:
1. Build a 30-year climate library for each region
2. For a current forecast, find most analogous historical years
3. Show yield range based on analog outcomes
4. Works at ANY point in the season (Mar 1, May 1, Jun 1)
"""
import json, math
from datetime import date

from .core.regions import get_region, get_crop
from .sources.weather import get_historical, calc_gdd
from .sources.power import season_solar_and_soil

# Eurostat DE wheat yields
YIELDS = {
    2010: 7.21, 2011: 7.01, 2012: 7.33, 2013: 8.00,
    2014: 8.63, 2015: 8.09, 2016: 7.64, 2017: 7.64,
    2018: 6.67, 2019: 7.40, 2020: 7.82, 2021: 7.30,
    2022: 7.58, 2023: 7.43, 2024: 7.08, 2000: 7.28,
    2001: 7.88, 2002: 7.03, 2003: 6.59, 2004: 8.22,
    2005: 7.54, 2006: 6.89, 2007: 6.99, 2008: 7.83,
    2009: 7.61,
}

DE_REGIONS = {"DEE0": "Sachsen-Anhalt", "DEF0": "Schleswig-Holstein",
               "DEG0": "Thüringen", "DE91": "Niedersachsen"}

def compute_features(region_code, crop_name, year, ref_month, ref_day):
    """Compute weather + POWER features for a partial season up to ref_date."""
    try:
        region = get_region(region_code)
        crop = get_crop(crop_name)
    except KeyError:
        return None
    
    ref_date = date(year, ref_month, ref_day)
    
    # Season dates for winter wheat
    if crop.planting_month > crop.harvest_month:
        season_start = date(year - 1, crop.planting_month, 1)
        season_end = date(year, crop.harvest_month, 28)
    else:
        season_start = date(year, crop.planting_month, 1)
        season_end = date(year, crop.harvest_month, 28)
    
    if ref_date < season_start:
        return None
    
    actual_end = min(ref_date, season_end)
    days_elapsed = (actual_end - season_start).days
    
    # Weather
    try:
        hist = get_historical(region.latitude, region.longitude,
                              season_start.isoformat(), actual_end.isoformat())
    except Exception:
        return None
    
    gdd = 0.0
    precip = 0.0
    for day in hist.get("days", []):
        if day["t_max"] is not None and day["t_min"] is not None:
            gdd += calc_gdd(day["t_max"], day["t_min"], crop.gdd_base)
        if day["precipitation_mm"] is not None:
            precip += day["precipitation_mm"]
    
    # POWER
    power = {}
    try:
        power = season_solar_and_soil(region.latitude, region.longitude,
                                      year, crop.planting_month, crop.harvest_month)
    except Exception:
        pass
    
    solar = power.get("solar_radiation_kwh_m2_day", {}).get("current", 0) or 0
    soil = power.get("soil_moisture_root_zone", {}).get("current", 0) or 0
    
    return {
        "gdd": round(gdd, 1),
        "precip_mm": round(precip, 1),
        "solar_kwh": round(solar, 2),
        "soil_moisture": round(soil, 3),
        "days_elapsed": days_elapsed,
    }


def find_analogs(region_code, crop_name, current_year, ref_month, ref_day, n_analogs=5):
    """
    Find most similar historical years for a given reference date.
    Uses Euclidean distance on normalized features (GDD, precip, solar, soil).
    """
    current = compute_features(region_code, crop_name, current_year, ref_month, ref_day)
    if not current:
        return {"error": "Could not compute current features"}, []
    
    historical = []
    for year in sorted(YIELDS.keys()):
        if year == current_year:
            continue
        feat = compute_features(region_code, crop_name, year, ref_month, ref_day)
        if feat:
            feat["year"] = year
            feat["yield_t_ha"] = YIELDS[year]
            historical.append(feat)
    
    if not historical:
        return current, []
    
    # Normalize features and compute distance
    norm_keys = ["gdd", "precip_mm", "solar_kwh", "soil_moisture"]
    means = {k: sum(h[k] for h in historical) / len(historical) for k in norm_keys}
    stds = {k: math.sqrt(sum((h[k] - means[k])**2 for h in historical) / len(historical)) or 1 for k in norm_keys}
    
    # Current normalized vector
    curr_norm = [(current[k] - means[k]) / stds[k] for k in norm_keys]
    
    for h in historical:
        h_vec = [(h[k] - means[k]) / stds[k] for k in norm_keys]
        h["distance"] = math.sqrt(sum((a-b)**2 for a, b in zip(curr_norm, h_vec)))
    
    # Sort by distance
    historical.sort(key=lambda x: x["distance"])
    top_n = historical[:n_analogs]
    
    return current, top_n, means, stds


def simulate_yield(region_code, crop_name, current_year, ref_month, ref_day):
    """Predict yield range based on analog years."""
    current, analogs = find_analogs(region_code, crop_name, current_year, ref_month, ref_day, n_analogs=5)[:2]
    
    if not analogs:
        return {"error": "No analog years found"}
    
    yields = [a["yield_t_ha"] for a in analogs]
    
    result = {
        "region": region_code,
        "crop": crop_name,
        "reference_date": f"{current_year}-{ref_month:02d}-{ref_day:02d}",
        "current_features": current,
        "predicted_yield_t_ha": {
            "mean": round(sum(yields) / len(yields), 2),
            "min": round(min(yields), 2),
            "max": round(max(yields), 2),
            "std": round(math.sqrt(sum((y - sum(yields)/len(yields))**2 for y in yields) / len(yields)), 2),
        },
        "analogs": [{"year": a["year"], "yield_t_ha": a["yield_t_ha"],
                      "gdd": a["gdd"], "precip_mm": a["precip_mm"],
                      "solar_kwh": a["solar_kwh"], "soil_moisture": a["soil_moisture"],
                      "similarity_score": round(1 - a["distance"]/5, 3)} for a in analogs],
        "data_quality": {
            "analog_years_used": len(analogs),
            "days_into_season": current["days_elapsed"],
        }
    }
    
    # Confidence based on season progress
    sp = current["days_elapsed"] / 300.0  # ~300 day season
    if sp < 0.3:
        result["confidence"] = "low"
    elif sp < 0.6:
        result["confidence"] = "medium"
    else:
        result["confidence"] = "high"
    
    return result


if __name__ == "__main__":
    import time
    
    print("="*60)
    print("V3b: Analog-Year Yield Simulation")
    print("="*60)
    
    # Test: Sachsen-Anhalt, May 1 2026
    for ref in [(5, 1, "Mai"), (3, 1, "März"), (6, 1, "Juni")]:
        month, day, name = ref
        print(f"\n📅 {name}-Prognose für Winterweizen in Sachsen-Anhalt:")
        result = simulate_yield("DEE0", "wheat", 2026, month, day)
        
        if "error" in result:
            print(f"   Fehler: {result['error']}")
            continue
        
        print(f"   Features: GDD={result['current_features']['gdd']} | "
              f"NS={result['current_features']['precip_mm']}mm | "
              f"Solar={result['current_features']['solar_kwh']} | "
              f"Bodenf.={result['current_features']['soil_moisture']}")
        print(f"   Prognose: {result['predicted_yield_t_ha']['mean']} t/ha "
              f"(Spanne {result['predicted_yield_t_ha']['min']}–{result['predicted_yield_t_ha']['max']})")
        print(f"   Konfidenz: {result['confidence']}")
        print(f"   Top-Analoge:")
        for a in result['analogs']:
            print(f"     {a['year']}: {a['yield_t_ha']} t/ha (Ähnlichkeit: {a['similarity_score']})")
        
        time.sleep(0.5)
    
    # Validation: backtest the analog method
    print("\n\n" + "="*60)
    print("BACKTEST: Analog Method vs Actual Yields")
    print("="*60)
    print(f"{'Jahr':<6} {'Aktuell':<9} {'Mai-Progn':<11} {'Jun-Progn':<11} {'Jul-Progn':<11}")
    print("-" * 52)
    
    errors_may = []
    errors_jun = []
    for year in sorted(YIELDS.keys())[5:]:  # Skip early years for analog pool
        for ref in [(5, 1), (6, 1)]:
            month, day = ref
            result = simulate_yield("DEE0", "wheat", year, month, day)
            if "error" in result:
                continue
            
            predicted = result["predicted_yield_t_ha"]["mean"]
            actual = YIELDS.get(year, 0)
            error = predicted - actual
            
            if month == 5:
                errors_may.append((year, actual, predicted, error))
            elif month == 6:
                errors_jun.append((year, actual, predicted, error))
    
    for year in sorted(YIELDS.keys())[5:]:
        actual = YIELDS.get(year, 0)
        may_p = next((p for y, a, p, e in errors_may if y == year), None)
        jun_p = next((p for y, a, p, e in errors_jun if y == year), None)
        
        may_s = f"{may_p:.2f}t" if may_p else "-"
        jun_s = f"{jun_p:.2f}t" if jun_p else "-"
        print(f"{year:<6} {actual:<9.2f} {may_s:<11} {jun_s:<11}")
    
    if errors_may:
        mae_may = sum(abs(e) for _, _, _, e in errors_may) / len(errors_may)
        mae_jun = sum(abs(e) for _, _, _, e in errors_jun) / len(errors_jun) if errors_jun else 0
        print(f"\nMAE Mai: {mae_may:.3f} t/ha ({mae_may/7.52*100:.1f}%)")
        if errors_jun:
            print(f"MAE Jun: {mae_jun:.3f} t/ha ({mae_jun/7.52*100:.1f}%)")
