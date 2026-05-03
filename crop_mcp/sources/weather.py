"""
Open-Meteo weather data connector.
Free API, no key required. Fetches forecast and historical data.
"""

import json
import time
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import urlopen, Request

# ─────────────────────────────────────────────────────────────
# API endpoints
# ─────────────────────────────────────────────────────────────

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Parameters we always request
DAILY_PARAMS = "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max"
CURRENT_PARAMS = "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m"

# Cache: Open-Meteo is rate-limited, cache aggressively
_cache: Dict[str, Tuple[float, Any]] = {}
CACHE_TTL_FORECAST = 900        # 15 min for forecast
CACHE_TTL_HISTORICAL = 86400    # 24h for historical data


def _cached_get(url: str, ttl: int) -> Any:
    """GET with caching + exponential backoff for 429 errors."""
    now = time.time()
    if url in _cache and (now - _cache[url][0]) < ttl:
        return _cache[url][1]

    retries = 0
    max_retries = 5
    sleep_time = 2  # start with 2s

    while retries < max_retries:
        try:
            req = Request(url, headers={"User-Agent": "crop-mcp/1.0 (research)"})
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            _cache[url] = (now, data)
            return data
        except Exception as e:
            status = getattr(e, 'code', 0) if hasattr(e, 'code') else 0
            if status == 429:
                retries += 1
                wait = sleep_time ** retries  # 2, 4, 8, 16, 32s
                print(f"  [429] Rate limited — waiting {wait}s (retry {retries}/{max_retries})", file=__import__('sys').stderr)
                time.sleep(wait)
            elif status == 503 or status == 502:
                retries += 1
                wait = sleep_time ** retries
                print(f"  [{status}] Server error — waiting {wait}s", file=__import__('sys').stderr)
                time.sleep(wait)
            else:
                raise  # Don't retry other errors

    raise Exception(f"Open-Meteo rate limited after {max_retries} retries: {url[:60]}...")


# ─────────────────────────────────────────────────────────────
# GDD (Growing Degree Days) calculation
# ─────────────────────────────────────────────────────────────

def calc_gdd(t_max: float, t_min: float, base_temp: float) -> float:
    """
    Calculate Growing Degree Days for a single day.
    GDD = ((Tmax + Tmin) / 2) - Tbase
    If result < 0, GDD = 0.
    """
    avg = (t_max + t_min) / 2.0
    gdd = avg - base_temp
    return max(0.0, gdd)


# ─────────────────────────────────────────────────────────────
# Forecast (16 days)
# ─────────────────────────────────────────────────────────────

def get_forecast(
    latitude: float,
    longitude: float,
    altitude: float = 0.0,
) -> Dict[str, Any]:
    """
    Fetch 16-day weather forecast for a location.
    Returns structured data with daily temps, precipitation, wind.
    """
    url = (
        f"{FORECAST_URL}?latitude={latitude}&longitude={longitude}"
        f"&daily={DAILY_PARAMS}"
        f"&current={CURRENT_PARAMS}"
        f"&timezone=Europe/Berlin"
        f"&forecast_days=16"
    )
    data = _cached_get(url, CACHE_TTL_FORECAST)

    daily = data.get("daily", {})
    current = data.get("current", {})

    days = []
    times = daily.get("time", [])
    t_maxs = daily.get("temperature_2m_max", [])
    t_mins = daily.get("temperature_2m_min", [])
    precips = daily.get("precipitation_sum", [])
    winds = daily.get("wind_speed_10m_max", [])

    for i in range(len(times)):
        days.append({
            "date": times[i],
            "t_max": t_maxs[i] if i < len(t_maxs) else None,
            "t_min": t_mins[i] if i < len(t_mins) else None,
            "precipitation_mm": precips[i] if i < len(precips) else None,
            "wind_max_kmh": winds[i] if i < len(winds) else None,
        })

    return {
        "location": {"lat": latitude, "lon": longitude},
        "current": {
            "temperature": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "precipitation": current.get("precipitation"),
            "wind_speed": current.get("wind_speed_10m"),
        },
        "forecast": days,
        "days_forecast": len(days),
        "generated_at": data.get("generationtime_ms"),
    }


# ─────────────────────────────────────────────────────────────
# Historical weather data
# ─────────────────────────────────────────────────────────────

