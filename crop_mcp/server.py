#!/usr/bin/env python3
"""
crop-mcp: EU Crop Intelligence for AI Agents
=============================================
MCP Server exposing agronomic intelligence tools.

Usage:
  python3 server.py              # Start MCP stdio server
  python3 server.py --test       # Self-test
  python3 server.py --list-tools # Show available tools
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

from .core.regions import REGIONS, CROPS, get_region, get_crop, list_regions, list_crops
from .sources.weather import (
    get_forecast,
    get_historical,
    analyze_growing_season,
    calc_gdd,
    drought_index,
)
from .sources.power import season_solar_and_soil, season_gdd_precip_power

# Market prices (€/t) for revenue calculation
try:
    from .market_prices import get_market_price, calculate_revenue, REFERENCE_PRICES
    _HAS_MARKET_PRICES = True
except Exception:
    _HAS_MARKET_PRICES = False

# Feature Cache (sub-second historische Vergleiche)
try:
    from .feature_cache import get as _cache_get
    _HAS_CACHE = True
except Exception:
    _HAS_CACHE = False

# V3: Analog-year yield simulator
from .simulate_yield import simulate_yield, YIELDS as _YIELDS

# European yield model (15 countries)
try:
    from .europe_model_api import predict_europe_yield, get_available_countries
    _HAS_EUROPE_MODEL = True
except Exception:
    _HAS_EUROPE_MODEL = False

# NDVI (optional — Planetary Computer API may be unavailable)
try:
    from .sources.ndvi import get_ndvi as _get_ndvi
    _HAS_NDVI = True
except Exception:
    _HAS_NDVI = False

# Environmental Risk Score (V5.4)
try:
    from .environmental_risk import (
        compute_ers,
        compute_wild_boar_risk,
        full_environmental_risk,
        batch_ers,
    )
    _HAS_ENV_RISK = True
except Exception:
    _HAS_ENV_RISK = False

# Forecast Anchoring (OpenTimestamps — Bitcoin Proof-of-Forecast)
try:
    from .anchor import anchor_forecast, verify_anchor, list_anchors
    _HAS_ANCHOR = True
except Exception:
    _HAS_ANCHOR = False

# NDVI Correction (adjusts model predictions with satellite data)
try:
    from .ndvi_correction import compute_ndvi_correction as _ndvi_correct
    _HAS_NDVI_CORRECTION = True
except Exception:
    _HAS_NDVI_CORRECTION = False

# Import handler functions from modular tools
from .tools.helpers import (
    _detect_language,
    _apply_ndvi_correction,
    _describe_gdd_en,
    _describe_precip_en,
    _describe_gdd,
    _describe_precip,
    _get_season_dates,
    _analyze_frost_outlook,
    _get_crop_cost,
)
from .tools.weather import (
    _handle_weather_outlook,
    _handle_crop_forecast,
    _handle_season_comparison,
    _handle_region_health,
)
from .tools.yield_tools import (
    _handle_yield_forecast,
    _handle_europe_yield_forecast,
    _handle_yield_and_value,
    _handle_climate_scenario,
)
from .tools.market import (
    _handle_compare_regions,
    _handle_portfolio_optimizer,
)
from .tools.info import (
    _handle_list_regions,
    _handle_list_crops,
)
from .tools.environmental import (
    _handle_environmental_risk,
)
from .tools.anchor import (
    _handle_anchor_forecast,
    _handle_list_anchors,
)
from .tools.wasde import (
    _handle_wasde_report,
    _handle_wasde_commodity,
)
from .tools.mars_bulletin import (
    _handle_mars_bulletin,
)

_start_time = time.time()

# Server-level language setting (from config or CLI)
_DEFAULT_LANGUAGE = os.environ.get("CROP_LANGUAGE", "de")

# ─────────────────────────────────────────────────────────────
# Pydantic Models (Agent-facing schemas)
# ─────────────────────────────────────────────────────────────

class WeatherOutlookInput(BaseModel):
    """Get weather forecast for a specific EU region."""
    region: str = Field(
        ...,
        min_length=4,
        max_length=5,
        description="NUTS2 region code (e.g. 'FRF2' for Picardie, 'DEE0' for Sachsen-Anhalt). "
                    "Use list_regions to discover available codes.",
    )
    days: int = Field(
        default=7,
        ge=1,
        le=16,
        description="Number of forecast days (1-16)",
    )


class CropForecastInput(BaseModel):
    """Generate a crop-specific forecast for a region combining weather + history."""
    crop: str = Field(
        ...,
        pattern=r"^(wheat|corn|rapeseed|sunflower|barley)$",
        description="Crop type. Use list_crops for details on each.",
    )
    region: str = Field(
        ...,
        min_length=4,
        max_length=5,
        description="NUTS2 region code",
    )
    as_of_date: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Optional reference date (YYYY-MM-DD) for rolling forecasts. "
                    "Default: today. Use to simulate what you'd have known on a past date.",
    )
    reference_years: int = Field(
        default=30,
        ge=5,
        le=40,
        description="Number of historical years for anomaly comparison (5-40, default 30)",
    )


class SeasonComparisonInput(BaseModel):
    """Compare current season weather to historical averages for a region."""
    crop: str = Field(
        ...,
        pattern=r"^(wheat|corn|rapeseed|sunflower|barley)$",
        description="Crop type to analyze",
    )
    region: str = Field(
        ...,
        min_length=4,
        max_length=5,
        description="NUTS2 region code",
    )
    reference_years: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Number of historical years to compare against (1-10)",
    )


class ListRegionsInput(BaseModel):
    """List available EU agricultural regions, optionally filtered by country."""
    country: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        pattern=r"^[A-Z]{2}$",
        description="ISO country code filter (e.g. 'DE', 'FR', 'PL'). Omit for all regions.",
    )


class ListCropsInput(BaseModel):
    """List all supported crop types with agronomic parameters."""
    pass


class RegionHealthInput(BaseModel):
    """Get comprehensive health overview for a region across all supported crops."""
    region: str = Field(
        ...,
        min_length=4,
        max_length=5,
        description="NUTS2 region code",
    )


class EnvironmentalRiskInput(BaseModel):
    """Assess environmental and wild boar damage risk for a region."""
    region: str = Field(
        ...,
        min_length=4,
        max_length=5,
        description="NUTS2 region code (e.g. 'DEE0', 'DE26', 'FRB0'). "
                    "Use list_regions to discover available codes.",
    )
    include_wild_boar: bool = Field(
        default=True,
        description="Include wild boar damage risk assessment (DE only, requires forest + corn data)",
    )


class YieldForecastInput(BaseModel):
    """Predict crop yield using analog-year matching."""
    crop: str = Field(
        ...,
        pattern=r"^(wheat|corn|rapeseed|sunflower|barley)$",
        description="Crop type. Use list_crops for available options.",
    )
    region: str = Field(
        ...,
        min_length=4,
        max_length=5,
        description="NUTS2 region code (e.g. 'DEE0' for Sachsen-Anhalt)",
    )
    as_of_date: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Optional reference date (YYYY-MM-DD). Default: today. "
                    "Earlier dates = lower confidence but useful for backtesting.",
    )


class EuropeanYieldForecastInput(BaseModel):
    """Predict crop yield for EU countries using Eurostat-verified data."""
    crop: str = Field(
        ...,
        pattern=r"^(wheat|corn|barley|rapeseed|sunflower)$",
        description="Crop type. Verified crops: wheat (C1100), corn (C1500), barley (C1300), rapeseed (I1110), sunflower (I1120).",
    )
    region: str = Field(
        ...,
        min_length=4,
        max_length=5,
        description="NUTS2 region code (e.g. 'DEE0' for Sachsen-Anhalt, 'FRF2' for Picardie)",
    )
    gdd: float | None = Field(
        default=None,
        description="Optional GDD override. If omitted, uses crop_forecast data.",
    )
    precipitation_mm: float | None = Field(
        default=None,
        description="Optional precipitation override.",
    )


class ClimateScenarioInput(BaseModel):
    """Climate scenario analysis: What if temperature/precipitation changes?"""
    crop: str = Field(
        ...,
        pattern=r"^(wheat|corn|barley|rapeseed|sunflower)$",
        description="Crop to analyze (verified: wheat, corn, barley, rapeseed, sunflower)",
    )
    region: str = Field(
        ...,
        min_length=4,
        max_length=5,
        description="NUTS2 region code",
    )
    temp_shift_C: float = Field(
        default=1.0,
        description="Temperature shift in °C (positive = warming). Applied to GDD.",
    )
    precip_shift_pct: float = Field(
        default=0.0,
        description="Precipitation shift in percent (e.g., -20 = 20% drier, +20 = 20% wetter)",
    )
    scenario_name: str = Field(
        default=None,
        description="Optional label for this scenario (e.g. '+2°C dry')",
    )
    as_of_date: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Optional reference date. Default: today.",
    )


class YieldAndValueInput(BaseModel):
    crop: str = Field(..., pattern=r"^(wheat|corn|barley|rapeseed|sunflower)$", description="Crop (verified: wheat, corn, barley, rapeseed, sunflower)")
    region: str = Field(..., min_length=4, max_length=5, description="NUTS2 code (e.g. DEE0)")
    gdd: float | None = Field(default=None, description="Optional GDD (growing degree days)")
    precipitation_mm: float | None = Field(default=None, description="Optional precipitation in mm")
    language: str | None = Field(default=None, description="Output language: 'de' (German, default) or 'en' (English). Auto-detected if omitted.")


class CompareRegionsInput(BaseModel):
    regions: str = Field(..., description="Comma-separated NUTS2 codes (e.g. 'DEE0,FR10,PL22'). Minimum 2. Max 20.",
                         pattern=r"^[A-Za-z]{2}[A-Za-z0-9]{2,3}(?:,[A-Za-z]{2}[A-Za-z0-9]{2,3})+$")
    crops: str = Field(..., description="Comma-separated crop names (e.g. 'wheat,corn,barley'). Options: wheat, corn, barley, rapeseed, sunflower.",
                        pattern=r"^(wheat|corn|barley|rapeseed|sunflower)(?:,(wheat|corn|barley|rapeseed|sunflower))+$")
    year: int = Field(default=2025, description="Target year for predictions")
    language: str | None = Field(default=None, description="Output language: 'de' or 'en'")


class PortfolioOptimizerInput(BaseModel):
    """Optimize a crop investment portfolio across EU regions."""
    budget_eur: float = Field(default=100000, description="Total budget in EUR for investment")
    risk_tolerance: str = Field(default="moderate", pattern=r"^(conservative|moderate|aggressive)$",
                                description="Risk tolerance: conservative (stable regions/crops), moderate (balanced), aggressive (high-ROI)")
    regions: str | None = Field(default=None, description="Optional NUTS2 filter (comma-separated). Default: top 15 regions.",
                                pattern=r"^[A-Za-z]{2}[A-Za-z0-9]{2,3}(?:,[A-Za-z]{2}[A-Za-z0-9]{2,3})*$")
    crops: str | None = Field(default=None, description="Optional crop filter (comma-separated). Default: all crops.",
                              pattern=r"^(wheat|corn|barley|rapeseed|sunflower)(?:,(wheat|corn|barley|rapeseed|sunflower))*$")
    year: int = Field(default=2026, description="Target year")
    language: str | None = Field(default=None, description="Output language")


class AnchorForecastInput(BaseModel):
    """Anchor a forecast on Bitcoin blockchain via OpenTimestamps (Proof-of-Forecast)."""
    region: str = Field(
        ..., min_length=4, max_length=5,
        description="NUTS2 region code whose forecast to anchor",
    )
    crop: str = Field(
        ..., pattern=r"^(wheat|corn|barley|rapeseed|sunflower)$",
        description="Crop whose forecast to anchor",
    )
    yield_t_ha: float = Field(
        ..., gt=0, le=20,
        description="Predicted yield in t/ha to anchor",
    )
    p10: float | None = Field(default=None, description="P10 yield (lower bound)")
    p90: float | None = Field(default=None, description="P90 yield (upper bound)")
    label: str | None = Field(
        default=None,
        description="Optional label for this anchor (e.g. 'pre-WASDE June 2026')",
    )


class ListAnchorsInput(BaseModel):
    """List all anchored forecasts (compact overview)."""
    limit: int = Field(
        default=20, ge=1, le=100,
        description="Maximum number of anchors to return (1-100, default 20)",
    )
    region: str | None = Field(
        default=None, min_length=4, max_length=5,
        description="Optional NUTS2 filter (e.g. 'DEE0'). Omit for all regions.",
    )
    crop: str | None = Field(
        default=None, pattern=r"^(wheat|corn|barley|rapeseed|sunflower)$",
        description="Optional crop filter. Omit for all crops.",
    )


# ─────────────────────────────────────────────────────────────
# Tool Registry
# ─────────────────────────────────────────────────────────────

class WasdeReportInput(BaseModel):
    """Fetch the latest USDA WASDE report with EU tables: Wheat, Corn, Rice, Soybeans."""
    pass


class WasdeCommodityInput(BaseModel):
    """Fetch WASDE data for a specific commodity (wheat, corn, rice, soybeans)."""
    commodity: str = Field(
        ...,
        pattern=r"^(wheat|corn|rice|soybeans)$",
        description="Commodity to fetch. Options: wheat, corn, rice, soybeans. Note: rapeseed/sunflower not in WASDE.",
    )


class MarsBulletinInput(BaseModel):
    """Fetch the latest JRC MARS Bulletin — EU crop yield forecasts and weather monitoring."""
    pass


TOOLS = {
    "weather_outlook": {
        "handler": _handle_weather_outlook,
        "description": (
            "16-day weather forecast for an EU agricultural region. Returns "
            "temperature, precipitation, and wind data. Call this before making "
            "crop forecasts to understand immediate weather conditions."
        ),
        "input_schema": WeatherOutlookInput.model_json_schema(),
    },
    "crop_forecast": {
        "handler": _handle_crop_forecast,
        "description": (
            "Crop-specific yield outlook for a region. Combines current weather, "
            "historical comparison, and crop phenology models. Returns GDD "
            "accumulation, precipitation, drought index, and yield signals. "
            "This is the primary intelligence tool — use it to assess crop "
            "health and expected yield relative to historical averages."
        ),
        "input_schema": CropForecastInput.model_json_schema(),
    },
    "season_comparison": {
        "handler": _handle_season_comparison,
        "description": (
            "Compare the current growing season to historical years for a "
            "specific crop and region. Returns GDD, precipitation, frost days, "
            "and heat days for each year. Use to detect trends and anomalies."
        ),
        "input_schema": SeasonComparisonInput.model_json_schema(),
    },
    "list_regions": {
        "handler": _handle_list_regions,
        "description": (
            "List available EU agricultural regions with their NUTS2 codes, "
            "coordinates, and major crops. Filter by country code (e.g. 'FR', "
            "'DE', 'PL'). Call this first to discover valid region codes."
        ),
        "input_schema": ListRegionsInput.model_json_schema(),
    },
    "list_crops": {
        "handler": _handle_list_crops,
        "description": (
            "List all supported crop types with their agronomic parameters "
            "(GDD base temperature, growing season, water sensitivity). "
            "Use this to understand which crops are available and their "
            "biological requirements."
        ),
        "input_schema": ListCropsInput.model_json_schema(),
    },
    "region_health": {
        "handler": _handle_region_health,
        "description": (
            "Comprehensive health overview for an entire agricultural region. "
            "Returns crop_forecast for ALL crops grown in the region — GDD, "
            "precipitation, soil moisture, solar radiation, and yield signals "
            "in a single call. Use this for a complete regional assessment."
        ),
        "input_schema": RegionHealthInput.model_json_schema(),
    },
    "yield_forecast": {
        "handler": _handle_yield_forecast,
        "description": (
            "Predict crop yield in t/ha using analog-year matching. "
            "Compares current season's weather (GDD, precipitation, solar radiation, "
            "soil moisture) to 25 years of historical data, finds the most similar "
            "years, and projects their yields. Returns mean, min, max, and top analogs. "
            "Confidence increases as the season progresses."
        ),
        "input_schema": YieldForecastInput.model_json_schema(),
    },
    "europe_yield_forecast": {
        "handler": _handle_europe_yield_forecast,
        "description": (
            "Pan-European yield forecast for 5 verified crops (wheat, corn, barley, rapeseed, sunflower). "
            "Uses Random Forest trained on Eurostat yield data (C1100/C1300/C1500/I1110/I1120) "
            "across 25 EU countries. Combines weather + 7 soil features + yield-at-risk."
        ),
        "input_schema": EuropeanYieldForecastInput.model_json_schema(),
    },
    "climate_scenario": {
        "handler": _handle_climate_scenario,
        "description": (
            "Climate What-If scenario analysis for EU crop yields. "
            "Use this to answer 'What if May-June is 2°C warmer?' or "
            "'What if we get 20% less rain?'"
        ),
        "input_schema": ClimateScenarioInput.model_json_schema(),
    },
    "yield_and_value": {
        "handler": _handle_yield_and_value,
        "description": (
            "Combined yield forecast + market value estimation. "
            "Returns yield in t/ha AND expected revenue in EUR/ha at current market prices. "
            "Output includes a plain-language summary in German (default) or English. "
            "Set language='en' for English output, language='de' for German. "
            "Auto-detects from the language parameter if provided. "
            "Verified crops: wheat, corn, barley, rapeseed, sunflower."
        ),
        "input_schema": YieldAndValueInput.model_json_schema(),
    },
    "compare_regions": {
        "handler": _handle_compare_regions,
        "description": (
            "Compare crop yields across multiple EU regions in a single call. "
            "Input comma-separated NUTS2 region codes and crop names. "
            "Returns a sorted table of predicted yields, risk ranges, and market values. "
            "Use this to find the best region×crop combination for investment decisions. "
            "Example: compare_regions(regions='DEE0,FR10,HU10', crops='wheat,corn')"
        ),
        "input_schema": CompareRegionsInput.model_json_schema(),
    },
    "portfolio_optimizer": {
        "handler": _handle_portfolio_optimizer,
        "description": (
            "Optimal EU crop investment allocation. "
            "Given a budget and risk tolerance, returns a diversified portfolio "
            "across regions and crops. Uses live market prices, NDVI correction, "
            "and model confidence scores for risk-adjusted optimization. "
            "Pure AI-for-AI decision support. "
            "Example: portfolio_optimizer(budget_eur=500000, risk_tolerance='moderate')"
        ),
        "input_schema": PortfolioOptimizerInput.model_json_schema(),
    },
    "environmental_risk": {
        "handler": _handle_environmental_risk,
        "description": (
            "Environmental Risk Score (ERS) for EU NUTS2 regions. "
            "Combines forest cover, maize share, soil erosion, storm and hail risk "
            "into a 3-tier (high/moderate/low) environmental risk indicator. "
            "For German regions (DExx), also returns wild boar damage risk "
            "with estimated €/ha losses for maize. "
            "Use this to factor environmental hazards into crop decisions. "
            "Example: environmental_risk(region='DE26') for Unterfranken/Massbach"
        ),
        "input_schema": EnvironmentalRiskInput.model_json_schema(),
    },
    "anchor_forecast": {
        "handler": _handle_anchor_forecast,
        "description": (
            "Anchor a forecast on Bitcoin blockchain via OpenTimestamps — Proof-of-Forecast. "
            "Creates an immutable timestamp proving the forecast existed before official "
            "reports (e.g., WASDE). Zero gas costs, zero keys needed. "
            "Returns SHA256 hash + .ots proof file that can be verified independently. "
            "Use this to generate verifiable audit trails for trading desks and insurers. "
            "Example: anchor_forecast(region='DEE0', crop='wheat', yield_t_ha=7.35)"
        ),
        "input_schema": AnchorForecastInput.model_json_schema(),
    },
    "list_anchors": {
        "handler": _handle_list_anchors,
        "description": (
            "List all anchored forecasts — compact overview of Proof-of-Forecast entries. "
            "Returns timestamp, region, crop, yield, status for each anchor. "
            "Optionally filter by region (NUTS2) or crop. "
            "Use this to track which forecasts have been timestamped on the Bitcoin blockchain "
            "via OpenTimestamps before comparing with official reports (WASDE, Eurostat). "
            "Example: list_anchors(limit=10, region='DEE0')"
        ),
        "input_schema": ListAnchorsInput.model_json_schema(),
    },
    "wasde_report": {
        "handler": _handle_wasde_report,
        "description": (
            "Fetch the latest USDA WASDE report — World Agricultural Supply and Demand Estimates. "
            "Downloads the monthly PDF, extracts EU-specific tables for Wheat, Corn, Rice, and Soybeans. "
            "Returns production, beginning stocks, imports, domestic use, exports, ending stocks, "
            "and month-over-month changes (May→June delta). "
            "Use this to validate your crop forecasts against the official USDA global benchmark. "
            "Note: WASDE does not contain rapeseed/sunflower data — those come from Eurostat. "
            "Example: wasde_report() — no arguments needed."
        ),
        "input_schema": WasdeReportInput.model_json_schema(),
    },
    "wasde_commodity": {
        "handler": _handle_wasde_commodity,
        "description": (
            "Fetch WASDE data for a single commodity. "
            "Available: wheat, corn, rice, soybeans (not rapeseed/sunflower). "
            "Returns EU-specific supply and use table plus global context. "
            "Faster than wasde_report if you need only one commodity. "
            "Example: wasde_commodity(commodity='wheat')"
        ),
        "input_schema": WasdeCommodityInput.model_json_schema(),
    },
    "mars_bulletin": {
        "handler": _handle_mars_bulletin,
        "description": (
            "Fetch the latest JRC MARS Bulletin — official EU crop yield forecasts. "
            "The MARS Bulletin is published ~monthly by the European Commission's Joint Research Centre "
            "and provides NUTS2-level yield forecasts for EU Member States. "
            "Includes: wheat, corn, barley, rapeseed, sunflower yield tables, "
            "weather monitoring (GDP, precipitation, frost), and NDVI anomaly maps. "
            "Note: The JRC server may block automated access — next bulletin expected 2026-06-22. "
            "Use wasde_report() as alternative for USDA global supply/demand data."
        ),
        "input_schema": MarsBulletinInput.model_json_schema(),
    },
}

# ─────────────────────────────────────────────────────────────
# MCP Server
# ─────────────────────────────────────────────────────────────

server = Server("crop-mcp")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=name,
            description=meta["description"],
            inputSchema=meta["input_schema"],
        )
        for name, meta in TOOLS.items()
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    meta = TOOLS.get(name)
    if not meta:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "error_code": "UNKNOWN_TOOL",
            "message": f"Tool '{name}' not found. Available: {list(TOOLS.keys())}",
        }))]
    try:
        return meta["handler"](**(arguments or {}))
    except KeyError as e:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "error_code": "UNKNOWN_KEY",
            "message": str(e),
        }))]
    except ValueError as e:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "message": str(e),
        }))]
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "error_code": "TOOL_ERROR",
            "message": str(e),
            "traceback": tb.split("\n")[-6:] if "--debug" in sys.argv else "Use --debug for traceback",
        }))]


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="crop-mcp",
                server_version="4.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def self_test() -> int:
    """Run self-test on all tools."""
    print("=== crop-mcp Self-Test ===\n")

    tests = [
        ("list_crops", {}),
        ("list_regions", {}),
        ("list_regions", {"country": "DE"}),
        ("weather_outlook", {"region": "FRF2", "days": 3}),
        ("crop_forecast", {"crop": "wheat", "region": "DEE0"}),
        ("season_comparison", {"crop": "wheat", "region": "FRF2", "reference_years": 3}),
        ("list_anchors", {"limit": 5}),
    ]

    all_passed = True
    for name, args in tests:
        try:
            result = TOOLS[name]["handler"](**args)
            payload = json.loads(result[0].text)
            status = payload.get("status", "?")
            emoji = "✅" if status == "ok" else "❌"
            preview = json.dumps(payload, indent=2)[:150]
            print(f"  {emoji} {name}({json.dumps(args)})")
            all_passed = all_passed and (status == "ok")
        except Exception as e:
            print(f"  ❌ {name}({json.dumps(args)}) → {e}")
            all_passed = False

    print(f"\n{'✅ All tests passed!' if all_passed else '❌ Some tests failed.'}")
    return 0 if all_passed else 1


# ─────────────────────────────────────────────────────────────
# Hot-Reload (--reload flag)
# ─────────────────────────────────────────────────────────────

def _run_with_reload() -> None:
    """Run the server with auto-reload on file changes."""
    import os
    import subprocess
    import time

    watch_dirs = {
        os.path.dirname(os.path.abspath(__file__)),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"),
    }
    watch_exts = {".py"}

    def _get_mtimes() -> dict:
        mtimes = {}
        for d in watch_dirs:
            if not os.path.isdir(d):
                continue
            for fname in os.listdir(d):
                if any(fname.endswith(ext) for ext in watch_exts):
                    fpath = os.path.join(d, fname)
                    try:
                        mtimes[fpath] = os.path.getmtime(fpath)
                    except OSError:
                        pass
        return mtimes

    server_script = os.path.abspath(__file__)
    print(f"[reload] Starting crop-mcp with hot-reload...")
    print(f"[reload] Watching {len(watch_dirs)} directories for .py changes")

    last_mtimes = _get_mtimes()
    proc = None

    def _start_server():
        nonlocal proc
        proc = subprocess.Popen(
            [sys.executable, server_script],
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        print(f"[reload] Server started (PID {proc.pid})")

    _start_server()

    try:
        while True:
            time.sleep(2)
            current_mtimes = _get_mtimes()
            changed = []
            for fpath, mtime in current_mtimes.items():
                old = last_mtimes.get(fpath)
                if old is not None and mtime > old:
                    changed.append(os.path.basename(fpath))
                last_mtimes[fpath] = mtime

            if changed:
                print(f"[reload] 🔄 Detected changes in: {', '.join(changed)}")
                print(f"[reload] Restarting server...")
                if proc:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                _start_server()
                last_mtimes = _get_mtimes()

    except KeyboardInterrupt:
        print(f"\n[reload] Shutting down...")
        if proc:
            proc.terminate()
            proc.wait()
        sys.exit(0)


# ── Public API for CLI ──

def run_stdio():
    """Start the MCP server in stdio mode (default)."""
    import asyncio
    asyncio.run(main())

async def run_http(host: str = "0.0.0.0", port: int = 8080):
    """Start the MCP server in HTTP/SSE mode."""
    try:
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route
    except ImportError:
        print("HTTP mode requires: pip install mcp[httpx] uvicorn")
        sys.exit(1)

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            read_stream, write_stream = streams
            await server.run(read_stream, write_stream, server.create_initialization_options())

    async def handle_root(request):
        from starlette.responses import JSONResponse
        return JSONResponse({
            "server": "crop-mcp",
            "version": "4.6.0",
            "description": "EU Crop Intelligence MCP Server — Yield forecasts, market values & risk analysis for EU agriculture. 10 tools, 120+ NUTS2 regions, 5 crops, 25-year climate library.",
            "tools": list(TOOLS.keys()),
            "docs": "https://github.com/DasClown/CropProphEU",
            "endpoints": {
                "sse": "/sse",
                "server_card": "/.well-known/mcp/server-card.json",
                "config_schema": "/.well-known/mcp/config-schema.json",
            }
        })

    async def handle_server_card(request):
        from starlette.responses import JSONResponse
        from copy import deepcopy
        tools_list = []
        for name, meta in TOOLS.items():
            tools_list.append({
                "name": name,
                "description": meta["description"],
                "inputSchema": meta["input_schema"],
            })
        return JSONResponse({
            "serverInfo": {"name": "crop-mcp", "version": "4.6.0"},
            "description": "EU Crop Intelligence MCP Server. Combines NASA POWER (weather), Open-Meteo, Eurostat (yields), SoilGrids (soil), and Yahoo Finance (market prices) into comprehensive crop intelligence for AI agents. Output in German or English.",
            "homepage": "https://github.com/DasClown/CropProphEU",
            "license": "MIT",
            "author": {
                "name": "CropProphEU",
                "email": "",
                "url": "https://github.com/DasClown",
            },
            "iconUrl": "https://raw.githubusercontent.com/DasClown/CropProphEU/main/static/icon.svg",
            "capabilities": {
                "tools": {"total": len(tools_list), "list": [t["name"] for t in tools_list]},
                "resources": {"total": 2, "list": ["crops://parameters", "regions://list"]},
                "prompts": {"total": 3, "list": ["analyze-region", "compare-regions", "market-overview"]},
            },
            "dataSources": [
                {"name": "NASA POWER", "type": "weather", "url": "https://power.larc.nasa.gov/"},
                {"name": "Open-Meteo", "type": "weather", "url": "https://open-meteo.com/"},
                {"name": "Eurostat", "type": "yield", "url": "https://ec.europa.eu/eurostat/"},
                {"name": "SoilGrids", "type": "soil", "url": "https://soilgrids.org/"},
                {"name": "Yahoo Finance", "type": "market", "url": "https://finance.yahoo.com/"},
                {"name": "CBOT", "type": "market", "url": "https://www.cmegroup.com/markets/agriculture/"},
            ],
            "tools": tools_list,
            "resources": [
                {
                    "name": "Crop Parameters",
                    "uri": "crops://parameters",
                    "description": "Agronomische Parameter aller unterstützten Kulturen: GDD-Basistemperatur, Wachstumsperiode, Wasserbedarf",
                    "mimeType": "application/json",
                },
                {
                    "name": "Region List",
                    "uri": "regions://list",
                    "description": "Alle verfügbaren EU NUTS2-Regionen mit Koordinaten, Ländern und Hauptkulturen",
                    "mimeType": "application/json",
                },
            ],
            "prompts": [
                {
                    "name": "analyze-region",
                    "description": "Complete health check for a region: yield forecast + market value + weather for all crops",
                    "arguments": [
                        {"name": "region", "description": "NUTS2 region code", "required": True},
                    ],
                },
                {
                    "name": "compare-regions",
                    "description": "Compare two EU regions across all metrics for a specific crop",
                    "arguments": [
                        {"name": "crop", "description": "Crop name (wheat, corn, rapeseed, sunflower, barley)", "required": True},
                        {"name": "region_a", "description": "First NUTS2 region", "required": True},
                        {"name": "region_b", "description": "Second NUTS2 region", "required": True},
                    ],
                },
                {
                    "name": "market-overview",
                    "description": "Current market prices and yield outlook for top EU producers",
                    "arguments": [
                        {"name": "crop", "description": "Crop to analyze", "required": True},
                    ],
                },
            ],
        })

    async def handle_config_schema(request):
        from starlette.responses import JSONResponse
        return JSONResponse({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "default_region": {
                    "type": "string",
                    "title": "Standard-Region",
                    "default": "DEE0",
                    "description": "NUTS2-Region für Standard-Abfragen (z.B. DEE0 = Sachsen-Anhalt)",
                    "examples": ["DEE0", "FRF2", "HU21"],
                    "pattern": "^[A-Z]{2}[A-Z0-9]{2,3}$",
                },
                "language": {
                    "type": "string",
                    "title": "Language",
                    "default": "de",
                    "enum": ["de", "en"],
                    "description": "Output language for summaries: 'de' (German) or 'en' (English)",
                },
                "confidence_threshold": {
                    "type": "number",
                    "title": "Konfidenz-Schwelle",
                    "default": 0.3,
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Minimale Konfidenz für Ertragsprognosen (0.0 = alle anzeigen, 1.0 = nur sichere)",
                },
            },
            "required": [],
        })

    app = Starlette(
        routes=[
            Route("/", endpoint=handle_root),
            Route("/.well-known/mcp/server-card.json", endpoint=handle_server_card),
            Route("/.well-known/mcp/config-schema.json", endpoint=handle_config_schema),
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )
    import uvicorn
    config = uvicorn.Config(app, host=host, port=port)
    srv = uvicorn.Server(config)
    print(f"🌾 crop-mcp HTTP server on http://{host}:{port}/sse")
    await srv.serve()


if __name__ == "__main__":
    if "--reload" in sys.argv:
        _run_with_reload()
    elif "--test" in sys.argv:
        sys.exit(self_test())
    elif "--list-tools" in sys.argv:
        print(json.dumps([{"name": n, "description": t["description"][:80]}
                          for n, t in TOOLS.items()], indent=2))
    else:
        # Parse --language from CLI args before starting
        for i, arg in enumerate(sys.argv):
            if arg == "--language" and i + 1 < len(sys.argv):
                _DEFAULT_LANGUAGE = sys.argv[i + 1]
                break
        import asyncio
        asyncio.run(main())
