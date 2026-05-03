#!/usr/bin/env python3
"""
Market prices for EU crops (€/t) — LIVE via Yahoo Finance + Reference fallback.

Tries multiple live sources (yfinance, public APIs) and falls back to static
reference prices if unavailable. Prices are cached for 1 hour.

Live sources:
  - yfinance: CBOT wheat (ZW=F), corn (ZC=F) + EUR/USD rate
  - Conversion: CBOT price × bushel_factor → USD/t, then USD→EUR with live rate
  - MATIF premium: +35 €/t for wheat (quality), +25 €/t for corn (freight)

Reference prices (fallback):
  - Wheat: 235 €/t (Euronext MATIF Paris, May 2026)
  - Corn: 205 €/t (Euronext MATIF Paris, May 2026)
  - Barley: 190 €/t (AMI regional exchanges, May 2026)
"""

import json, time, os
from datetime import datetime, timedelta
from typing import Optional

# Cache
_PRICE_CACHE: dict = {}
_CACHE_TTL = timedelta(hours=1)  # Refresh prices max once per hour
_CACHE_FILE = "/home/j/crop-mcp/.price_cache.json"

# Bushel → metric ton conversion factors
BU_TO_T_WHEAT = 36.744   # 1 bu = 60 lbs
BU_TO_T_CORN = 39.368    # 1 bu = 56 lbs

# MATIF premium over CBOT (quality + freight differential)
MATIF_PREMIUM = {
    "wheat": 35,   # €/t — milling wheat quality premium
    "corn": 25,    # €/t — freight differential
}

# Reference prices (static fallback)
REFERENCE_PRICES = {
    "wheat": {
        "price_eur_per_t": 235,
        "market": "Euronext MATIF (Paris)",
        "contract": "EBM Z2026 (Dec 2026)",
        "source": "Referenzpreis — MATIF Paris / CBOT Chicago (yfinance)",
        "note": "Brotweizen (mahlfähig), frei Erste-Handelskette",
        "updated": "2026-05-01",
    },
    "corn": {
        "price_eur_per_t": 205,
        "market": "Euronext MATIF (Paris)",
        "contract": "EMA Z2026 (Nov 2026)",
        "source": "Referenzpreis — MATIF Paris / CBOT Chicago (yfinance)",
        "note": "Körnermais, frei Handelsstufe",
        "updated": "2026-05-01",
    },
    "barley": {
        "price_eur_per_t": 190,
        "market": "Regionalbörsen (Mitte Deutschland)",
        "contract": "Futtergerste, frei Hof",
        "source": "AMI / Landwirtschaftskammern",
        "note": "Kein Future-Markt — regionale Erfassungspreise",
        "updated": "2026-05-01",
    },
}

PRODUCTION_COSTS = {
    "wheat": {"min": 500, "max": 800, "average": 650, "note": "Inkl. Saatgut, Dünger, Pflanzenschutz, Ernte"},
    "corn": {"min": 550, "max": 850, "average": 700, "note": "Körnermais, inkl. Trocknungskosten"},
    "barley": {"min": 450, "max": 750, "average": 600, "note": "Futtergerste, extensiver als Weizen"},
}


