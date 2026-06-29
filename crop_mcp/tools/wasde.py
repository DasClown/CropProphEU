"""
WASDE PDF Parser — World Agricultural Supply and Demand Estimates.
Downloads USDA WASDE PDFs and extracts EU tables for Wheat, Corn, Rice, Soybeans.

Targets the **2026/27 Proj.** marketing year tables (latest WASDE).
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

WASDE_BASE_URL = "https://www.usda.gov/oce/commodity/wasde"
CACHE_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / ".." / ".." / "cache" / "wasde"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Column Definitions ─────────────────────────────────────────────────────────

COMMODITY_TABLES = {
    "wheat": {
        "tables": ["World Wheat Supply and Use"],
        "columns": [
            ("beginning_stocks", "MMT"),
            ("production", "MMT"),
            ("imports", "MMT"),
            ("feed_domestic", "MMT"),
            ("total_domestic", "MMT"),
            ("exports", "MMT"),
            ("ending_stocks", "MMT"),
        ],
    },
    "corn": {
        "tables": ["World Coarse Grain Supply and Use"],
        "columns": [
            ("beginning_stocks", "MMT"),
            ("production", "MMT"),
            ("imports", "MMT"),
            ("feed_domestic", "MMT"),
            ("total_domestic", "MMT"),
            ("exports", "MMT"),
            ("ending_stocks", "MMT"),
        ],
    },
    "rice": {
        "tables": ["World Rice Supply and Use"],
        "columns": [
            ("beginning_stocks", "MMT"),
            ("production", "MMT"),
            ("imports", "MMT"),
            ("feed_domestic", "MMT"),
            ("total_domestic", "MMT"),
            ("exports", "MMT"),
            ("ending_stocks", "MMT"),
        ],
    },
    "soybeans": {
        "tables": ["World Soybean Supply and Use"],
        "columns": [
            ("beginning_stocks", "MMT"),
            ("production", "MMT"),
            ("imports", "MMT"),
            ("crush", "MMT"),
            ("total_domestic", "MMT"),
            ("exports", "MMT"),
            ("ending_stocks", "MMT"),
        ],
    },
}

# ── Parsing Helpers ────────────────────────────────────────────────────────────


def _parse_value(s: str) -> float | None:
    """Parse a WASDE table cell value."""
    s = s.strip()
    if not s or s in ("", ".", "3/", "—", "-", "3/"):
        return None
    # Remove footnote markers
    s = re.sub(r'\d/$', '', s)
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _extract_2026_table(text: str, commodity_config: dict) -> list[dict[str, Any]]:
    """Extract EU rows from the 2026/27 projection table for a commodity.

    Strategy: Find the '2026/27 Proj.' header, then find 'European Union' lines
    below it. The table has two-row entries (May and Jun).
    """
    lines = text.split("\n")
    results = []

    # Find the 2026/27 header
    proj_start = None
    for i, line in enumerate(lines):
        if "2026/27 Proj." in line or "2026/27" in line:
            # Verify this is within a relevant section
            section_context = "\n".join(lines[max(0, i - 3):i + 1])
            if any(t in section_context for t in commodity_config.get("tables", [])):
                proj_start = i
                break

    if proj_start is None:
        return results

    # Now find European Union rows within 150 lines after the header
    col_defs = commodity_config["columns"]
    search_end = min(proj_start + 150, len(lines))

    i = proj_start
    while i < search_end:
        line = lines[i]
        if "European Union" in line:
            # This is a May or Jun row
            row_data = {"region": "European Union", "commodity": commodity_config.get("_name", "")}

            # Determine month from this line
            may_values = None
            jun_values = None

            if "May" in line:
                may_values = _extract_values_from_row(line)
                # Check next line for Jun
                if i + 1 < search_end:
                    next_line = lines[i + 1]
                    if "European Union" not in next_line and "Jun" in next_line:
                        jun_values = _extract_values_from_row(next_line)
                        i += 1  # skip the Jun line
            elif "Jun" in line:
                jun_values = _extract_values_from_row(line)
                # Check previous line for May
                if i > proj_start:
                    prev_line = lines[i - 1]
                    if "European Union" not in prev_line and "May" in prev_line:
                        may_values = _extract_values_from_row(prev_line)

            if may_values is not None:
                for idx, (col_name, unit) in enumerate(col_defs):
                    if idx < len(may_values):
                        val = _parse_value(may_values[idx])
                        if val is not None:
                            row_data[f"may_{col_name}"] = val

            if jun_values is not None:
                for idx, (col_name, unit) in enumerate(col_defs):
                    if idx < len(jun_values):
                        val = _parse_value(jun_values[idx])
                        if val is not None:
                            row_data[f"jun_{col_name}"] = val

            # Compute deltas
            for col_name, _ in col_defs:
                may_key = f"may_{col_name}"
                jun_key = f"jun_{col_name}"
                if may_key in row_data and jun_key in row_data:
                    delta = round(row_data[jun_key] - row_data[may_key], 2)
                    if delta != 0:
                        row_data[f"delta_{col_name}"] = delta

            if may_values is not None or jun_values is not None:
                results.append(row_data)

        i += 1

    return results


def _extract_values_from_row(line: str) -> list[str]:
    """Extract numeric values from a WASDE 'European Union' table row.

    The row format is:
        "    European Union 5/       May         16.88        136.00        ..."
    or  "                            Jun         16.88        136.00        ..."
    """
    # Remove everything up to and including the month marker
    line = re.sub(r'^.*?(May|Jun|June)\s+', '', line, count=1)
    # Split on 2+ whitespace
    parts = re.split(r'\s{2,}', line.strip())
    return [p for p in parts if p and p != "."]

# ── PDF Download & Parse ──────────────────────────────────────────────────────


async def _download_pdf(url: str, cache_path: Path) -> Path | None:
    """Download WASDE PDF and cache locally."""
    if cache_path.exists():
        age = datetime.now().timestamp() - cache_path.stat().st_mtime
        if age < 86400:  # < 24 hours
            return cache_path

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return None
                content = await resp.read()
                cache_path.write_bytes(content)
                return cache_path
    except Exception:
        # Fall back to sync curl
        try:
            result = subprocess.run(
                ["curl", "-sL", url, "-o", str(cache_path)],
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0 and cache_path.exists() and cache_path.stat().st_size > 1000:
                return cache_path
        except Exception:
            pass
    return None


def _parse_pdf_to_text(pdf_path: Path) -> str | None:
    """Convert PDF to text using pdftotext with layout preservation."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True,
            timeout=30,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return None


