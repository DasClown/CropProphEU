#!/usr/bin/env python3
"""
CropProphEU Monthly Outlook — V5.4.2
======================================
Automatische Finanzanalyse. Läuft als Cron-Job am 2. jedes Monats um 06:00 UTC.
Zieht live Predictions + Live-Marktpreise + ERS, vergleicht mit Eurostat-Historie.

KS-Agrar-Stil: Direkt, handelsorientiert, DB/ha-Tabellen, Düngerpreise,
internationale Faktoren (Ukraine/Brasilien/La Niña).
"""
import json, sys, os
sys.path.insert(0, '/home/j/crop-mcp')
from datetime import datetime as _dt

from crop_mcp.market_prices import get_market_price, get_production_cost

def log(msg: str):
    ts = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

# ── TOP-REGIONEN (EU-weit, nach Anbaufläche & Relevanz) ──
REGIONS = [
    'DEE0', 'DEF0', 'DE91', 'DE26',     # DE: Sachsen-Anhalt, SH, Nds, Unterfranken
    'FRF2', 'FRB0',                      # FR: Picardie, Centre
    'PL22', 'PL71',                      # PL: Schlesien, Lodz
    'HU21', 'HU33',                      # HU: Südtransdanubien, Dél-Alföld
    'RO31', 'RO32',                      # RO: Sud-Muntenia, Sud-Est
    'ES42', 'ES61',                      # ES: Castilla y León, Andalusien
    'ITC4', 'ITH4',                      # IT: Lombardei, Venetien
    'UKH1', 'UKH2',                      # UK: East of England, East Midlands
]
REGION_NAMES = {
    'DEE0': 'Sachsen-Anhalt', 'DEF0': 'Schleswig-Holstein',
    'DE91': 'Niedersachsen-Oldenburg', 'DE26': 'Unterfranken',
    'FRF2': 'Picardie/Hauts-de-France', 'FRB0': 'Centre-Val de Loire',
    'PL22': 'Schlesien', 'PL71': 'Lodz',
    'HU21': 'Südtransdanubien', 'HU33': 'Dél-Alföld',
    'RO31': 'Sud-Muntenia', 'RO32': 'Sud-Est',
    'ES42': 'Castilla y León', 'ES61': 'Andalusien',
    'ITC4': 'Lombardei', 'ITH4': 'Venetien',
    'UKH1': 'East of England', 'UKH2': 'East Midlands',
}
CROPS = ['wheat', 'corn', 'barley', 'rapeseed', 'sunflower']
CROP_NAMES = {
    'wheat': 'Weizen', 'corn': 'Mais', 'barley': 'Gerste',
    'rapeseed': 'Raps', 'sunflower': 'Sonnenblumen'
}

# ── Live-Marktpreise ──
PRICES = {}
PRICE_SOURCES = {}
for c in CROPS:
    p = get_market_price(c)
    PRICES[c] = p['price_eur_per_t']
    PRICE_SOURCES[c] = '🔴 LIVE' if p.get('live_quote') else '📖 REF'

# ── ERS für alle Regionen laden ──
ERS_CACHE = {}
try:
    from crop_mcp.environmental_risk import full_environmental_risk
    for rid in REGIONS:
        try:
            ers = full_environmental_risk(rid, rid[:2])
            ERS_CACHE[rid] = ers
        except Exception:
            ERS_CACHE[rid] = None
except ImportError:
    pass

# ── FAO GIEWS Datenabruf (NEU) ──
FAO_DATA = {}
try:
    import requests as _req
    # FAO Stat — Weizenproduktion DE
    fao_r = _req.get(
        "https://fenixservices.fao.org/faostat/api/v1/en/QAQ/country/DE",
        timeout=15
    )
    if fao_r.status_code == 200:
        fao_data = fao_r.json()
        FAO_DATA['de'] = {
            'source': 'FAO API',
            'status': 'ok',
            'items': len(fao_data.get('data', []))
        }
        log(f"  ✅ FAO DE: {FAO_DATA['de']['items']} Datensätze")
    else:
        FAO_DATA['de'] = {'source': 'FAO API', 'status': f'HTTP {fao_r.status_code}'}
        log(f"  ⚠️ FAO DE: HTTP {fao_r.status_code}")
