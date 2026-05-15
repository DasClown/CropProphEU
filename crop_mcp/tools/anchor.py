"""
MCP handler for anchor_forecast — OpenTimestamps Proof-of-Forecast.
"""

import json
from datetime import datetime, timezone

from mcp import types


def _handle_anchor_forecast(**kwargs) -> list[types.TextContent]:
    """Anchor a forecast on Bitcoin blockchain via OpenTimestamps."""
    # Lazy import to avoid circular dependency
    from crop_mcp.server import AnchorForecastInput
    
    v = AnchorForecastInput(**kwargs)

    try:
        from crop_mcp.anchor import anchor_forecast as _anchor

        forecast_data = {
            "region": v.region,
            "crop": v.crop,
            "predicted_yield_t_ha": v.yield_t_ha,
            "p10": v.p10 or v.yield_t_ha * 0.8,
            "p90": v.p90 or v.yield_t_ha * 1.2,
            "label": v.label or f"forecast_{v.region}_{v.crop}",
            "model_version": "V5.4",
        }

        result = _anchor(forecast_data)

        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": result.get("status", "ok"),
                "data": result,
                "parameters": {
                    "region": v.region,
                    "crop": v.crop,
                    "yield_t_ha": v.yield_t_ha,
                    "label": v.label,
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }, indent=2),
        )]

    except ImportError:
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "message": "Anchor module not available. Install: pip install opentimestamps-client",
            }),
        )]
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "message": str(e)[:300],
            }),
        )]