# ── Main API ───────────────────────────────────────────────────────────────────


def get_wasde_pdf_url(year: int | None = None, month_num: int | None = None) -> str:
    """Get download URL for the latest WASDE PDF."""
    now = datetime.now()
    y = year if year else now.year
    m = month_num if month_num else now.month
    return f"{WASDE_BASE_URL}/wasde{m:02d}{y % 100}v2.pdf"


async def parse_latest_wasde() -> dict[str, Any]:
    """Download and parse the latest WASDE report. Returns EU-specific data."""
    url = get_wasde_pdf_url()
    filename = f"wasde_{datetime.now().strftime('%Y%m')}.pdf"
    cache_path = CACHE_DIR / filename

    pdf_path = await _download_pdf(url, cache_path)
    if not pdf_path:
        url_no_v2 = url.replace("v2.pdf", ".pdf")
        pdf_path = await _download_pdf(url_no_v2, cache_path)

    if not pdf_path:
        return {
            "status": "error",
            "error_code": "DOWNLOAD_FAILED",
            "message": f"Could not download WASDE PDF from {url}",
        }

    text = _parse_pdf_to_text(pdf_path)
    if not text:
        return {
            "status": "error",
            "error_code": "PDF_PARSE_FAILED",
            "message": f"Could not extract text from {pdf_path}",
        }

    # Extract report metadata
    report = {}
    for line in text.split("\n"):
        if "WASDE -" in line:
            m = re.search(r'WASDE\s*-\s*(\d+)', line)
            if m:
                report["wasde_number"] = int(m.group(1))
            m2 = re.search(r'(\w+\s+\d+,\s+\d{4})', line)
            if m2:
                report["date"] = m2.group(1)

    # Parse each commodity
    commodities = {}
    for commodity, config in COMMODITY_TABLES.items():
        config["_name"] = commodity
        eu_rows = _extract_2026_table(text, config)
        if eu_rows:
            commodities[commodity] = eu_rows

    # Build key summary
    summary = {}
    for commodity, rows in commodities.items():
        for row in rows:
            summary[f"EU_{commodity}_production"] = row.get("jun_production") or row.get("may_production")
            summary[f"EU_{commodity}_exports"] = row.get("jun_exports") or row.get("may_exports")
            summary[f"EU_{commodity}_ending_stocks"] = row.get("jun_ending_stocks") or row.get("may_ending_stocks")

    return {
        "status": "ok",
        "report": report,
        "parsed_at": datetime.now(timezone.utc).isoformat(),
        "commodities": commodities,
        "summary": summary,
    }


# ── MCP Handlers ──────────────────────────────────────────────────────────────


async def _handle_wasde_report(**kwargs: Any) -> list[types.TextContent]:
    """Fetch and parse the latest USDA WASDE report. No arguments needed."""
    parsed = await parse_latest_wasde()
    if parsed.get("status") == "error":
        return [types.TextContent(type="text", text=json.dumps(parsed, indent=2))]

    output = {
        "status": "ok",
        "report": parsed.get("report", {}),
        "parsed_at": parsed.get("parsed_at"),
        "eu_data": {},
    }

    for commodity, rows in parsed.get("commodities", {}).items():
        if rows:
            output["eu_data"][commodity] = rows[0]

    output["summary"] = parsed.get("summary", {})
    return [types.TextContent(type="text", text=json.dumps(output, indent=2, default=str))]


async def _handle_wasde_commodity(**kwargs: Any) -> list[types.TextContent]:
    """Fetch WASDE for a single commodity (wheat, corn, rice, soybeans)."""
    commodity = kwargs.get("commodity", "").lower().strip()
    if commodity not in COMMODITY_TABLES:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "error_code": "UNKNOWN_COMMODITY",
            "message": f"Unknown '{commodity}'. Available: {list(COMMODITY_TABLES.keys())}",
        }))]

    parsed = await parse_latest_wasde()
    if parsed.get("status") == "error":
        return [types.TextContent(type="text", text=json.dumps(parsed, indent=2))]

    rows = parsed.get("commodities", {}).get(commodity, [])
    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "commodity": commodity,
        "report": parsed.get("report", {}),
        "eu_data": rows,
        "summary": parsed.get("summary", {}),
    }, indent=2, default=str))]
