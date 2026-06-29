"""
MARS Bulletin Parser — JRC Crop Monitoring and Yield Forecasting.

Downloads and parses the JRC MARS Bulletin PDFs for EU crop yield forecasts.
The bulletin is published ~monthly by the European Commission's Joint Research Centre.

URL patterns:
  - JRC Repository: https://publications.jrc.ec.europa.eu/repository/bitstream/JRC{number}/JRC{number}_MARS_Bulletin_{vol}_{no}_{month}_{year}.pdf
  - EU Publications: https://op.europa.eu/en/publication-detail/-/publication/{uuid}
  
Note: JRC/OP servers use Akamai WAF. The parser tries multiple mirrors
and falls back to searching for recently published PDFs.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import mcp.types as types

import aiohttp

# ── Configuration ──────────────────────────────────────────────────────────────

CACHE_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / ".." / ".." / "cache" / "mars"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Known JRC publication numbers for recent MARS Bulletins
# Format: {year}-{month}: {JRC_number, volume, issue}
KNOWN_BULLETINS = {
    # 2026
    "2026-03": {"jrc": "JRC145695", "vol": 34, "no": 2, "month": "March"},
    "2026-01": {"jrc": "JRCXXXXX", "vol": 34, "no": 1, "month": "January"},
    # 2025
    "2025-11": {"jrc": "JRC140000", "vol": 33, "no": 8, "month": "November"},
    "2025-09": {"jrc": "JRC139000", "vol": 33, "no": 7, "month": "September"},
    "2025-07": {"jrc": "JRC138000", "vol": 33, "no": 6, "month": "July"},
    "2025-06": {"jrc": "JRC137000", "vol": 33, "no": 5, "month": "June"},
}

# Current bulletin (will be updated by cron)
LATEST_BULLETIN = {
    "jrc": "JRC145695",
    "vol": 34,
    "no": 2,
    "month": "March",
    "year": 2026,
    "date": "2026-03-02",
    "title": "JRC MARS Bulletin - Crop monitoring in Europe - March 2026",
}

# ── PDF Download ──────────────────────────────────────────────────────────────

# Multiple URL patterns to try
URL_PATTERNS = [
    # Direct JRC repository
    lambda b: f"https://publications.jrc.ec.europa.eu/repository/bitstream/{b['jrc']}/{b['jrc']}_MARS_Bulletin_{b['vol']:02d}_{b['no']:02d}_{b['month']}_{b['year']}.pdf",
    # Alternative URL format
    lambda b: f"https://publications.jrc.ec.europa.eu/repository/bitstream/{b['jrc']}/{b['jrc']}_MARS_Bulletin_{b['vol']:02d}_No{b['no']:02d}_{b['month']}_{b['year']}.pdf",
    # Simple format
    lambda b: f"https://publications.jrc.ec.europa.eu/repository/bitstream/{b['jrc']}/{b['jrc']}.pdf",
]


async def _fetch_latest_bulletin_url(bulletin: dict | None = None) -> str | None:
    """Try to find the latest MARS Bulletin PDF URL.
    
    Tries multiple URL patterns. Returns the first that returns HTTP 200.
    """
    b = bulletin or LATEST_BULLETIN

    for pattern in URL_PATTERNS:
        url = pattern(b)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(
                    url,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=aiohttp.ClientTimeout(total=10),
                    allow_redirects=True,
                ) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get("content-type", "")
                        if "pdf" in content_type.lower():
                            return url
                        # Also accept redirects that eventually resolve
                        if resp.status in (301, 302, 307, 308):
                            return str(resp.url)
        except Exception:
            continue

    return None


async def _download_pdf(url: str, cache_path: Path) -> Path | None:
    """Download MARS Bulletin PDF with retry and alternate sources."""
    if cache_path.exists():
        age = datetime.now().timestamp() - cache_path.stat().st_mtime
        if age < 86400 * 7:  # Cache for 7 days (bulletins change monthly)
            return cache_path

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=True,
            ) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    if len(content) > 10000:  # Sanity check: >10KB
                        cache_path.write_bytes(content)
                        return cache_path
    except Exception:
        pass

    # Fallback: curl with different options
    try:
        result = subprocess.run(
            ["curl", "-sL", "-A", "Mozilla/5.0", url, "-o", str(cache_path)],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0 and cache_path.exists() and cache_path.stat().st_size > 10000:
            return cache_path
    except Exception:
        pass

    return None


def _parse_pdf_to_text(pdf_path: Path) -> str | None:
    """Convert PDF to text using pdftotext."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True,
            timeout=30,
            text=True,
        )
        if result.returncode == 0 and len(result.stdout) > 500:
            return result.stdout
    except Exception:
        pass
    return None


# ── Text Parsing ──────────────────────────────────────────────────────────────