def get_historical(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    """
    Fetch historical weather for a date range.
    Date format: YYYY-MM-DD.
    """
    url = (
        f"{ARCHIVE_URL}?latitude={latitude}&longitude={longitude}"
        f"&start_date={start_date}&end_date={end_date}"
        f"&daily={DAILY_PARAMS}"
        f"&timezone=Europe/Berlin"
    )
    data = _cached_get(url, CACHE_TTL_HISTORICAL)

    daily = data.get("daily", {})
    days = []
    for i in range(len(daily.get("time", []))):
        days.append({
            "date": daily["time"][i],
            "t_max": daily.get("temperature_2m_max", [None])[i],
            "t_min": daily.get("temperature_2m_min", [None])[i],
            "precipitation_mm": daily.get("precipitation_sum", [None])[i],
            "wind_max_kmh": daily.get("wind_speed_10m_max", [None])[i],
        })

    return {
        "location": {"lat": latitude, "lon": longitude},
        "period": {"start": start_date, "end": end_date},
        "days": days,
        "total_days": len(days),
    }


# ─────────────────────────────────────────────────────────────
# Crop-specific weather analysis
# ─────────────────────────────────────────────────────────────

def analyze_growing_season(
    latitude: float,
    longitude: float,
    base_temp: float,
    season_start: str,        # "YYYY-MM-DD" start of growing season
    season_end: str,          # "YYYY-MM-DD" end of growing season
) -> Dict[str, Any]:
    """
    Analyze a growing season: cumulative GDD, precipitation, extremes.
    Fetches historical data for the full period plus 16-day forecast.
    """
    # Get historical data for the season so far
    today = date.today()
    actual_end = min(date.fromisoformat(season_end), today).isoformat()
    historical = get_historical(latitude, longitude, season_start, actual_end)

    # Get forecast for next 16 days
    forecast = get_forecast(latitude, longitude)

    total_gdd = 0.0
    total_precip = 0.0
    hot_days = 0       # days > 30°C
    frost_days = 0     # days < 0°C
    rainy_days = 0     # days > 5mm

    for day in historical["days"]:
        if day["t_max"] is not None and day["t_min"] is not None:
            gdd = calc_gdd(day["t_max"], day["t_min"], base_temp)
            total_gdd += gdd
        if day["t_max"] is not None and day["t_max"] > 30:
            hot_days += 1
        if day["t_min"] is not None and day["t_min"] < 0:
            frost_days += 1
        if day["precipitation_mm"] is not None and day["precipitation_mm"] > 5:
            rainy_days += 1
            total_precip += day["precipitation_mm"]
        elif day["precipitation_mm"] is not None:
            total_precip += day["precipitation_mm"]

    # Forecast GDD
    forecast_gdd = 0.0
    forecast_precip = 0.0
    for day in forecast.get("forecast", []):
        if day["t_max"] is not None and day["t_min"] is not None:
            gdd = calc_gdd(day["t_max"], day["t_min"], base_temp)
            forecast_gdd += gdd
        if day["precipitation_mm"] is not None:
            forecast_precip += day["precipitation_mm"]

    return {
        "season": {"start": season_start, "end": season_end},
        "elapsed_days": historical["total_days"],
        "gdd": {
            "accumulated": round(total_gdd, 1),
            "forecast_16d": round(forecast_gdd, 1),
        },
        "precipitation_mm": {
            "accumulated": round(total_precip, 1),
            "forecast_16d": round(forecast_precip, 1),
        },
        "extremes": {
            "hot_days_gt_30c": hot_days,
            "frost_days_lt_0c": frost_days,
            "rainy_days_gt_5mm": rainy_days,
        },
    }


def drought_index(
    precipitation_mm: float,
    t_max_avg: float,
) -> float:
    """
    Simple drought index (0-1).
    0 = no drought, 1 = extreme drought.
    Based on precipitation relative to temperature-driven evapotranspiration.
    """
    if precipitation_mm <= 0:
        return 1.0
    # Simple estimate: ET ~= 0.7 * Tmax (in mm/month equivalent)
    et_estimate = max(0.7 * t_max_avg, 1.0)
    ratio = precipitation_mm / et_estimate
    if ratio >= 1.5:
        return 0.0
    if ratio <= 0.2:
        return 1.0
    return round(1.0 - (ratio - 0.2) / 1.3, 2)
