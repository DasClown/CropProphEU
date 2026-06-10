#!/usr/bin/env python3
"""
Frostalarme — Daily frost alerts for top EU crop regions.
Queries Open-Meteo API for daily minimum temperatures.
Thresholds: < 1°C = Warning, < -2°C = Alarm.
Only produces output if frost risk is detected (silent otherwise).
"""

import json
import urllib.request
import urllib.error
import sys
from datetime import datetime

# ── Region definitions (NUTS code: (lat, lon, name)) ──────────────────────
REGIONS = [
    ("DEE0", 51.9, 11.6, "Sachsen-Anhalt"),
    ("DEF0", 54.2, 10.0, "Schleswig-Holstein"),
    ("DE91", 52.8, 8.0,  "Weser-Ems"),
    ("DE26", 49.9, 10.1, "Unterfranken"),
    ("FRF2", 49.8, 2.9,  "Picardie"),
    ("FRB0", 47.0, 1.7,  "Centre-Val de Loire"),
    ("PL22", 50.3, 19.0, "Śląskie"),
    ("PL71", 51.8, 19.5, "Łódzkie"),
    ("HU21", 46.4, 17.8, "Somogy"),
    ("HU33", 46.7, 20.5, "Békés"),
    ("RO31", 44.9, 26.0, "Prahova + Ialomița"),
    ("RO32", 44.3, 28.0, "Constanța"),
    ("ES42", 41.7, -4.7, "Castilla y León"),
    ("ES61", 37.4, -5.9, "Andalucía"),
    ("ITC4", 45.5, 9.5,  "Lombardia"),
    ("ITH4", 45.7, 12.2, "Veneto"),
    ("UKH1", 52.5, 0.3,  "East Anglia"),
    ("UKH2", 52.8, -0.5, "Lincolnshire"),
]

API_URL = "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_min&forecast_days=3&timezone=auto"
TIMEOUT = 15  # seconds


def fetch_min_temps(lat: float, lon: float):
    """Fetch daily minimum temperatures for a location. Returns list of (date, temp) or None."""
    url = API_URL.format(lat=lat, lon=lon)
    req = urllib.request.Request(url, headers={"User-Agent": "crop-mcp-frost-alert/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError) as e:
        print(f"  ⚠ Error fetching {lat},{lon}: {e}", file=sys.stderr)
        return None

    daily = data.get("daily")
    if not daily:
        return None

    dates = daily.get("time", [])
    temps = daily.get("temperature_2m_min", [])
    if not dates or not temps:
        return None

    return list(zip(dates, temps))


def classify(temp: float) -> tuple[str, str]:
    """Returns (icon, label) for a given temperature."""
    if temp < -2.0:
        return ("🔴", "ALARM")
    elif temp < 1.0:
        return ("🟡", "Warning")
    return ("", "")


def main():
    today = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    header = f"❄️ Frostalarm-Check — {today}"
    separator = "─" * len(header)

    # Collect all risk entries
    risk_entries = []

    for code, lat, lon, name in REGIONS:
        # print(f"  Checking {code} ({name})…", file=sys.stderr)
        result = fetch_min_temps(lat, lon)
        if result is None:
            continue

        for date_str, temp in result:
            if temp is None:
                continue
            temp_f = float(temp)
            icon, label = classify(temp_f)
            if label:
                risk_entries.append((code, name, date_str, temp_f, icon, label))

    # Output — only if there's frost risk
    if not risk_entries:
        # Silent exit — no frost detected
        return

    lines = [header, separator]
    # Group by region for cleaner output
    region_groups: dict[str, list] = {}
    for code, name, date_str, temp_f, icon, label in risk_entries:
        key = f"{code} ({name})"
        region_groups.setdefault(key, []).append((date_str, temp_f, icon, label))

    for region_key in sorted(region_groups.keys()):
        entries = sorted(region_groups[region_key], key=lambda x: x[0])
        dates_str = ", ".join(f"{d}: {icon} {temp:.1f}°C ({label})" for d, temp, icon, label in entries)
        lines.append(f"  {region_key}")
        lines.append(f"    {dates_str}")

    lines.append("")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
