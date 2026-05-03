"""
NASA POWER: Solar radiation, soil moisture, GDD, and precipitation data.
Free REST API, no key required. Monthly climate data for agriculture.
API: https://power.larc.nasa.gov/api/
"""

import json, time
from typing import Any, Dict, List, Tuple, Optional
from urllib.request import Request, urlopen

# POWER monthly API for GDD + precipitation (rate-limit-free fallback)
POWER_MONTHLY_PARAMS = ["T2M_MAX", "T2M_MIN", "PRECTOTCORR"]
DAYS_IN_MONTH = {1:31,2:28,3:31,4:30,5:31,6:30,7:31,8:31,9:30,10:31,11:30,12:31}

_cache: Dict[str, Tuple[float, Any]] = {}
CACHE_TTL = 86400

MONTHLY_API = "https://power.larc.nasa.gov/api/temporal/monthly/point"
SOLAR_PARAM = "ALLSKY_SFC_SW_DWN"   # kWh/m²/day
SOIL_M1 = "GWETPROF"                # Root zone (0-1)
T2M_MAX = "T2M_MAX"                  # °C
T2M_MIN = "T2M_MIN"                  # °C
PRECIP = "PRECTOTCORR"               # mm/day


def _is_valid(val) -> bool:
    return val is not None and (not isinstance(val, (int, float)) or val > -100)


def _fetch_params(url: str) -> Dict[str, Any]:
    now = time.time()
    if url in _cache and (now - _cache[url][0]) < CACHE_TTL:
        return _cache[url][1]
    try:
        req = Request(url, headers={"User-Agent": "crop-mcp/2.0"})
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        result = data.get("properties", {}).get("parameter", {})
        _cache[url] = (now, result)
        return result
    except Exception:
        return {}


def get_power_data(lat: float, lon: float, start: int, end: int,
                   params: List[str] = None) -> Dict[str, Dict[str, float]]:
    """Fetch monthly POWER data. Returns {param: {YYYYMM: value}}."""
    if params is None:
        params = [SOLAR_PARAM, SOIL_M1]
    url = (f"{MONTHLY_API}?parameters={','.join(params)}&community=AG"
           f"&latitude={lat}&longitude={lon}&start={start}&end={end}&format=JSON")
    raw = _fetch_params(url)
    result = {}
    for p in params:
        vals = raw.get(p, {})
        result[p] = {k: v for k, v in vals.items() if len(k) == 6 and _is_valid(v)}
    return result


def season_solar_and_soil(lat: float, lon: float, year: int,
                          plant_m: int, harvest_m: int) -> Dict:
    """
    Analyze solar radiation and soil moisture for a growing season.
    Returns current averages + anomaly vs 30-year climate normal (1994-2023).
    Handles POWER data lag (only compares months that have data, uses dynamic avail_year).
    """
    # Build season month keys
    if plant_m > harvest_m:
        season_keys = [f"{year-1}{str(m).zfill(2)}" for m in range(plant_m, 13)] + \
                      [f"{year}{str(m).zfill(2)}" for m in range(1, harvest_m + 1)]
        fetch_start = year - 1
    else:
        season_keys = [f"{year}{str(m).zfill(2)}" for m in range(plant_m, harvest_m + 1)]
        fetch_start = year

    # POWER typically lags ~6 months; cap so we don't query into the future
    # Use current year minus 1 as safe max (POWER data for current year may be incomplete)
    from datetime import date as _dt
    _cur = _dt.today().year
    avail_year = min(year, max(2025, _cur - 1))
    current = get_power_data(lat, lon, fetch_start, avail_year,
                             params=[SOLAR_PARAM, SOIL_M1])

    # Only include months with actual data
    curr_solar = []
    curr_soil = []
    data_months = set()
    for k in season_keys:
        s = current.get(SOLAR_PARAM, {}).get(k)
        g = current.get(SOIL_M1, {}).get(k)
        if s is not None:
            curr_solar.append(s)
            data_months.add(int(k[4:6]))
        if g is not None:
            curr_soil.append(g)

    # 30-year climate normal (all months for full season + same months comparison)
    clim = get_power_data(lat, lon, 1994, 2023, params=[SOLAR_PARAM, SOIL_M1])

    clim_solar_by_month = {m: [] for m in range(1, 13)}
    clim_soil_by_month = {m: [] for m in range(1, 13)}
    for key, val in clim.get(SOLAR_PARAM, {}).items():
        if len(key) == 6:
            m = int(key[4:6])
            if 1 <= m <= 12:
                clim_solar_by_month[m].append(val)
    for key, val in clim.get(SOIL_M1, {}).items():
        if len(key) == 6:
            m = int(key[4:6])
            if 1 <= m <= 12:
                clim_soil_by_month[m].append(val)

    # Full season months
    season_months = (list(range(plant_m, 13)) + list(range(1, harvest_m + 1))
                     if plant_m > harvest_m else list(range(plant_m, harvest_m + 1)))

    def avg(vals):
        return sum(vals) / len(vals) if vals else 0.0

    # Current: average of available months
    curr_solar_avg = avg(curr_solar)
    curr_soil_avg = avg(curr_soil)

    # Climate: full season normal (always available)
    clim_solar_avg = avg([avg(clim_solar_by_month[m]) for m in season_months
                          if clim_solar_by_month[m]])
    clim_soil_avg = avg([avg(clim_soil_by_month[m]) for m in season_months
                         if clim_soil_by_month[m]])

    # Same-month climate (for fair anomaly: current months vs same months' normal)
    clim_solar_same = avg([avg(clim_solar_by_month[m]) for m in data_months
                           if clim_solar_by_month[m]]) if data_months else clim_solar_avg
    clim_soil_same = avg([avg(clim_soil_by_month[m]) for m in data_months
                          if clim_soil_by_month[m]]) if data_months else clim_soil_avg

    def anom(cur, clim_ref):
        return ((cur - clim_ref) / clim_ref * 100) if clim_ref else 0.0

    return {
        "solar_radiation_kwh_m2_day": {
            "current": round(curr_solar_avg, 2),
            "30yr_full_season_normal": round(clim_solar_avg, 2),
            "30yr_same_months_normal": round(clim_solar_same, 2),
            "anomaly_vs_same_months_pct": round(anom(curr_solar_avg, clim_solar_same), 1),
        },
        "soil_moisture_root_zone": {
            "current": round(curr_soil_avg, 3),
            "30yr_full_season_normal": round(clim_soil_avg, 3),
            "30yr_same_months_normal": round(clim_soil_same, 3),
            "anomaly_vs_same_months_pct": round(anom(curr_soil_avg, clim_soil_same), 1),
        },
        "data_months_available": sorted(data_months),
    }