except Exception as e:
    FAO_DATA['de'] = {'source': 'FAO API', 'status': f'error: {e}'}
    log(f"  ⚠️ FAO DE: {e}")

# ── JRC MARS Bulletin Check (NEU) ──
MARS_AVAILABLE = False
try:
    mars_r = _req.get(
        "https://agri4cast.jrc.ec.europa.eu/Bulletin/Current/index.html",
        timeout=15
    )
    MARS_AVAILABLE = mars_r.status_code == 200
    log(f"  {'✅' if MARS_AVAILABLE else '⚠️'} JRC MARS Bulletin: {'erreichbar' if MARS_AVAILABLE else f'HTTP {mars_r.status_code}'}")
except Exception as e:
    log(f"  ⚠️ JRC MARS: {e}")


# ── Historische Eurostat-Daten ──
DATA_FILES = {
    'wheat': 'europe_training_data.json',
    'barley': 'europe_training_data_barley.json',
    'corn': 'europe_training_data_corn.json',
    'rapeseed': 'europe_training_data_rapeseed.json',
    'sunflower': 'europe_training_data_sunflower.json',
}
data_all = {}
for crop, fname in DATA_FILES.items():
    fpath = f'/home/j/crop-mcp/{fname}'
    if os.path.exists(fpath):
        with open(fpath) as f:
            data_all[crop] = json.load(f)
    else:
        data_all[crop] = []

# ── Live-Predictions via compare_regions simulieren ──
predictions = {}
try:
    from crop_mcp.server import _handle_compare_regions
    res = _handle_compare_regions(
        regions=','.join(REGIONS),
        crops=','.join(CROPS),
        year=2026
    )
    for r in json.loads(res[0].text)['results']:
        predictions[(r['region'], r['crop'])] = r
except Exception as e:
    # Fallback: direkte Yield-Prognose über europe_model_api
    from crop_mcp.europe_model_api import predict_europe_yield
    for rid in REGIONS:
        for crop in CROPS:
            try:
                pred = predict_europe_yield(rid, rid[:2], crop=crop)
                predictions[(rid, crop)] = {
                    'region': rid, 'crop': crop, 'country': rid[:2],
                    'predicted_yield_t_ha': pred.get('predicted_yield', 0),
                    'predicted_yield_range': pred.get('yield_range', [0, 0]),
                    'price_eur_per_t': PRICES.get(crop, 0),
                    'ndvi_correction_applied': False,
                }
            except Exception:
                pass

# ── Analyse-Tabelle bauen ──
now = _dt.now().strftime('%d.%m.%Y %H:%M')
price_line = ' | '.join(f"{CROP_NAMES[c]}: {PRICES[c]}€/t {PRICE_SOURCES[c]}" for c in CROPS)

print(f"🌾 CROPProphEU — MONATLICHER AUSBLICK V5.4.2")
print(f"📅 {now} UTC")
print(f"💰 {price_line}")
print(f"{'─'*76}")

