#!/usr/bin/env python3
"""
CropProphEU Monthly Outlook — automatische Finanzanalyse.
Läuft als Cron-Job am 2. jedes Monats um 06:00 UTC.
Zieht live Predictions + Live-Marktpreise, vergleicht mit Historie (Eurostat 2019-2024).
"""
import json, sys, os
sys.path.insert(0, '/home/j/crop-mcp')
from crop_mcp.market_prices import get_market_price
from crop_mcp.server import _handle_compare_regions

# ── Live-Marktpreise ──
PRICES = {}
PRICE_SOURCES = {}
for c in ['wheat','corn','barley','rapeseed']:
    p = get_market_price(c)
    PRICES[c] = p['price_eur_per_t']
    PRICE_SOURCES[c] = '🔴 LIVE' if p.get('live_quote') else '📖 REF'

COSTS = {'wheat': 650, 'barley': 600, 'corn': 700, 'rapeseed': 780}
REGIONS = ['DEE0','DEF0','UKH1']
CROPS = ['wheat','barley','corn','rapeseed']
REGION_NAMES = {'DEE0':'Sachsen-Anhalt','DEF0':'Schleswig-Holstein','UKH1':'East of England'}

# ── Aktuelle Predictions (live) ──
res = _handle_compare_regions(regions=','.join(REGIONS), crops=','.join(CROPS), year=2026)
predictions = {}
for r in json.loads(res[0].text)['results']:
    predictions[(r['region'], r['crop'])] = r

# ── Historische Eurostat-Daten ──
data_all = {}
for crop, fname in [('wheat','europe_training_data.json'),('barley','europe_training_data_barley.json'),
                    ('corn','europe_training_data_corn.json'),('rapeseed','europe_training_data_rapeseed.json')]:
    with open(f'/home/j/crop-mcp/{fname}') as f:
        data_all[crop] = json.load(f)

# ── Analyse ──
now = __import__('datetime').datetime.now().strftime('%d.%m.%Y %H:%M')
price_line = ' | '.join(f"{c}: {PRICES[c]}€/t {PRICE_SOURCES[c]}" for c in ['wheat','corn','barley','rapeseed'])

print(f"🌾 CROPProphEU — MONATLICHER AUSBLICK")
print(f"📅 {now} UTC")
print(f"💰 {price_line}")
print(f"{'─'*66}")

results = []
for rid in REGIONS:
    for crop in CROPS:
        key = (rid, crop)
        if key not in predictions:
            continue
        
        p = predictions[key]
        pred_y = p['predicted_yield_t_ha']
        price = p.get('price_eur_per_t') or PRICES[crop]  # from tool if available, else local
        cost = COSTS[crop]
        
        samples = [s for s in data_all[crop] if s.get('region','') == rid]
        recent = [s for s in samples if 2019 <= s.get('year',0) <= 2024]
        
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
        
        pred_margin = pred_y * price - cost
        hist_margin = hist_y * price - cost
        delta_pct = ((pred_y - hist_y) / hist_y * 100) if hist_y > 0 else 0
        roi = (pred_margin / cost * 100) if cost > 0 else 0
        ndvi = "✅" if p.get('ndvi_correction_applied', False) else "⬜"
        
        results.append({
            'region': rid, 'crop': crop, 'price': price,
            'pred_y': round(pred_y,2), 'hist_y': round(hist_y,2),
            'delta_pct': round(delta_pct,1), 'pred_margin': round(pred_margin),
            'hist_margin': round(hist_margin), 'roi': round(roi),
            'n_hist': n_hist, 'hist_years': hist_years, 'ndvi': ndvi,
        })

# Ranking
results.sort(key=lambda r: r['pred_margin'], reverse=True)
safe = [r for r in results if r['n_hist'] >= 2]
extrap = [r for r in results if r['n_hist'] == 0]

# Tabelle
print(f"\n{'Rang':4s} {'Region':6s} {'Kultur':10s} {'Yield':>7s} {'Δ%':>7s} {'Marge':>8s} {'ROI':>5s} {'NDVI':>5s}")
print(f"{'─'*54}")
for i, r in enumerate(results, 1):
    trend = "🟢" if r['delta_pct'] > -1 else ("🟡" if r['delta_pct'] > -5 else "🔴")
    print(f"{trend}{i:2d}. {r['region']:6s} {r['crop']:10s} {r['pred_y']:5.2f}t {r['delta_pct']:+6.1f}% {r['pred_margin']:6.0f}€ {r['roi']:3d}% {r['ndvi']:5s}")

# Top Investments
print(f"\n🏆 TOP SICHERE INVESTITIONEN (historisch validiert):")
for i, r in enumerate(sorted(safe, key=lambda x: x['pred_margin'], reverse=True)[:3], 1):
    trend = "🟢" if r['delta_pct'] > -1 else ("🟡" if r['delta_pct'] > -5 else "🔴")
    print(f"  {trend} #{i}: {r['region']} {REGION_NAMES[r['region']]} — {r['crop'].upper()}")
    print(f"     Yield {r['pred_y']} t/ha ({r['delta_pct']:+.1f}% vs Historie {r['hist_years']}) | {r['price']}€/t")
    print(f"     Marge: {r['pred_margin']:,} €/ha | ROI: {r['roi']}%")

if extrap:
    print(f"\n⚡ SPEKULATION (keine Trainingsdaten — Extrapolation):")
    for r in extrap:
        print(f"  🔵 {r['region']} {r['crop']:8s} — {r['pred_margin']:,} €/ha Marge ({r['price']}€/t)")

# Allocation
print(f"\n📊 Empfehlung (100 ha):")
total = 0
allocs = []
if safe:
    s1, s2 = safe[:2] if len(safe) >= 2 else (safe[0], safe[0])
    allocs = [(s1, 50), (s2, 30)]
    if extrap:
        allocs.append((extrap[0], 20))
    elif len(safe) >= 3:
        allocs.append((safe[2], 20))

for r, ha in allocs:
    subtotal = ha * r['pred_margin']
    print(f"  {r['region']} {r['crop']:8s} {ha:3d} ha × {r['pred_margin']:,} €/ha = {subtotal:>6,} €")
    total += subtotal

print(f"  {'':19} {'───':>3s}   {'──────':>6s}")
print(f"  {'':19} Gesamt: {total:>6,} €")
print(f"  Ø Marge: {total//100:,} €/ha | ROI: {total//sum(COSTS[r['crop']] for r,_ in allocs)*100 if False else ''}%")

print()
print(f"{'─'*66}")
print(f"V5.1b · Nächster Ausblick: 01.06.2026 | Preise: yfinance (CBOT/MATIF) + Referenzen")
