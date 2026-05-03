#!/usr/bin/env python3
"""
Auto-Update Pipeline für crop-mcp.
Läuft als Cron-Job (z.B. monatlich) und:
1. Prüft Eurostat auf neue Yield-Daten
2. Wenn neue Jahre verfügbar: Features bauen + Modell trainieren + Cache updaten
3. Server neustarten (über systemd oder Signal)

Kein menschlicher Eingriff nötig — alles automatisch.
"""
import json, os, sys, time, subprocess
from datetime import date, datetime

BASE = '/home/j/crop-mcp'
os.chdir(BASE)
sys.path.insert(0, BASE)

LOG_FILE = '/tmp/crop-mcp-auto-update.log'

def log(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{timestamp}] {msg}'
    print(line)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')

# ── Schritt 1: Eurostat-Check ──
log('=== crop-mcp Auto-Update ===')
log('Schritt 1: Prüfe Eurostat auf neue Yield-Daten...')

from build_europe import fetch_eurostat, COUNTRIES

new_data_found = False
total_new_years = 0

for c in COUNTRIES:
    try:
        latest_yields = fetch_eurostat(c)
        latest_year = max(latest_yields.keys())
        
        # Prüfe, ob wir dieses Jahr schon haben
        # Lade aktuelle Training-Daten
        if os.path.exists('europe_training_data.json'):
            with open('europe_training_data.json') as f:
                training = json.load(f)
            existing_years = set(s['year'] for s in training if s['country'] == c)
            new_years = set(latest_yields.keys()) - existing_years
        else:
            new_years = set(latest_yields.keys())
        
        if new_years:
            log(f'  📥 {c}: {len(new_years)} neue Jahre: {sorted(new_years)}')
            new_data_found = True
            total_new_years += len(new_years)
        else:
            log(f'  ✅ {c}: aktuell (bis {latest_year})')
    except Exception as e:
        log(f'  ⚠️  {c}: Fehler — {str(e)[:60]}')

if not new_data_found:
    log(f'✅ Alles aktuell — kein Update nötig.')
    sys.exit(0)

log(f'📦 {total_new_years} neue Yield-Jahre gefunden — starte Update...')

# ── Schritt 2: Cache bauen (fehlende Jahre) ──
log('Schritt 2: Feature-Cache updaten...')
cache_result = subprocess.run(
    [sys.executable, 'build_cache.py'],
    capture_output=True, text=True, timeout=3600
)
for line in cache_result.stdout.strip().split('\n'):
    log(f'  {line}')
if cache_result.returncode != 0:
    log(f'  ❌ Cache-Build fehlgeschlagen (exit {cache_result.returncode})')
    log(f'  {cache_result.stderr[:500]}')
    sys.exit(1)

# ── Schritt 3: Training-Daten bauen ──
log('Schritt 3: Feature-Dataset bauen...')
# Schnell: wir nutzen den Cache + fügen fehlende Jahre hinzu
# build_europe.py macht kompletten Neubau, das ist bekannt und zuverlässig
build_result = subprocess.run(
    [sys.executable, 'build_europe.py'],
    capture_output=True, text=True, timeout=3600
)
for line in build_result.stdout.strip().split('\n'):
    log(f'  {line}')
if build_result.returncode != 0:
    log(f'  ❌ Build fehlgeschlagen (exit {build_result.returncode})')
    log(f'  {build_result.stderr[:500]}')
    sys.exit(1)

# ── Schritt 4: Modell trainieren ──
log('Schritt 4: Modell trainieren...')
train_result = subprocess.run(
    [sys.executable, 'train_europe.py'],
    capture_output=True, text=True, timeout=600
)
for line in train_result.stdout.strip().split('\n'):
    log(f'  {line}')
if train_result.returncode != 0:
    log(f'  ❌ Training fehlgeschlagen (exit {train_result.returncode})')
    log(f'  {train_result.stderr[:500]}')
    sys.exit(1)

# ── Schritt 5: Server neustarten ──
log('Schritt 5: Server neustarten...')

# Option A: systemd
try:
    subprocess.run(['systemctl', 'restart', 'crop-mcp'], check=True, timeout=30, capture_output=True)
    log('  ✅ Server via systemd restartet')
except Exception:
    # Option B: process kill
    try:
        subprocess.run(['pkill', '-f', 'python3.*server.py'], timeout=10)
        log('  ✅ Alte Server-Prozesse gekillt (Hermes startet neu bei Bedarf)')
    except Exception as e:
        log(f'  ⚠️  Server-Neustart nicht möglich: {str(e)[:60]}')

log(f'')
log(f'✅ Auto-Update abgeschlossen — Modell ist auf Stand {date.today()}')
log(f'   Neue Total-Samples: checke')
if os.path.exists('europe_training_data.json'):
    with open('europe_training_data.json') as f:
        final = json.load(f)
    years = sorted(set(s['year'] for s in final))
    log(f'   Jahre: {years[0]}–{years[-1]} ({len(years)} Jahre)')
    log(f'   Samples: {len(final)}')