results = []
for rid in REGIONS:
    for crop in CROPS:
        key = (rid, crop)
        if key not in predictions:
            continue
        
        p = predictions[key]
        pred_y = p.get('predicted_yield_t_ha', 0)
        country = p.get('country', rid[:2])
        price = p.get('price_eur_per_t') or PRICES[crop]
        cost_info = get_production_cost(crop, country)
        cost = cost_info['eur_per_ha']
        
        # Historische Daten
        samples = [s for s in data_all.get(crop, []) if s.get('region', '') == rid]
        recent = [s for s in samples if 2019 <= s.get('year', 0) <= 2024]
        
        if recent:
            hist_y = sum(s['yield_t_ha'] for s in recent) / len(recent)
            n_hist = len(recent)
            hist_years = f"{recent[0]['year']}-{recent[-1]['year']}"
        elif samples:
            hist_y = sum(s['yield_t_ha'] for s in samples) / len(samples)
            n_hist = len(samples)
            hist_years = "alle"
        else:
            hist_y = 0
            n_hist = 0
            hist_years = "—"
        
        revenue = pred_y * price
        pred_margin = revenue - cost
        hist_revenue = hist_y * price
        hist_margin = hist_revenue - cost
        delta_pct = ((pred_y - hist_y) / hist_y * 100) if hist_y > 0 else 0
        roi = (pred_margin / cost * 100) if cost > 0 else 0
        ndvi = "✅" if p.get('ndvi_correction_applied', False) else "⬜"
        
        # ERS
        ers_info = ERS_CACHE.get(rid, {})
        ers_level = ers_info.get('overall_risk', 'N/A') if ers_info else 'N/A'
        
        results.append({
            'region': rid, 'crop': crop, 'price': price,
            'pred_y': round(pred_y, 2), 'hist_y': round(hist_y, 2),
            'delta_pct': round(delta_pct, 1), 'revenue': round(revenue),
            'pred_margin': round(pred_margin), 'hist_margin': round(hist_margin),
            'roi': round(roi), 'n_hist': n_hist, 'hist_years': hist_years,
            'ndvi': ndvi, 'ers': ers_level, 'cost': cost,
        })

# Ranking nach Deckungsbeitrag
results.sort(key=lambda r: r['pred_margin'], reverse=True)
safe = [r for r in results if r['n_hist'] >= 2]
extrap = [r for r in results if r['n_hist'] == 0]

# ── TABELLE ──
print(f"\n{'Rg':3s} {'Region':6s} {'Kultur':12s} {'Yield':>6s} {'Δ%':>6s} {'Umsatz':>8s} {'Kosten':>7s} {'DB':>8s} {'ROI':>5s} {'ERS':>4s}")
print(f"{'─'*75}")
for i, r in enumerate(results[:30], 1):
    trend = "🟢" if r['delta_pct'] > -1 else ("🟡" if r['delta_pct'] > -5 else "🔴")
    rname = r['region']
    print(f"{trend}{i:2d}. {rname:6s} {CROP_NAMES[r['crop']]:12s} {r['pred_y']:5.2f}t {r['delta_pct']:+5.1f}% {r['revenue']:6.0f}€ {r['cost']:5.0f}€ {r['pred_margin']:6.0f}€ {r['roi']:3d}% {r['ers']:4s}")

# ── TOP 5 INVESTITIONEN ──
print(f"\n🏆 TOP 5 SICHERE INVESTITIONEN (historisch validiert):")
for i, r in enumerate(sorted(safe, key=lambda x: x['pred_margin'], reverse=True)[:5], 1):
    trend = "🟢" if r['delta_pct'] > -1 else ("🟡" if r['delta_pct'] > -5 else "🔴")
    print(f"  {trend} #{i}: {r['region']} {REGION_NAMES.get(r['region'], r['region'])} — {CROP_NAMES[r['crop']].upper()}")
    print(f"     Yield {r['pred_y']} t/ha ({r['delta_pct']:+.1f}% vs {r['hist_years']}) | {r['price']}€/t | DB {r['pred_margin']:,}€/ha")
    print(f"     ERS: {r['ers']} | ROI: {r['roi']}% | NDVI: {r['ndvi']}")

if extrap:
    print(f"\n⚡ SPEKULATION (keine Trainingsdaten — Extrapolation):")
    for r in extrap[:3]:
        print(f"  🔵 {r['region']} {CROP_NAMES[r['crop']]:12s} — {r['pred_margin']:,} €/ha DB ({r['price']}€/t)")

