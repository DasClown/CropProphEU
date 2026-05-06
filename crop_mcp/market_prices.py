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
        "price_eur_per_t": 239,
        "market": "Euronext MATIF (Paris)",
        "contract": "EBM Z2026 (Dec 2026)",
        "source": "Referenzpreis — MATIF Paris / CBOT Chicago (yfinance)",
        "note": "Brotweizen (mahlfähig), frei Erste-Handelskette",
        "updated": "2026-05-05",
    },
    "corn": {
        "price_eur_per_t": 189,
        "market": "Euronext MATIF (Paris)",
        "contract": "EMA Z2026 (Nov 2026)",
        "source": "Referenzpreis — MATIF Paris / CBOT Chicago (yfinance)",
        "note": "Körnermais, frei Handelsstufe — MARKT GEFALLEN (CBOT Mai 2026)",
        "updated": "2026-05-05",
    },
    "barley": {
        "price_eur_per_t": 190,
        "market": "Regionalbörsen (Mitte Deutschland)",
        "contract": "Futtergerste, frei Hof",
        "source": "AMI / Landwirtschaftskammern",
        "note": "Kein Future-Markt — regionale Erfassungspreise",
        "updated": "2026-05-05",
    },
    "rapeseed": {
        "price_eur_per_t": 470,
        "market": "Euronext MATIF (Paris)",
        "contract": "ECO (Rapeseed Futures)",
        "source": "Referenzpreis — MATIF Paris (yfinance)",
        "note": "Winterraps, frei Ölmühle",
        "updated": "2026-05-05",
    },
    "sunflower": {
        "price_eur_per_t": 420,
        "market": "ICE Futures Europe / Regional",
        "contract": "Sunflower seed (Black Sea reference)",
        "source": "Black Sea / Argus Media reference",
        "note": "Sonnenblumenkerne, frei Ölmühle",
        "updated": "2026-05-05",
    },
}

# Country-specific production costs (€/ha) per crop
# Sources: FADN, KTBL (DE), ARVALIS (FR), AHDB (UK), EU-Kommission Agrarausblick
COUNTRY_PRODUCTION_COSTS = {
    "wheat": {
        "default": 650,
        "note": "Inkl. Saatgut, Dünger, Pflanzenschutz, Ernte",
        "by_country": {
            # Western Europe — high input
            "NL": 950, "BE": 850, "DK": 800, "IE": 750,
            # Northern Europe
            "FI": 700, "SE": 700,
            # Central/Western
            "DE": 680, "UK": 700, "AT": 650,
            # Southern
            "FR": 620, "IT": 700, "ES": 450, "PT": 450, "EL": 480,
            # Central-Eastern
            "CZ": 550, "SI": 550, "SK": 480, "HU": 480,
            # Eastern
            "PL": 450, "HR": 420, "LT": 420, "EE": 400, "LV": 400,
            # Balkans
            "BG": 380, "RO": 380,
            # Eastern Europe
            "UA": 300,
            # Mediterranean
            "CY": 450, "MT": 550,
        },
        "range_eur_per_ha": [250, 1200],
    },
    "corn": {
        "default": 700,
        "note": "Körnermais, inkl. Trocknungskosten",
        "by_country": {
            "NL": 1000, "BE": 900, "DK": 850, "DE": 750, "FR": 680,
            "IT": 800, "ES": 500, "PL": 500, "HU": 520, "RO": 420,
            "BG": 420, "UA": 350, "AT": 700, "CZ": 600, "SK": 520,
        },
        "range_eur_per_ha": [300, 1200],
    },
    "barley": {
        "default": 600,
        "note": "Futtergerste, extensiver als Weizen",
        "by_country": {
            "NL": 850, "BE": 780, "DK": 750, "DE": 620, "FR": 560,
            "PL": 400, "CZ": 500, "AT": 580, "ES": 400, "UK": 620,
            "SE": 620, "FI": 620, "IE": 680, "UA": 280,
        },
        "range_eur_per_ha": [250, 1000],
    },
    "rapeseed": {
        "default": 780,
        "note": "Winterraps, hohe Dünger- & Pflanzenschutzkosten",
        "by_country": {
            "DE": 800, "FR": 750, "PL": 550, "UK": 800, "CZ": 650,
            "AT": 750, "DK": 850, "HU": 580, "RO": 480, "BG": 480,
            "UA": 380,
        },
        "range_eur_per_ha": [350, 1100],
    },
    "sunflower": {
        "default": 650,
        "note": "Sonnenblumen, extensiver als Raps (weniger Dünger)",
        "by_country": {
            "FR": 600, "ES": 420, "IT": 600, "RO": 380, "BG": 380,
            "HU": 450, "UA": 300, "EL": 420, "PT": 400,
        },
        "range_eur_per_ha": [250, 900],
    },
}

# Legacy flat PRODUCTION_COSTS — kept for backwards compatibility
PRODUCTION_COSTS = {
    crop: {"min": info["range_eur_per_ha"][0], "max": info["range_eur_per_ha"][1],
           "average": info["default"], "note": info["note"]}
    for crop, info in COUNTRY_PRODUCTION_COSTS.items()
}


def get_production_cost(crop: str, country: str = None) -> dict:
    """Get production cost for a crop, optionally country-specific.
    
    Returns dict with 'eur_per_ha', 'range', 'note'.
    Falls back to default if country not found.
    """
    crop = crop.lower()
    info = COUNTRY_PRODUCTION_COSTS.get(crop, PRODUCTION_COSTS.get(crop))
    if info is None:
        return {"eur_per_ha": 650, "range": [300, 1000], "note": "Geschätzt"}
    
    if country and "by_country" in info:
        by_country = info["by_country"]
        # Normalize: try as-is, then 2-letter, then uppercase
        cost = by_country.get(country.upper())
        if cost is None:
            cost = by_country.get(country[:2].upper(), info["default"])
        return {
            "eur_per_ha": cost,
            "range": info.get("range_eur_per_ha", [300, 1000]),
            "note": info["note"],
        }
    
    return {
        "eur_per_ha": info["default"],
        "range": info.get("range_eur_per_ha", [300, 1000]),
        "note": info["note"],
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


def calculate_revenue(yield_t_ha: float, crop: str, include_costs: bool = True,
                     country: str = None) -> dict:
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
        cost_info = get_production_cost(crop, country)
        avg_cost = cost_info["eur_per_ha"]
        margin = revenue_eur_ha - avg_cost
        result["production_costs"] = {
            "estimated_eur_per_ha": avg_cost,
            "country_specific": country if country else False,
            "range_eur_per_ha": cost_info["range"],
            "note": cost_info["note"],
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
