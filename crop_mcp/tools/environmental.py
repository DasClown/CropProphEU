"""Environmental risk handler (V5.4) for crop-mcp."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import mcp.types as types

# Optional: Environmental risk module
_HAS_ENV_RISK = False
try:
    from crop_mcp.environmental_risk import full_environmental_risk, compute_ers, compute_wild_boar_risk, batch_ers
    _HAS_ENV_RISK = True
except Exception:
    pass


def _handle_environmental_risk(**kwargs: Any) -> list[types.TextContent]:
    """Environmental Risk Score + Wildschaden-Risiko fuer eine Region."""
    from crop_mcp.server import EnvironmentalRiskInput

    v = EnvironmentalRiskInput(**kwargs)

    if not _HAS_ENV_RISK:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "message": "Environmental risk module not available.",
        }))]

    try:
        region_code = v.region.upper()
        country = region_code[:2]
        is_de = country == "DE" or region_code.startswith("DE")

        result = full_environmental_risk(region_code, country)

        if not v.include_wild_boar or not is_de:
            result["wild_boar_risk"] = {
                "note": "Not requested or non-DE region",
                "wild_boar_risk_score": 0,
                "wild_boar_risk_level": "n/a",
            }

        return [types.TextContent(type="text", text=json.dumps({
            "status": "ok",
            "data": result,
            "parameters": {"region": region_code, "include_wild_boar": v.include_wild_boar},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, indent=2))]

    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "message": str(e)[:200],
        }))]
