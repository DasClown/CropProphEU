# Changelog — CropProphEU

## 2026-05-04 — V4.8

### Added
- **Modell-Retrain mit V4.7 Soil-Features**: Alle 3 Modelle (wheat, corn, barley) mit bdod, cfvo, coarse_pct, awc_mm_m neu gebaut + trainiert
- **Frost Outlook** auch in `yield_and_value` Tool
- `run_pipeline_v2.py`: Automatisierte Build+Train Sequenz für alle Kulturen

### Changed
- `build_europe.py`: 4 neue Soil-Features in Trainingsdaten (17 statt 13 Feature-Spalten)
- `train_europe_fast.py`: `NUM_FEATURES` auf 17 Features erweitert
- `europe_model_api.py`: Akzeptiert 4 neue Soil-Parameter, lädt sie aus dem Cache
- `soil_cache.json` → `data/` kopiert für API-Kompatibilität
- `build_europe.py`: Import-Fix (`core.regions` → `crop_mcp.core.regions`)

### Performance
| Crop | V4.6 MAE | V4.8 MAE | Δ | R² |
|------|----------|----------|---|----|
| Weizen | 0.598 (11.2%) | **0.588 (11.0%)** | **-1.7%** ✅ | 0.880 |
| Mais | 0.920 (11.6%) | **0.918 (11.6%)** | -0.2% | 0.719 |
| Gerste | 0.540 (11.3%) | **0.534 (11.2%)** | **-1.1%** ✅ | 0.856 |

**Neue Top-Features**: coarse_pct → #1 Gerste (0.238), #2 Weizen; AWC → #2 Mais, #4 Gerste; cfvo → Weizen #3 (0.143)

## 2026-05-04 — V4.7
- **Bulk Density (bdod)**: aus SoilGrids v2 API → `bdod_kg_dm3` in jedem Soil-Profil
- **Coarse Fragments (cfvo)**: aus SoilGrids v2 → `cfvo_pct` in jedem Soil-Profil
- **Coarse Fragments (LUCAS)**: `coarse_pct` aus LUCAS Textur-Daten (war bereits in CSV, wurde nicht ausgegeben)
- **Available Water Capacity (AWC)**: `awc_mm_m` per Saxton-Pedotransferfunktion aus Clay+Sand berechnet
- **Frost Outlook**: `frost_outlook` in `crop_forecast` — analysiert 16-Tage-Vorhersage auf T_min < 0°C, bewertet Risiko (none/low/moderate/high) und warnt bei kritischen Perioden
- **Frost-Warn-Signale**: `frost_warning_next_5_days` und `frost_warning` in yield_signals
- **NDVI Reliability**: Copernicus Data Space als primäre STAC-Quelle, Planetary Computer mit 3× Retry als Fallback, Cache TTL auf 2h erhöht

### Changed
- `SOIL_PROPERTIES` von 7→9 Features (bdod, cfvo hinzugefügt)
- `_country_soil_fallback()`: alle 15 Länder mit bdod/cfvo Defaults
- `get_region_texture()`: gibt jetzt `coarse_pct` und `awc_mm_m` aus
- `get_soil_profile()`: gibt jetzt 11 statt 7 Soil-Felder aus
- Soil-Cache neu gebaut (108 Regionen, ~4 min)
- `ndvi.py`: Dual-Source-Architektur mit Copernicus + Planetary Computer

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