def season_gdd_precip_power(lat: float, lon: float, year: int,
                            plant_m: int, harvest_m: int,
                            gdd_base: float = 0.0,
                            cut_off_month: int = None, cut_off_day: int = None) -> Dict:
    """
    Compute GDD + precipitation from NASA POWER monthly data.
    Rate-limit-free fallback when Open-Meteo is unavailable.

    Uses monthly T2M_MAX/T2M_MIN for GDD and PRECTOTCORR for precipitation.
    GDD = max(0, (tmax_avg + tmin_avg) / 2 - gdd_base) * days_in_month
    Precipitation = PRECTOTCORR (mm/day) * days_in_month

    When cut_off_month/cut_off_day are provided, truncates the season at that date
    (for partial-season comparison e.g. May 2).
    """
    if plant_m > harvest_m:
        season_months = list(range(plant_m, 13)) + list(range(1, harvest_m + 1))
        fetch_start = year - 1
        fetch_end = year
    else:
        season_months = list(range(plant_m, harvest_m + 1))
        fetch_start = year
        fetch_end = year

    # Apply cutoff for partial season
    if cut_off_month is not None:
        cut_months = []
        for m in season_months:
            if plant_m > harvest_m:
                # Previous-year months (m >= plant_m) are entirely in the past — always include
                if m >= plant_m:
                    cut_months.append(m)
                # Current-year months (m < plant_m): apply cutoff
                elif m < cut_off_month or (m == cut_off_month and cut_off_day and 1 <= cut_off_day):
                    cut_months.append(m)
            else:
                # Same calendar year: apply cutoff
                if m < cut_off_month or (m == cut_off_month and cut_off_day and 1 <= cut_off_day):
                    cut_months.append(m)
        season_months = cut_months

    if not season_months:
        return {"gdd_accumulated": 0.0, "precip_mm_accumulated": 0.0, "months_count": 0, "source": "power"}

    # Build month keys
    if plant_m > harvest_m:
        season_keys = []
        for m in season_months:
            if m >= plant_m:
                season_keys.append(f"{year-1}{str(m).zfill(2)}")
            else:
                season_keys.append(f"{year}{str(m).zfill(2)}")
    else:
        season_keys = [f"{year}{str(m).zfill(2)}" for m in season_months]

    from datetime import date as _dt
    _cur = _dt.today().year
    avail_end = min(fetch_end, max(2025, _cur - 1))

    data = get_power_data(lat, lon, fetch_start, avail_end,
                          params=[T2M_MAX, T2M_MIN, PRECIP])

    total_gdd = 0.0
    total_precip = 0.0
    months_used = 0

    for i, m in enumerate(season_months):
        key = season_keys[i]
        tmax = data.get(T2M_MAX, {}).get(key)
        tmin = data.get(T2M_MIN, {}).get(key)
        precip_mm_day = data.get(PRECIP, {}).get(key)

        if tmax is not None and tmin is not None and precip_mm_day is not None:
            days = DAYS_IN_MONTH.get(m, 30)
            daily_gdd = max(0.0, (tmax + tmin) / 2.0 - gdd_base)
            total_gdd += daily_gdd * days
            total_precip += precip_mm_day * days
            months_used += 1

    return {
        "gdd_accumulated": round(total_gdd, 1),
        "precip_mm_accumulated": round(total_precip, 1),
        "months_count": months_used,
        "source": "power",
    }


if __name__ == "__main__":
    import json
    r = season_solar_and_soil(51.5, 11.5, 2026, 10, 7)
    print(json.dumps(r, indent=2, ensure_ascii=False))
    print("\n✅ POWER connector v2")
