"""Market comparison and portfolio optimization handlers for crop-mcp."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import mcp.types as types

from crop_mcp.core.regions import get_region
from crop_mcp.tools.helpers import _apply_ndvi_correction, _get_crop_cost, _detect_language

# Optional: European model
_HAS_EUROPE_MODEL = False
try:
    from crop_mcp.europe_model_api import predict_europe_yield, get_available_countries
    _HAS_EUROPE_MODEL = True
except Exception:
    pass

# Optional: Market prices
_HAS_MARKET_PRICES = False
try:
    from crop_mcp.market_prices import calculate_revenue
    _HAS_MARKET_PRICES = True
except Exception:
    pass

_DEFAULT_LANGUAGE = __import__("os").environ.get("CROP_LANGUAGE", "de")


def _handle_compare_regions(**kwargs: Any) -> list[types.TextContent]:
    """Compare multiple regions × crops — find the best combination."""
    if not _HAS_EUROPE_MODEL:
        return [types.TextContent(type="text", text=json.dumps({"status": "error", "message": "Model not loaded."}))]

    from crop_mcp.server import CompareRegionsInput

    v = CompareRegionsInput(**kwargs)

    region_list = [r.strip().upper() for r in v.regions.split(",") if r.strip()]
    crop_list = [c.strip().lower() for c in v.crops.split(",") if c.strip()]

    if len(region_list) < 2:
        return [types.TextContent(type="text", text=json.dumps({"status": "error", "message": "At least 2 regions required."}))]
    if len(region_list) > 20:
        return [types.TextContent(type="text", text=json.dumps({"status": "error", "message": "Max 20 regions."}))]

    results = []
    errors = []

    for region_code in region_list:
        try:
            reg = get_region(region_code)
            country = reg.country
        except KeyError:
            errors.append({"region": region_code, "error": "unknown_region"})
            continue

        for crop in crop_list:
            try:
                gdd = 1400 if crop in ("wheat", "barley") else 1600 if crop == "corn" else 1200
                precip = 350

                r = predict_europe_yield(region_code, country, crop=crop,
                                         gdd=gdd, precip_mm=precip)

                y = r.get("predicted_yield_t_ha", 0)
                p10 = r.get("p10", y * 0.8)
                p90 = r.get("p90", y * 1.2)
                baseline = r.get("model_info", {}).get("baseline_yield_t_ha", y)
                mae_pct = r.get("model_info", {}).get("cv_mae_pct", 15)
                samples = r.get("model_info", {}).get("n_samples", 0)

                # Try NDVI correction
                try:
                    reg_obj = get_region(region_code)
                    _apply_ndvi_correction(r, region_code, reg_obj.latitude, reg_obj.longitude, crop)
                    y_corrected = r.get("predicted_yield_t_ha", y)
                    ndvi_info = r.get("ndvi_correction", {})
                except Exception:
                    y_corrected = y
                    ndvi_info = {"applied": False}

                # Market value
                market_val = None
                market_price = None
                if _HAS_MARKET_PRICES:
                    try:
                        _rev = calculate_revenue(y_corrected, crop, country=country)
                        if isinstance(_rev, dict):
                            market_val = _rev.get("revenue_eur_per_ha")
                            market_price = _rev.get("price_eur_per_t")
                    except Exception:
                        pass

                results.append({
                    "region": region_code,
                    "region_name": reg_obj.name if 'reg_obj' in dir() else reg.name,
                    "country": country,
                    "crop": crop,
                    "predicted_yield_t_ha": round(y_corrected, 3),
                    "risk_range_t_ha": [round(p10, 3), round(p90, 3)],
                    "baseline_t_ha": round(baseline, 3),
                    "mae_pct": mae_pct,
                    "n_training_samples": samples,
                    "market_value_eur_per_ha": market_val,
                    "price_eur_per_t": market_price,
                    "ndvi_correction_applied": ndvi_info.get("applied", False),
                })
            except Exception as e:
                errors.append({"region": region_code, "crop": crop, "error": str(e)[:100]})

    # Sort by yield descending
    results.sort(key=lambda x: x["predicted_yield_t_ha"], reverse=True)

    lang = v.language or _DEFAULT_LANGUAGE
    summary_parts = []
    if results:
        best = results[0]
        best_price = f" @ {best['price_eur_per_t']}€/t" if best.get('price_eur_per_t') else ""
        summary_parts.append(f"Best: {best['crop']} in {best['region']} ({best['region_name']}) — {best['predicted_yield_t_ha']:.2f} t/ha" +
                            (f" — {best['market_value_eur_per_ha']:.0f}€/ha{best_price}" if best['market_value_eur_per_ha'] else ""))
        if len(results) > 1:
            worst = results[-1]
            summary_parts.append(f"Worst: {worst['crop']} in {worst['region']} ({worst['region_name']}) — {worst['predicted_yield_t_ha']:.2f} t/ha")

    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "results": results,
        "errors": errors,
        "summary": "; ".join(summary_parts),
        "parameters": {
            "regions": region_list,
            "crops": crop_list,
            "year": v.year,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, indent=2))]


def _handle_portfolio_optimizer(**kwargs: Any) -> list[types.TextContent]:
    """Optimize a crop investment portfolio — pure AI-for-AI decision support."""
    from crop_mcp.server import PortfolioOptimizerInput

    v = PortfolioOptimizerInput(**kwargs)

    # Determine regions and crops to scan
    try:
        from crop_mcp.core.regions import REGIONS
        all_region_codes = list(REGIONS.keys())
    except ImportError:
        all_region_codes = ["DEE0", "DEF0", "UKH1", "NL11", "FRB0", "RO11", "DK01", "DE80", "PL12"]

    all_crops = ["wheat", "barley", "corn", "rapeseed", "sunflower"]

    region_list = [r.strip().upper() for r in v.regions.split(",") if r.strip()] if v.regions else all_region_codes[:15]
    crop_list = [c.strip().lower() for c in v.crops.split(",") if c.strip()] if v.crops else all_crops
    region_list = region_list[:15]

    # Get predictions via compare_regions
    try:
        res = _handle_compare_regions(regions=",".join(region_list), crops=",".join(crop_list), year=v.year)
        data = json.loads(res[0].text)
        predictions = data.get("results", [])
    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({"status": "error", "message": str(e)[:200]}))]

    if not predictions:
        return [types.TextContent(type="text", text=json.dumps({"status": "error", "message": "No predictions."}))]

    # Calculate profitability
    opportunities = []
    for p in predictions:
        crop = p["crop"]
        country = p.get("country", "")
        yield_t_ha = p["predicted_yield_t_ha"]
        revenue = p.get("market_value_eur_per_ha", 0) or 0
        cost = _get_crop_cost(crop, country)
        margin = revenue - cost
        roi_pct = round((margin / cost) * 100, 1) if cost > 0 else 0

        mae = p.get("mae_pct", 15)
        n_samples = p.get("n_training_samples", 0)
        ndvi = p.get("ndvi_correction_applied", False)
        risk_base = mae * 5
        sample_bonus = max(0, (1000 - n_samples) / 20) if n_samples < 1000 else 0
        ndvi_bonus = 5 if ndvi else 0
        risk_score = min(100, risk_base + sample_bonus - ndvi_bonus)

        risk_factor = {"conservative": 0.8, "moderate": 1.0, "aggressive": 1.3}.get(v.risk_tolerance, 1.0)
        risk_adjusted_margin = margin * (1 - (risk_score / 100) * (0.5 / risk_factor))

        opportunities.append({
            "region": p["region"], "region_name": p.get("region_name", ""), "country": p.get("country", ""),
            "crop": crop, "yield_t_ha": round(yield_t_ha, 2),
            "price_eur_t": p.get("price_eur_per_t", 0) or 0,
            "revenue_eur_ha": round(revenue), "cost_eur_ha": cost,
            "margin_eur_ha": round(margin), "roi_pct": roi_pct,
            "risk_score": round(risk_score, 1),
            "risk_adjusted_margin": round(risk_adjusted_margin, 0),
            "ndvi_corrected": ndvi, "n_training_samples": n_samples,
        })

    # Filter by risk tolerance
    if v.risk_tolerance == "conservative":
        opportunities = [o for o in opportunities if o["risk_score"] < 50 and o["margin_eur_ha"] > 0]
    elif v.risk_tolerance == "moderate":
        opportunities = [o for o in opportunities if o["margin_eur_ha"] > -100]

    opportunities.sort(key=lambda x: x["risk_adjusted_margin"], reverse=True)

    # Build allocation
    remaining = v.budget_eur
    allocation = []
    total_margin = 0
    total_ha = 0
    max_pos = {"conservative": 3, "moderate": 5, "aggressive": 7}.get(v.risk_tolerance, 5)

    for opp in opportunities[:max_pos]:
        if remaining <= 0:
            break
        ha = max(1, int(remaining * 0.2 / opp["cost_eur_ha"])) if opp["cost_eur_ha"] > 0 else 1
        inv = ha * opp["cost_eur_ha"]
        if inv > remaining:
            ha = max(1, int(remaining / opp["cost_eur_ha"]))
            inv = ha * opp["cost_eur_ha"]
        allocation.append({
            "region": opp["region"], "region_name": opp["region_name"], "country": opp["country"],
            "crop": opp["crop"], "hectares": ha, "cost_eur": inv,
            "expected_margin_eur": round(ha * opp["margin_eur_ha"]),
            "roi_pct": opp["roi_pct"], "risk_score": opp["risk_score"],
        })
        remaining -= inv
        total_margin += ha * opp["margin_eur_ha"]
        total_ha += ha

    invested = v.budget_eur - remaining
    portfolio_roi = round((total_margin / invested) * 100, 1) if invested > 0 else 0

    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "portfolio": {
            "total_budget_eur": round(v.budget_eur),
            "total_invested_eur": round(invested),
            "remaining_budget_eur": round(remaining),
            "total_hectares": total_ha,
            "expected_total_margin_eur": round(total_margin),
            "portfolio_roi_pct": portfolio_roi,
            "risk_tolerance": v.risk_tolerance,
        },
        "allocation": allocation,
        "top_opportunities": [{
            "rank": i + 1, "region": o["region"], "region_name": o["region_name"],
            "country": o["country"], "crop": o["crop"],
            "margin_eur_ha": o["margin_eur_ha"],
            "risk_adjusted_margin": o["risk_adjusted_margin"],
            "roi_pct": o["roi_pct"], "risk_score": o["risk_score"],
        } for i, o in enumerate(opportunities[:10])],
        "parameters": {"budget_eur": v.budget_eur, "risk_tolerance": v.risk_tolerance, "year": v.year},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, indent=2))]