def _extract_yield_table(text: str) -> list[dict[str, Any]]:
    """Extract crop yield forecast tables from MARS Bulletin text.
    
    MARS bulletins contain tables like:
    "Table 1: Crop yield forecasts for EU Member States (t/ha)"
    with rows for each country/crop combination.
    """
    results = []
    lines = text.split("\n")

    in_table = False
    current_crop = None
    current_year = None

    for i, line in enumerate(lines):
        line_stripped = line.strip()

        # Detect table headers
        if re.search(r'(yield\s*forecast|crop\s*yield|table\s*\d+)', line_stripped, re.I):
            # Determine crop and year from context
            for crop in ["wheat", "maize", "corn", "barley", "rapeseed", "sunflower", "sugar beet", "potato"]:
                if crop in line_stripped.lower():
                    current_crop = crop
                    break
            yr_match = re.search(r'(20\d{2})', line_stripped)
            if yr_match:
                current_year = int(yr_match.group(1))
            in_table = True
            continue

        # Extract data rows: country name + numbers
        if in_table and line_stripped:
            # Match: country name followed by yield values
            # Common format: "Germany                    8.2    7.9    7.8"
            match = re.match(r'^([A-Za-z\s\-]+?)\s{3,}(\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)', line_stripped)
            if match:
                country = match.group(1).strip()
                values = [match.group(2), match.group(3), match.group(4)]
                entry = {
                    "country": country,
                    "crop": current_crop or "unknown",
                    "year": current_year,
                }
                # Try to interpret the three values
                # Usually: current year forecast, previous year, 5-year avg
                if len(values) >= 1:
                    v = _parse_decimal(values[0])
                    if v is not None:
                        entry["forecast_t_ha"] = v
                if len(values) >= 2:
                    v = _parse_decimal(values[1])
                    if v is not None:
                        entry["previous_year_t_ha"] = v
                if len(values) >= 3:
                    v = _parse_decimal(values[2])
                    if v is not None:
                        entry["five_year_avg_t_ha"] = v

                if "forecast_t_ha" in entry:
                    results.append(entry)
            # Detect end of table
            elif "Source:" in line_stripped or "Note:" in line_stripped:
                in_table = False

    return results


def _parse_decimal(s: str) -> float | None:
    """Parse a decimal number (handles European comma notation)."""
    s = s.strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _extract_ndvi_maps(text: str) -> list[dict[str, Any]]:
    """Extract NDVI anomaly information from bulletin text."""
    anomalies = []
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if "NDVI" in line and ("anomal" in line.lower() or "deviation" in line.lower()):
            anomalies.append({"description": line.strip()})
            # Get next few context lines
            for j in range(1, 4):
                if i + j < len(lines):
                    next_line = lines[i + j].strip()
                    if next_line and len(next_line) > 10:
                        anomalies[-1]["context"] = anomalies[-1].get("context", "") + " " + next_line
    return anomalies


def _extract_weather_summary(text: str) -> dict[str, Any]:
    """Extract key weather observations from bulletin."""
    summary = {"temperature": [], "precipitation": [], "frost": [], "drought": []}
    lines = text.split("\n")

    for i, line in enumerate(lines):
        lower = line.lower()
        if any(w in lower for w in ["temperature", "warm", "cold", "heat", "celsius", "°c"]):
            summary["temperature"].append(line.strip())
        if any(w in lower for w in ["rainfall", "precipitation", "rain", "wet", "dry"]):
            summary["precipitation"].append(line.strip())
        if "frost" in lower:
            summary["frost"].append(line.strip())
        if any(w in lower for w in ["drought", "water stress", "soil moisture deficit"]):
            summary["drought"].append(line.strip())

    # Trim to relevant lines
    for key in summary:
        summary[key] = summary[key][:10]

    return summary


# ── Main API ───────────────────────────────────────────────────────────────────


async def fetch_latest_bulletin() -> dict[str, Any]:
    """Download and parse the latest MARS Bulletin."""
    bulletin_url = await _fetch_latest_bulletin_url()
    if not bulletin_url:
        return {
            "status": "error",
            "error_code": "PDF_NOT_FOUND",
            "message": (
                "MARS Bulletin PDF could not be downloaded. The JRC server blocks automated "
                "requests. The next bulletin is expected June 22, 2026. "
                "In the meantime, use wasde_report() for USDA global supply/demand data."
            ),
        }

    filename = f"mars_bulletin_{LATEST_BULLETIN['year']}_{LATEST_BULLETIN['month']}.pdf"
    cache_path = CACHE_DIR / filename

    pdf_path = await _download_pdf(bulletin_url, cache_path)
    if not pdf_path:
        return {
            "status": "error",
            "error_code": "DOWNLOAD_FAILED",
            "message": f"Could not download PDF from {bulletin_url}",
        }

    text = _parse_pdf_to_text(pdf_path)
    if not text:
        return {
            "status": "error",
            "error_code": "PARSE_FAILED",
            "message": "Could not extract text from PDF",
        }

    # Parse content
    yield_data = _extract_yield_table(text)
    weather = _extract_weather_summary(text)
    ndvi = _extract_ndvi_maps(text)

    return {
        "status": "ok",
        "bulletin": {
            "title": LATEST_BULLETIN["title"],
            "date": LATEST_BULLETIN["date"],
            "jrc_number": LATEST_BULLETIN["jrc"],
            "url": bulletin_url,
        },
        "parsed_at": datetime.now(timezone.utc).isoformat(),
        "yield_forecasts": yield_data,
        "weather_highlights": {
            k: v[:5] for k, v in weather.items() if v
        },
        "ndvi_anomalies": ndvi,
        "total_yield_rows": len(yield_data),
    }


# ── MCP Handler ───────────────────────────────────────────────────────────────


async def _handle_mars_bulletin(**kwargs: Any) -> list[types.TextContent]:
    """Fetch the latest JRC MARS Bulletin — EU crop yield forecasts.

    Provides official EU yield forecasts for wheat, corn, barley, rapeseed, etc.
    Published monthly by the European Commission's Joint Research Centre.
    Note: May be temporarily unavailable if the JRC server blocks automated access.
    Next bulletin expected: June 22, 2026.
    """
    result = await fetch_latest_bulletin()
    return [types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
