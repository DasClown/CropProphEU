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


def _handle_list_anchors(**kwargs) -> list[types.TextContent]:
    """List all anchored forecasts (compact overview)."""
    from crop_mcp.server import ListAnchorsInput
    v = ListAnchorsInput(**kwargs)
    
    try:
        from crop_mcp.anchor import list_anchors as _list_anchors
        anchors = _list_anchors()
        
        # Filter
        if v.region:
            anchors = [a for a in anchors if a.get("anchor_data", {}).get("region", "").upper() == v.region.upper()]
        if v.crop:
            anchors = [a for a in anchors if a.get("anchor_data", {}).get("crop", "").lower() == v.crop.lower()]
        
        # Sort: newest first
        anchors.sort(key=lambda a: a.get("timestamp", ""), reverse=True)
        
        # Limit
        anchors = anchors[:v.limit]
        
        compact = []
        for a in anchors:
            d = a.get("anchor_data", {})
            ots_hash = a.get("ots_hash", "")
            compact.append({
                "region": d.get("region", "?"),
                "crop": d.get("crop", "?"),
                "yield_t_ha": d.get("predicted_yield_t_ha"),
                "timestamp": a.get("timestamp", "?")[:19],
                "status": a.get("status", "?"),
                "ots_hash": (ots_hash[:16] + "...") if len(ots_hash) > 16 else ots_hash,
                "verified": a.get("verified", False),
            })
        
        # Summary stats (pre-filter for accurate counts)
        all_anchors = _list_anchors()
        total = len(all_anchors)
        anchored = sum(1 for a in all_anchors if a.get("status") == "anchored")
        
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "ok",
                "data": {
                    "total_anchors": total,
                    "filtered": len(anchors),
                    "anchored": anchored,
                    "anchors": compact,
                },
                "parameters": {"limit": v.limit, "region": v.region, "crop": v.crop},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }, indent=2),
        )]
    
    except ImportError:
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "message": "Anchor module not available.",
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
