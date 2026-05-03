# Changelog — CropProphEU

## 2026-05-03

### Added
- HTTPS-Server (Port 8443, self-signed cert) für Smithery-Scan
- `/.well-known/mcp/server-card.json` Endpoint (10 Tools)
- `start_http.py` und `start_https.py` Wrapper-Skripte
- Automatischer Health-Check Cron-Job (alle 2 Tage)
- Telegram Bot für Crop + Drug Intelligence (/home/j/bots/telegram_bot.py)
- Optimierungs-Cron (wöchentlich): Data-Source-Scan + Verbesserungsvorschläge

### Fixed
- `pyproject.toml` build-backend korrigiert (setuptools.build_meta)
- Dockerfile CMD auf HTTP-Modus geändert

### Changed
- Smithery-Registry: von `janick/CropProphEU` → `crop-mcp/CropProphEU`

## 2026-05-02

### Added
- `yield_and_value` Tool: Ertrag + Marktwert in €/ha mit deutscher Klartext-Zusammenfassung
- `market_prices.py`: Live CBOT-Futures via Yahoo Finance (wheat ZW=F, corn ZC=F)
- Human-readable weather interpretation (kühl/warm, trocken/nass, feucht)
- Historischer Vergleich in jeder Ausgabe (vs Vorjahr, vs 5-J-Mittel)
- CHANGELOG.md

## 2026-05-01

### Fixed
- Eurostat crop codes korrigiert: corn C1500, barley C1300 (waren fälschlich C1100 wheat)
- Alle per-crop Modelle neu trainiert mit korrekten Zielvariablen

### Added
- 3 verifizierte Kulturen: wheat (C1100), corn (C1500), barley (C1300)
- Rapeseed/Sunflower rejected mit klarem Error (keine Eurostat-Daten)

## 2026-04-30

### Added
- Climate What-If Szenarien (+2°C, -20% Regen)
- Yield-at-Risk (P10/P50/P90)
- EU27 Expansion (25 Länder, 120 NUTS2-Regionen)
- SoilGrids + LUCAS Texture (7 Boden-Features)
- Feature Cache für sub-second historische Vergleiche

## 2026-04-29

### Added
- Erstes Release: crop-mcp V3 — Analog-Year Yield Simulator
- Europäisches Random Forest Modell (11 Länder)
- NASA POWER + Open-Meteo Datenquellen
- MCP-Server mit 6 Tools