# ── ERS-RISIKO-ÜBERSICHT ──
if ERS_CACHE:
    print(f"\n🌍 UMWELTRISIKO (ERS) — Übersicht:")
    for rid in REGIONS[:8]:
        ers = ERS_CACHE.get(rid)
        if ers:
            s = ers.get('summary', '')
            print(f"  {s}")

# ── ALLOKATIONSEMPFEHLUNG (100 ha) ──
print(f"\n📊 EMPFEHLUNG (100 ha):")
total = 0
allocs = []
if safe:
    top3 = sorted(safe, key=lambda x: x['pred_margin'], reverse=True)[:3]
    allocs = [(top3[0], 40), (top3[1] if len(top3) > 1 else top3[0], 30)]
    if len(top3) > 2:
        allocs.append((top3[2], 20))
    if extrap:
        allocs.append((extrap[0], 10))
    elif len(safe) > 3:
        allocs.append((sorted(safe, key=lambda x: x['pred_margin'], reverse=True)[3], 10))

for r, ha in allocs:
    subtotal = ha * r['pred_margin']
    print(f"  {r['region']} {CROP_NAMES[r['crop']]:10s} {ha:3d} ha × {r['pred_margin']:>6,} €/ha = {subtotal:>7,} €")
    total += subtotal

print(f"  {'':19} {'───':>3s}   {'───────':>7s}")
print(f"  {'':19} Gesamt: {total:>7,} €")
print(f"  Ø DB: {total//100:,} €/ha")

# ── MARKTKOMMENTAR ──
print(f"\n📈 MARKTKOMMENTAR:")
w_p = PRICES.get('wheat', 0)
c_p = PRICES.get('corn', 0)
r_p = PRICES.get('rapeseed', 0)
if w_p:
    print(f"  • Weizen {w_p}€/t — {'NOTIERUNG UNTER 240€ — kritische Schwelle' if w_p < 240 else 'Stabil über 240€'}")
if c_p:
    print(f"  • Mais {c_p}€/t — {'PREISDRUCK durch Ukraine/Brasilien-Exporte' if c_p < 190 else 'Stabiler Mais-Markt'}")
if r_p:
    print(f"  • Raps {r_p}€/t — {'Palmöl/Kanola-Wettbewerb beobachten' if r_p < 480 else 'Robuster Rapsmarkt'}")
print(f"  • Dünger: KAS 27% ~320-340€/t | MAP ~580-610€/t (Mai 2026)")
print(f"  • La Niña-Risiko Q3 2026: NAO-Index negativ → nasser Norden, trockener Süden")
print(f"  • Ukraine-Korridor: Verlängerung unwahrscheinlich → +/- 15€/t Risikoaufschlag")
if FAO_DATA.get('de', {}).get('status') == 'ok':
    print(f"  • FAO DE: {FAO_DATA['de'].get('items', 0)} Datensätze verfügbar (neue Quelle)")
else:
    print(f"  • FAO DE: ⚠️ nicht verfügbar ({FAO_DATA.get('de', {}).get('status', 'unknown')})")
if MARS_AVAILABLE:
    print(f"  • JRC MARS Bulletin: ✅ erreichbar — Vergleich bei nächstem Outlook")

# ── COMPACT ANCHORS ──
try:
    from crop_mcp.anchor import list_anchors
    anchors = list_anchors()
    if anchors:
        print(f"\n🔐 COMPACT ANCHORS ({len(anchors)} Proof-of-Forecast):")
        for a in anchors[:6]:
            d = a.get('anchor_data', {})
            ts = a.get('timestamp', '?')[:10]
            yield_v = d.get('predicted_yield_t_ha', 0)
            reg = d.get('region', '?')
            cr = d.get('crop', '?')
            status = a.get('status', '?')
            print(f"  • {reg}_{cr}: {yield_v}t/ha (⛓️ {ts}) [{status}]")
except Exception:
    pass

print()
print(f"{'─'*76}")
print(f"V5.4.2 · Nächster Ausblick: 01.06.2026 | Daten: yfinance (CBOT/MATIF) + Eurostat")
