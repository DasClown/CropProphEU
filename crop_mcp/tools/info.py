"""Discovery tools: list_regions and list_crops handlers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import mcp.types as types

from crop_mcp.core.regions import list_regions as _list_regions, list_crops as _list_crops


def _handle_list_regions(**kwargs: Any) -> list[types.TextContent]:
    """List available regions, optionally filtered by country."""
    from crop_mcp.server import ListRegionsInput
    validated = ListRegionsInput(**kwargs)
    regions = _list_regions(validated.country)
    result = []
    for code, r in sorted(regions.items()):
        result.append({
            "code": code,
            "name": r.name,
            "country": r.country,
            "crops": r.major_crops,
            "area_km2": r.area_km2,
            "latitude": r.latitude,
            "longitude": r.longitude,
        })
    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "count": len(result),
        "regions": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))]


def _handle_list_crops(**kwargs: Any) -> list[types.TextContent]:
    """List all supported crops with agronomic parameters."""
    crops = _list_crops()
    result = []
    for name, c in sorted(crops.items()):
        result.append({
            "name": c.name,
            "name_de": c.name_de,
            "gdd_base_temp": c.gdd_base,
            "gdd_optimum": c.gdd_optimum,
            "planting_month": c.planting_month,
            "harvest_month": c.harvest_month,
            "frost_sensitive": c.frost_sensitive,
            "water_sensitivity": c.water_sensitivity,
            "description": c.description,
        })
    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "count": len(result),
        "crops": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))]