def get_market_price(crop: str) -> dict:
    """Get current market price — live if possible, with 1h cache."""
    crop = crop.lower()
    if crop not in REFERENCE_PRICES:
        return {"status": "error", "message": f"Keine Preisinformationen für '{crop}'."}
    
    ref = dict(REFERENCE_PRICES[crop])
    
    # Try live price
    live_price = _get_live_price_cached(crop)
    if live_price is not None:
        ref["price_eur_per_t"] = live_price
        ref["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        ref["live_quote"] = True
    else:
        ref["live_quote"] = False
    
    return {
        "status": "ok",
        "crop": crop,
        "price_eur_per_t": ref["price_eur_per_t"],
        "currency": "EUR",
        "market": ref["market"],
        "source": ref["source"],
        "updated": ref["updated"],
        "live_quote": ref["live_quote"],
        "note": ref["note"],
    }


def calculate_revenue(yield_t_ha: float, crop: str, include_costs: bool = True) -> dict:
    """Calculate revenue and margin from yield + market price."""
    price_info = get_market_price(crop)
    if price_info["status"] == "error":
        return price_info
    
    price_per_t = price_info["price_eur_per_t"]
    revenue_eur_ha = round(yield_t_ha * price_per_t, 0)
    
    result = {
        "crop": crop,
        "yield_t_ha": round(yield_t_ha, 2),
        "price_eur_per_t": price_per_t,
        "revenue_eur_per_ha": revenue_eur_ha,
        "calculation": f"{yield_t_ha:.2f} t/ha × {price_per_t} €/t = {revenue_eur_ha:,.0f} €/ha",
        "price_source": price_info["source"],
        "price_updated": price_info["updated"],
        "price_is_live": price_info["live_quote"],
    }
    
    if include_costs and crop in PRODUCTION_COSTS:
        costs = PRODUCTION_COSTS[crop]
        avg_cost = costs["average"]
        margin = revenue_eur_ha - avg_cost
        result["production_costs"] = {
            "estimated_eur_per_ha": avg_cost,
            "range_eur_per_ha": [costs["min"], costs["max"]],
            "note": costs["note"],
        }
        result["margin_eur_per_ha"] = margin
        result["margin_is_positive"] = margin > 0
    
    return result


def _get_live_price_cached(crop: str) -> Optional[float]:
    """Get live price from cache or fetch fresh."""
    global _PRICE_CACHE
    
    # Check in-memory cache
    cached = _PRICE_CACHE.get(crop)
    if cached and cached["ts"] > datetime.now() - _CACHE_TTL:
        return cached["price"]
    
    # Check disk cache
    _load_cache_from_disk()
    cached = _PRICE_CACHE.get(crop)
    if cached and cached["ts"] > datetime.now() - _CACHE_TTL:
        return cached["price"]
    
    # Fetch live
    price = _fetch_live_yfinance(crop)
    if price is not None:
        _PRICE_CACHE[crop] = {"price": price, "ts": datetime.now()}
        _save_cache_to_disk()
        return price
    
    return None


def _fetch_live_yfinance(crop: str) -> Optional[float]:
    """Fetch live futures price from Yahoo Finance, convert to €/t."""
    try:
        import yfinance as yf
        
        if crop == "wheat":
            ticker = yf.Ticker("ZW=F")  # CBOT Wheat
            factor = BU_TO_T_WHEAT
        elif crop == "corn":
            ticker = yf.Ticker("ZC=F")  # CBOT Corn
            factor = BU_TO_T_CORN
        else:
            return None  # Barley has no futures market
        
        hist = ticker.history(period="2d")
        if len(hist) == 0:
            return None
        
        price_cents = hist.iloc[-1]["Close"]  # Yahoo gives USX (cents)
        price_usd_per_bu = price_cents / 100.0
        price_usd_per_t = price_usd_per_bu * factor
        
        # Get EUR/USD rate
        try:
            eur_ticker = yf.Ticker("EURUSD=X")
            eur_hist = eur_ticker.history(period="1d")
            if len(eur_hist) > 0:
                eur_usd = eur_hist.iloc[-1]["Close"]
            else:
                eur_usd = 0.92  # Fallback
        except Exception:
            eur_usd = 0.92
        
        price_eur_per_t = price_usd_per_t / eur_usd
        
        # Apply MATIF premium for European prices
        premium = MATIF_PREMIUM.get(crop, 0)
        price_eur_per_t += premium
        
        return round(price_eur_per_t)
    
    except Exception:
        return None


def _load_cache_from_disk():
    global _PRICE_CACHE
    try:
        with open(_CACHE_FILE) as f:
            data = json.load(f)
        for k, v in data.items():
            v["ts"] = datetime.fromisoformat(v["ts"])
            _PRICE_CACHE[k] = v
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass


def _save_cache_to_disk():
    try:
        data = {}
        for k, v in _PRICE_CACHE.items():
            data[k] = {"price": v["price"], "ts": v["ts"].isoformat()}
        with open(_CACHE_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


if __name__ == "__main__":
    print("=== LIVE MARKET PRICES ===")
    from datetime import datetime as _dt
    for crop in ["wheat", "corn", "barley"]:
        p = get_market_price(crop)
        live = "🔴 LIVE" if p.get("live_quote") else "📖 Referenz"
        print(f"  {crop}: {p['price_eur_per_t']} €/t [{live}] ({p.get('updated','')})")
