"""Yield forecast, prediction, and scenario handler functions for crop-mcp."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

import mcp.types as types

from crop_mcp.core.regions import get_region, get_crop
from crop_mcp.sources.weather import get_forecast
from crop_mcp.simulate_yield import simulate_yield
from crop_mcp.tools.helpers import (
    _apply_ndvi_correction,
    _analyze_frost_outlook,
    _get_season_dates,
    _describe_gdd_en,
    _describe_precip_en,
    _describe_gdd,
    _describe_precip,
)

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
    from crop_mcp.market_prices import calculate_revenue, get_market_price, REFERENCE_PRICES
    _HAS_MARKET_PRICES = True
except Exception:
    pass

_DEFAULT_LANGUAGE = __import__("os").environ.get("CROP_LANGUAGE", "de")

# Cache for training data (loaded once per crop)
_TRAINING_CACHE: dict = {}
CROP_NAMES = {"de": {"wheat": "Weizen", "corn": "Mais", "barley": "Gerste"},
              "en": {"wheat": "Wheat", "corn": "Corn", "barley": "Barley"}}

_DESCRIBE_GDD = {"de": _describe_gdd, "en": _describe_gdd_en}
_DESCRIBE_PRECIP = {"de": _describe_precip, "en": _describe_precip_en}


def _load_training_cached(crop: str) -> list:
    if crop not in _TRAINING_CACHE:
        import os as _os
        base = "/home/j/crop-mcp/data"
        if crop == "wheat":
            path = _os.path.join(base, "europe_training_data.json")
        else:
            path = _os.path.join(base, f"europe_training_data_{crop}.json")
        if _os.path.exists(path):
            with open(path) as _f:
                _TRAINING_CACHE[crop] = json.load(_f)
        else:
            _TRAINING_CACHE[crop] = []
    return _TRAINING_CACHE[crop]


def _get_crop_comparison(crop: str, region: str) -> dict:
    data = _load_training_cached(crop)
    region_samples = [s for s in data if s.get("region") == region]
    if not region_samples:
        country = data[0].get("country", "DE") if data else "DE"
        region_samples = [s for s in data if s.get("country") == country]
    if not region_samples:
        return {"status": "no_data"}

    sorted_samples = sorted(region_samples, key=lambda x: x.get("year", 0))
    all_yields = [s["yield_t_ha"] for s in sorted_samples]

    last = sorted_samples[-1]
    prev_year_yield = last["yield_t_ha"]
    prev_year = last["year"]

    last5 = sorted_samples[-5:]
    last5_yields = [s["yield_t_ha"] for s in last5]
    mean5 = sum(last5_yields) / len(last5_yields)
    min5 = min(last5_yields)
    max5 = max(last5_yields)

    return {
        "previous_year": {"year": prev_year, "yield_t_ha": prev_year_yield},
        "last_5_years_mean": round(mean5, 2),
        "last_5_years_range": {"min": round(min5, 2), "max": round(max5, 2)},
        "last_5_years_detail": [{s["year"]: round(s["yield_t_ha"], 2)} for s in last5],
        "all_years_available": sorted_samples[0]["year"],
    }


def _build_human_summary(result: dict, language: str = "de") -> str:
    if not result or result.get("status") == "error":
        if language == "en":
            return "No data available."
        return "Keine Daten verfuegbar."
    d = result.get("data", result)
    crop_de = CROP_NAMES.get(language, CROP_NAMES["de"]).get(d.get("crop", ""), d.get("crop", ""))
    region = d.get("region", "?")
    ctry = d.get("country", "?")
    pred = d.get("predicted_yield_t_ha", 0)
    p10 = d.get("p10", 0)
    p90 = d.get("p90", 0)

    if language == "en":
        lines = [f"**{crop_de} – Region {region} ({ctry})**"]
        lines.append(f"Yield: {pred:.2f} t/ha (range {p10:.2f}–{p90:.2f})")
        f = d.get("features_used", {})
        if f:
            lines.append(f"Temperature: {_DESCRIBE_GDD.get(language, _describe_gdd_en)(f.get('gdd',0), d.get('crop',''))}")
            lines.append(f"Precipitation: {_DESCRIBE_PRECIP.get(language, _describe_precip_en)(f.get('precipitation_mm',0), d.get('crop',''))}")
            s = f.get('soil_moisture', 0.5)
            lines.append(f"Soil Moisture: {'wet' if s>0.6 else 'moist' if s>0.4 else 'dry'} ({s:.0%})")
        m = d.get("model_info", {})
        if m:
            mae_pct = m.get('cv_mae_pct', 0)
            lines.append(f"Model error: ±{mae_pct:.1f}% ({m.get('n_samples','?')} samples, {m.get('countries_trained','?')} EU countries)")

        comp = d.get("comparison", {})
        if comp and comp.get("status") != "no_data":
            prev = comp.get("previous_year", {})
            mean5 = comp.get("last_5_years_mean", 0)
            if prev:
                py_yield = prev.get("yield_t_ha", 0)
                py_year = prev.get("year", "?")
                diff = pred - py_yield
                lines.append(f"\nvs {py_year}: {diff:+.2f} t/ha ({'above' if diff>0 else 'below'} last year)")
            if mean5:
                diff5 = pred - mean5
                tag = "above" if diff5 > 0.5 else "below" if diff5 < -0.5 else "within"
                lines.append(f"vs 5-yr avg ({mean5:.2f} t/ha): {diff5:+.2f} t/ha ({tag} of range)")

        mv = d.get("market_value", {})
        if mv and mv.get("revenue_eur_per_ha"):
            rev = mv["revenue_eur_per_ha"]
            lines.append(f"\nRevenue: {rev:,.0f} €/ha (at {mv.get('price_eur_per_t','?')} €/t)")
            mg = mv.get("margin_eur_per_ha")
            if mg is not None:
                lines.append(f"Margin: {mg:,.0f} €/ha")
            lines.append(f"Price basis: {mv.get('price_source','Reference')}")
        return "\n".join(lines)

    # German (default)
    lines = [f"**{crop_de.capitalize()} – Region {region} ({ctry})**"]
    lines.append(f"Ertrag: {pred:.2f} t/ha (Spanne {p10:.2f}–{p90:.2f})")
    f = d.get("features_used", {})
    if f:
        lines.append(f"Temperatur: {_DESCRIBE_GDD.get('de', _describe_gdd)(f.get('gdd',0), d.get('crop',''))}")
        lines.append(f"Niederschlag: {_DESCRIBE_PRECIP.get('de', _describe_precip)(f.get('precipitation_mm',0), d.get('crop',''))}")
        s = f.get('soil_moisture', 0.5)
        lines.append(f"Bodenfeuchte: {'nass' if s>0.6 else 'feucht' if s>0.4 else 'trocken'} ({s:.0%})")
    m = d.get("model_info", {})
    if m:
        mae_pct = m.get('cv_mae_pct', 0)
        lines.append(f"Modellabweichung: ±{mae_pct:.1f}% (aus {m.get('n_samples','?')} Datensätzen, {m.get('countries_trained','?')} EU-Ländern)")

    comp = d.get("comparison", {})
    if comp and comp.get("status") != "no_data":
        prev = comp.get("previous_year", {})
        mean5 = comp.get("last_5_years_mean", 0)
        if prev:
            py_yield = prev.get("yield_t_ha", 0)
            py_year = prev.get("year", "?")
            diff = pred - py_yield
            lines.append(f"\nVergleich zu {py_year}: {diff:+.2f} t/ha ({'über' if diff>0 else 'unter'} Vorjahr)")
        if mean5:
            diff5 = pred - mean5
            lines.append(f"Vergleich zu 5-J-Mittel ({mean5:.2f} t/ha): {diff5:+.2f} t/ha ({'über' if diff5>0.5 else 'unter' if diff5<-0.5 else 'im Rahmen'} des Mittels)")

    mv = d.get("market_value", {})
    if mv and mv.get("revenue_eur_per_ha"):
        rev = mv["revenue_eur_per_ha"]
        lines.append(f"\nErlös: {rev:,.0f} €/ha (bei {mv.get('price_eur_per_t','?')} €/t)")
        mg = mv.get("margin_eur_per_ha")
        if mg is not None:
            lines.append(f"Deckungsbeitrag: {mg:,.0f} €/ha")
        lines.append(f"Preisbasis: {mv.get('price_source','Referenz')}")
    return "\n".join(lines)


def _handle_yield_forecast(**kwargs: Any) -> list[types.TextContent]:
    """Yield forecast using analog-year matching against 25-year climate library."""
    from crop_mcp.server import YieldForecastInput
    validated = YieldForecastInput(**kwargs)

    ref_date = date.today()
    if validated.as_of_date:
        ref_date = date.fromisoformat(validated.as_of_date)

    result = simulate_yield(
        validated.region, validated.crop,
        ref_date.year, ref_date.month, ref_date.day,
    )

    if "error" in result:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "message": result["error"],
        }))]

    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "data": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))]


def _handle_europe_yield_forecast(**kwargs: Any) -> list[types.TextContent]:
    """European yield forecast using Random Forest (3 verified crops, real Eurostat data)."""
    if not _HAS_EUROPE_MODEL:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "message": "European model not loaded. Run build_europe_fast.py first.",
        }))]

    from crop_mcp.server import EuropeanYieldForecastInput
    from crop_mcp.europe_model_api import predict_europe_yield, get_available_countries
    from crop_mcp.tools.weather import _handle_crop_forecast

    validated = EuropeanYieldForecastInput(**kwargs)

    try:
        region = get_region(validated.region)
        country = region.country
    except KeyError:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "message": f"Unknown region: {validated.region}",
        }))]

    # Get features from crop_forecast if not explicitly provided
    if validated.gdd is not None and validated.precipitation_mm is not None:
        gdd = validated.gdd
        precip = validated.precipitation_mm
        solar = 5.0
        soil_m = 0.5
    else:
        try:
            fc = _handle_crop_forecast(crop=validated.crop, region=validated.region)
            fc_data = json.loads(fc[0].text).get("data", {})
            gdd = fc_data.get("gdd", {}).get("accumulated", 1300)
            precip = fc_data.get("precipitation_mm", {}).get("accumulated", 350)
            solar = fc_data.get("solar_radiation", {}).get("current", 5.0) or 5.0
            soil_m = fc_data.get("soil_moisture", {}).get("current", 0.5) or 0.5
        except Exception:
            gdd, precip, solar, soil_m = 1300, 350, 5.0, 0.5

    available = get_available_countries()
    result = predict_europe_yield(validated.region, country, crop=validated.crop,
                                  gdd=gdd, precip_mm=precip, solar_kwh=solar,
                                  soil_moisture=soil_m)

    result["available_countries"] = available
    result["features_used"] = {
        "gdd": round(gdd, 1),
        "precipitation_mm": round(precip, 1),
        "solar_kwh": round(solar, 2),
        "soil_moisture": round(soil_m, 3),
    }

    # V5.1: NDVI satellite correction
    try:
        _apply_ndvi_correction(result, validated.region, region.latitude, region.longitude, validated.crop)
    except Exception:
        result["ndvi_correction"] = {"applied": False, "reason": "exception_during_correction"}

    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "data": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))]


def _handle_yield_and_value(**kwargs: Any) -> list[types.TextContent]:
    """Combined yield forecast + market value estimation."""
    if not _HAS_EUROPE_MODEL:
        return [types.TextContent(type="text", text=json.dumps({"status": "error", "message": "Model not loaded."}))]

    from crop_mcp.server import YieldAndValueInput
    from crop_mcp.europe_model_api import predict_europe_yield
    from crop_mcp.market_prices import calculate_revenue
    from crop_mcp.tools.weather import _handle_crop_forecast

    v = YieldAndValueInput(**kwargs)
    try:
        reg = get_region(v.region)
        cnt = reg.country
    except KeyError:
        return [types.TextContent(type="text", text=json.dumps({"status": "error", "message": f"Unknown region: {v.region}"}))]

    gdd = v.gdd
    pr = v.precipitation_mm
    if gdd is None or pr is None:
        try:
            fc = _handle_crop_forecast(crop=v.crop, region=v.region)
            j = json.loads(fc[0].text).get("data", {})
            if gdd is None:
                gdd = j.get("gdd", {}).get("accumulated", 1300)
            if pr is None:
                pr = j.get("precipitation_mm", {}).get("accumulated", 350)
        except Exception:
            gdd = gdd or 1300
            pr = pr or 350
    solar, soil_m = 5.0, 0.5
    r = predict_europe_yield(v.region, cnt, crop=v.crop, gdd=gdd, precip_mm=pr, solar_kwh=solar, soil_moisture=soil_m)
    if _HAS_MARKET_PRICES:
        r["market_value"] = calculate_revenue(r.get("predicted_yield_t_ha", 0), v.crop, country=cnt)
    r["features_used"] = {"gdd": round(gdd, 1), "precipitation_mm": round(pr, 1), "solar_kwh": round(solar, 2), "soil_moisture": round(soil_m, 3)}
    r["region"] = v.region
    r["country"] = cnt
    r["crop"] = v.crop

    # V5.1: NDVI satellite correction
    try:
        _apply_ndvi_correction(r, v.region, reg.latitude, reg.longitude, v.crop)
        if _HAS_MARKET_PRICES and r.get("ndvi_correction", {}).get("applied"):
            r["market_value"] = calculate_revenue(r.get("predicted_yield_t_ha", 0), v.crop, country=cnt)
    except Exception:
        r["ndvi_correction"] = {"applied": False, "reason": "exception_during_correction"}

    # V4.7: Frost outlook
    try:
        fc = get_forecast(reg.latitude, reg.longitude, reg.altitude)
        r["frost_outlook"] = _analyze_frost_outlook(
            fc.get("forecast", []),
            get_crop(v.crop).frost_sensitive,
            date.fromisoformat(v.as_of_date) if v.as_of_date else date.today()
        )
    except Exception:
        r["frost_outlook"] = {"forecast_frost_days": 0, "risk_level": "unknown"}

    # Historical comparison
    r["comparison"] = _get_crop_comparison(v.crop, v.region)
    r["country"] = cnt
    r["crop"] = v.crop
    lang = v.language or _DEFAULT_LANGUAGE
    summary = _build_human_summary({"data": r}, language=lang)
    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok", "data": r, "summary": summary, "language": lang,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))]


def _handle_climate_scenario(**kwargs: Any) -> list[types.TextContent]:
    """Climate scenario analysis: what if temperature/precipitation changed?"""
    if not _HAS_EUROPE_MODEL:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error",
            "message": "European model not loaded. Run train_europe.py first.",
        }))]

    from crop_mcp.server import ClimateScenarioInput
    from crop_mcp.europe_model_api import predict_europe_yield
    from crop_mcp.tools.weather import _handle_crop_forecast

    validated = ClimateScenarioInput(**kwargs)

    try:
        region = get_region(validated.region)
        country = region.country
        crop = get_crop(validated.crop)
    except KeyError as e:
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error", "message": str(e),
        }))]

    # Get current season features
    try:
        fc = _handle_crop_forecast(crop=validated.crop, region=validated.region)
        fc_data = json.loads(fc[0].text).get("data", {})
        gdd = fc_data.get("gdd", {}).get("accumulated", 1300)
        precip = fc_data.get("precipitation_mm", {}).get("accumulated", 350)
        solar = fc_data.get("solar_radiation", {}).get("current", 5.0) or 5.0
        soil_m = fc_data.get("soil_moisture", {}).get("current", 0.5) or 0.5
    except Exception:
        gdd, precip, solar, soil_m = 1300, 350, 5.0, 0.5

    # Apply climate shifts
    from datetime import date as _date
    _today = _date.today()
    _season_progress = min(1.0, (_today - _date(_today.year, 1, 1)).days / 365.0)

    season_days = 270
    days_so_far = season_days * _season_progress
    days_remaining = season_days - days_so_far
    gdd_shift = validated.temp_shift_C * days_remaining
    gdd_scenario = gdd + max(0, gdd_shift)

    precip_scenario = precip * (1 + validated.precip_shift_pct / 100.0)

    # Base prediction (current)
    base = predict_europe_yield(
        validated.region, country, crop=validated.crop,
        gdd=gdd, precip_mm=precip, solar_kwh=solar, soil_moisture=soil_m
    )

    # Scenario prediction
    scenario = predict_europe_yield(
        validated.region, country, crop=validated.crop,
        gdd=gdd_scenario, precip_mm=precip_scenario, solar_kwh=solar, soil_moisture=soil_m
    )

    # Calculate impact
    impact = round(scenario["predicted_yield_t_ha"] - base["predicted_yield_t_ha"], 2)

    return [types.TextContent(type="text", text=json.dumps({
        "status": "ok",
        "data": {
            "region": validated.region,
            "country": country,
            "crop": validated.crop,
            "scenario": {
                "name": validated.scenario_name or f"{validated.temp_shift_C:+.0f}°C, {validated.precip_shift_pct:+.0f}% precip",
                "temp_shift_C": validated.temp_shift_C,
                "precip_shift_pct": validated.precip_shift_pct,
            },
            "current": {
                "gdd": round(gdd, 1),
                "precipitation_mm": round(precip, 1),
                "predicted_yield_t_ha": base["predicted_yield_t_ha"],
                "p10": base["p10"],
                "p90": base["p90"],
            },
            "scenario_outcome": {
                "gdd": round(gdd_scenario, 1),
                "precipitation_mm": round(precip_scenario, 1),
                "predicted_yield_t_ha": scenario["predicted_yield_t_ha"],
                "p10": scenario["p10"],
                "p90": scenario["p90"],
            },
            "impact": {
                "yield_change_t_ha": impact,
                "yield_change_pct": round(impact / max(base["predicted_yield_t_ha"], 0.01) * 100, 1),
                "direction": "increase" if impact > 0 else "decrease" if impact < 0 else "no change",
            },
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))]
