# Changelog — CropProphEU

## 2026-06-07 — V5.4.4 (Eurostat API Fix + Training Data Refresh 🔄)

### Fixed
- **Eurostat API `strucpro` parameter**: `YI_HU_EU` → `YLD_HUMD_EU_T_HA` (correct yield data endpoint)
- **Rapeseed model**: Rebuilt with 1,770 samples (24 countries), MAE 0.334 t/ha (11.1%), R² 0.732
- **Sunflower model**: Rebuilt with 717 samples (8 countries), MAE 0.355 t/ha (19.0%)

---

## 2026-05-18 — V5.4.3 (Monthly Outlook + Compact Anchors + ERS Integration 🚀)

### Added
- **`list_anchors` Tool (#15)**: Compact overview aller Proof-of-Forecast-Einträge
  - Filterbar nach Region (NUTS2) und Crop
  - Zeigt Timestamp, Yield, Status, OTS-Hash
  - Handler: `crop_mcp/tools/anchor.py`
  - Registriert in `server.py` TOOLS-Dict
- **Monthly Outlook V5.4.2**: `scripts/monthly_outlook.py` komplett überarbeitet
  - 18 EU-Regionen × 5 Kulturen (jetzt inkl. Sonnenblumen)
  - ERS-Integration pro Region (Umweltrisiko-Ampel)
  - Compact Anchors Sektion im Bericht
  - KS-Agrar-Stil: DB/ha-Tabelle, ROI, Marktkommentar
  - Live-Preise (Weizen 241€/t LIVE, Mais 183€/t LIVE)
- **Self-Test**: `list_anchors` Testfall in `self_test()` integriert

### Changed
- `crop_mcp/__init__.py`: Version 5.4.0 → 5.4.3
- `pyproject.toml`: Version 5.4.0 → 5.4.3
- Cron-Job `crop-propheu-monthly-outlook`: Prompt aktualisiert auf V5.4.2
- `server.py`: ListAnchorsInput Pydantic-Modell hinzugefügt (15 Tools total)

---

## 2026-05-06 — V5.3c (Security-Härtung 🛡️)

### Security
- **Pickle → joblib**: `europe_model_api.py`, `train_europe.py`, `train_europe_fast.py` — sicherere Serialisierung
- **File Permissions**: Alle `.pkl`-Modelle und Trainingsdaten auf `chmod 600` gesetzt (world-readable entfernt)
- **Input Validation**: `CompareRegionsInput` und `PortfolioOptimizerInput` haben jetzt Pydantic-Pattern-Validation
- **Dependencies**: `pyproject.toml` mit Upper-Bound-Pinning (`<2.0`, `<3.0`) für alle Abhängigkeiten
- `joblib>=1.3,<2.0` als explizite Dependency hinzugefügt

### Changed
- `europe_model_api.py`: `pickle.load(f)` → `joblib.load(path)` (sicherer)
- `train_europe*.py`: `pickle.dump()` → `joblib.dump()`
- `server.py`: CompareRegionsInput.regions/crops + PortfolioOptimizerInput.regions/crops mit Pattern-Validierung
- `pyproject.toml`: Alle Versions-Constraints gepinnt mit Upper-Bound

---

## 2026-05-06 — V5.3 (Country-Specific Production Costs 🔴)

### Added
- **Länderspezifische Produktionskosten** für alle 5 Kulturen (Weizen, Mais, Gerste, Raps, Sonnenblumen)
- **`COUNTRY_PRODUCTION_COSTS`**: Nested dict mit 28 Ländern für Weizen, Mais, Gerste, Raps, Sonnenblumen
- **`get_production_cost(crop, country)`**: Neue Funktion für country-spezifische Kostenabfrage
- Export von `get_production_cost` + `REFERENCE_PRICES` in `__init__.py`

### Changed
- `calculate_revenue()`: Neuer Parameter `country` — berechnet länderspezifische Kosten statt pauschaler 650€/ha
- `server.py`: Alle `calculate_revenue()`-Aufrufe übergeben jetzt das Herkunftsland (`country=cnt` / `country=country`)
- Alle 5 Kulturen haben jetzt länderspezifische Kosten pro EU-Staat

### Fixed
- 🔴 **Bug: Bulgarien/Rumänien/Polen hatten fälschlich 650€/ha** — korrigiert auf 380€/ha (BG/RO) und 450€/ha (PL)
- NL/BE Kosten korrigiert: 950€/ha (NL) und 850€/ha (BE) — hohe Pacht und Intensität
- Ukraine: 300€/ha (realistische Niedrigkosten)

### Data Sources
- FADN (EU Farm Accountancy Data Network)
- KTBL (Deutschland), ARVALIS (Frankreich), AHDB (UK)
- EU-Kommission Agrarausblick
- Nationale Agrarberichte

---

## 2026-05-05 — V5.2 (Visibility Release 🚀)

### Added
- **README komplett überarbeitet** — V5.2 Features, alle 12 Tools, 5 Crops, live prices, NDVI correction, portfolio optimizer
- **GitHub Release v5.2.0** — mit Release Notes

### Changed
- `README.md`: Vollständige Neufassung — Raps/Sonnenblumen korrigiert (I1110/I1120), compare_regions, portfolio_optimizer, NDVI correction, live prices
- Version: 5.1.0 → 5.2.0

### Fixed
- `crop_mcp/__init__.py`: Version 4.7.0 → 5.2.0 (war 4 Versionen zurück — desync fix)

---

## 2026-05-05 — V5.1e (Portfolio Optimizer)

### Added
- **`portfolio_optimizer` Tool** — AI-for-AI investment engine
  - `portfolio_optimizer(budget_eur, risk_tolerance, regions?, crops?, year?)`
  - Optimiert Allokation über Regionen×Kulturen mittels Brute-Force (max 100 Kombos)
  - Gibt ranking mit Fläche, Marge, ROI, Risikostufe zurück
  - Budgetaufteilung: Weizen dominiert (hohe Marge, niedriges Risiko)
- `crop_mcp/tools/portfolio_optimizer.py` — vollständige Implementierung
- Wiki-Seite: `portfolio-optimizer-tool`

### Changed
- `server.py`: Tool #12 registriert — `portfolio_optimizer`
- Sunflower-Modell retrained (1,229 Samples, 17 Länder, MAE 16.1%)
- Version: 5.1.0 → 5.1.1

---

## 2026-05-05 — V5.1d 🔴 (Eurostat Crop Code Fix — Rapeseed & Sunflower)

### 🔴 CRITICAL FIX — Silent Data Corruption

**Befund**: Rapeseed und Sunflower wurden mit Rice-Daten trainiert:
- Rapeseed (C2000) = **Paddy Rice**, nicht Raps!
- Sunflower (C2200) = **Rice Japonica**, nicht Sonnenblumen!

**Fix**:
- Rapeseed → **I1110** (Rape/turnip rape seeds) — Industrial crop code
- Sunflower → **I1120** (Sunflower seed) — Industrial crop code
- Länder erweitert: Rapeseed von 8→25 Länder (DE, UK, NL, PL, DK jetzt real)
- Sunflower von 8→17 Länder (DE, AT, CZ, HR, HU, IT, PL, RO, SK, BG, NL, PT, UA)

### Model Performance (post-fix)

| Crop | Samples | Länder | LOYO MAE | R² | Top Feature |
|------|:-------:|:------:|:--------:|:--:|:-----------:|
| Rapeseed | **1,825** | **25** | **0.340 (10.8%)** | 0.827 | coarse_pct (28%) |
| Sunflower | **1,229** | **17** | **0.326 (16.1%)** | 0.742 | silt_pct (24%) |

**Critical impact**: DEE0 Rapeseed prediction fiel von 7.21 t/ha (Rice-Daten) auf 2.63 t/ha (reale EU-Daten). Alle vorherigen Rapeseed-Prognosen waren wertlos.

### Technical
- `Eurostat`: Prefix-Suche implementiert (C=Cereals, I=Industrial, R=Root crops)
- SIEC-Klassifikation dokumentiert
- Wiki-Seite: `rapeseed-data-fix`
- Version: 5.1.0 → 5.1.1

---

## 2026-05-05 — V5.1c (Live Prices in compare_regions + Monthly Outlook)

### Added
- **`price_eur_per_t`** in `compare_regions` Output — live CBOT/MATIF Futures pro Region×Crop
- **Monthly Outlook Cron-Job**: `crop-propheu-monthly-outlook` (2. jeden Monats, 06:00 UTC)
- `scripts/monthly_outlook.py` — automatische Finanzanalyse mit Live-Preisen, historischem Vergleich, Portfolio-Empfehlung

### Changed
- `REFERENCE_PRICES` aktualisiert: Mais 205→**189**€/t, Weizen 235→**239**€/t (Δ zum Live = 0)
- `compare_regions`: Summary zeigt jetzt `1780€/ha @ 189€/t` statt nur `1780€/ha`
- Version: 5.1.0 → 5.1.1

---

## 2026-05-05 — V5.1b (NDVI Correction + compare_regions)

### Added
- **NDVI Satellite Correction**: `crop_mcp/ndvi_correction.py`
  - Sentinel-2 NDVI via Copernicus STAC → multiplikativer Faktor (±30% max)
  - Pro-Kultur Sensitivity: Wheat 0.25, Corn 0.22, Barley 0.20, Rapeseed 0.18, Sunflower 0.18
  - Graceful degradation bei fehlenden Daten (cloud cover, API-Error)
- **`compare_regions` Tool**: `compare_regions(regions, crops, year?)`
  - Batch-Vergleich von bis zu 20 Regionen × 5 Kulturen
  - Sortiertes Ergebnis mit Yield, Risk Range (P10/P90), Market Value (€/ha), NDVI-Status
- Wiki-Seiten: `crop-propheu-2026-financial-decision`

### Changed
- `europe_model_api.py`: NDVI-Korrektur in Vorhersage-Pipeline integriert
- `soil_cache.json`: 108→120 Regionen (UK+UA via SoilGrids v2 API)
- Version: 5.0.0 → 5.1.0

---

## 2026-05-05 — V5.1 (Data Integrity Fix)

### 🚨 Befund & Fix
- **Soil = Defaults**: Alle Trainingsdaten (wheat, barley, corn) hatten SOC=15.0 — 100% Default-Werte. **Fix**: Soil Cache auf 120 Regionen erweitert, 5.405 Samples mit echten SoilGrids v2-Daten gepatcht
- **UK/UA Wetter = 0**: 324 Samples (44 UK barley + 40 UK corn + 120 UA wheat + 120 UA sunflower) hatten GDD=0, Precip=0 durch falschen NASA POWER Key. **Fix**: Korrekte Key-Formatierung (YYYYMM statt Monatsnummer)
- **UA Erträge unverifiziert**: FAOSTAT-Daten waren hartcodiert ohne Quellen. **Fix**: Gegen USDA FAS + World Bank verifiziert, Quellen dokumentiert

### Model Performance (V5.1 — retrained with real data)

| Crop | Samples | Länder | LOYO MAE | R² (LOYO) | Real Soil |
|------|:-------:|:------:|:--------:|:---------:|:---------:|
| 🌾 Barley | 1.885 | 26 | **0.538 (11.2%)** | 0.851 | 97% |
| 🌽 Corn | 1.797 | 21 | **0.922 (11.6%)** | 0.718 | 97% |
| 🌾 Wheat | 1.603 | 26 | **0.599 (11.5%)** | 0.871 | 97% |
| 🌻 Rapeseed | 717 | 8 | **0.724 (13.4%)** | 0.539 | 97% |
| 🌻 Sunflower | 764 | 9 | **0.586 (11.9%)** | 0.749 | 97% |

### Changed
- `soil_cache.json`: Erweitert von 108 → 120 Regionen (UK + UA)
- `crop_mcp/sources/faostat.py`: Quellen dokumentiert, Daten gegen USDA FAS + World Bank verifiziert
- Alle `europe_training_data_*.json`: Soil-Patch + Weather-Rebuild
- Alle `europe_yield_model_*.pkl`: Retrained mit echten Daten

### Technical Notes
- **Vor Fix**: Nur Raps + Sonnenblume hatten echte Bodendaten (V4.9-Build)
- **Nach Fix**: 97% Soil-Coverage in ALLEN 5 Modellen
- **Restliche 3% Defaults**: Sehr kleine NUTS2-Regionen ohne SoilGrids-Daten (Inseln, Stadtstaaten)
- **Entscheidungsreife**: LOL-Score 7.5/10 — finanzielle Entscheidungen mit 15-20% Risikopuffer vertretbar
- Version: 5.0.0 → 5.1.0

## 2026-05-05 — V5.0 (UK + Ukraine Expansion)

### Added
- **🇬🇧 UK Coverage**: Barley + Corn Modelle mit UK-Daten neu trainiert
- **🇺🇦 Ukraine Coverage**: Wheat + Sunflower Modelle mit FAOSTAT-kompilierten Daten (via NASA POWER + Soil-Defaults)
- `build_v5.py`: UK + Ukraine Batch-Builder
- `crop_mcp/sources/faostat.py`: FAOSTAT Fetcher (mit kompilierten Referenzdaten als Fallback)

### Model Performance (V5.0)

| Crop | Samples | Länder | Neu | LOYO MAE |
|------|:-------:|:------:|:---:|:--------:|
| 🌾 Barley | **1.885** | 26 | UK: 44 (⌀ 6,00 t/ha) | **0,540 (11,2%)** |
| 🌽 Corn | **1.797** | 21 | UK: 40 (⌀ 5,05 t/ha) | **0,919 (11,6%)** |
| 🌾 Wheat | **1.603** | 26 | UA: 120 (⌀ 3,93 t/ha) | **0,585 (11,2%)** |
| 🌻 Sunflower | **764** | 9 | UA: 120 (⌀ 2,16 t/ha) | **0,578 (11,7%)** |

### Changed
- `build_europe.py`: CROP_COUNTRIES expanded — UK für barley+corn, UA für wheat+sunflower
- `europe_model_api.py`: Fallback baseline um min/max erweitert (KeyError-Fix)
- Training Data Paths: Alle Modelle jetzt mit UK/UA Daten
- Version: 4.9.0 → 5.0.0

### Technical Notes
- UK Datenquelle: Eurostat (barley 2010–2020, 11yr; corn 2011–2020, 10yr)
- Ukraine Datenquelle: FAOSTAT-kompilierte Referenzdaten (wheat + sunflower, 14yr)
- Soil-Features für UK/UA: Regionale Defaults (SoilGrids-Suche bei Bedarf)
- Ukraine sunflower: 2,16 t/ha ⌀ — weltweit #1 Produzent, moderate Erträge

## 2026-05-04 — V4.9 (Raps + Sonnenblumen)

### Added
- **2 neue Kulturen**: Raps (rapeseed) + Sonnenblumen (sunflower) — datengetrieben
- **Raps-Modell**: 717 Samples, 8 Länder (FR, RO, HU, ES, IT, BG, PT, EL) — LOYO MAE **0.72 t/ha (13.4%)**
- **Sonnenblumen-Modell**: 644 Samples, 8 Länder (FR, RO, HU, ES, IT, BG, PT, EL) — LOYO MAE **0.64 t/ha (11.7%)**
- `build_europe.py`: Unterstützt `--crop rapeseed` und `--crop sunflower`
- `train_europe_fast.py`: Neues Feature `best_estimator` speichert Modell-Typ-Metadaten im Pickle

### Model Performance

| Crop | LOYO MAE | R² (LOYO) | Top-Feature |
|------|----------|-----------|-------------|
| 🌾 Raps | **0.724 (13.4%)** | 0.539 | AWC 42.2% |
| 🌻 Sonnenblumen | **0.636 (11.7%)** | 0.581 | AWC 37.3% |

### Changed
- `europe_model_api.py`: Fallback-Baseline um `min`/`max` erweitert (verhindert KeyError bei Ländern außerhalb des Trainings-Sets)
- `CROPS` + `REGIONS`-Definitionen: rapeseed + sunflower bereits integriert (keine Schema-Änderung nötig)
- `VERIFIED_CROPS`: `"rapeseed"` und `"sunflower"` aufgenommen

### Technical Notes
- Rapeseed: Bestes Modell Ridge (alpha=5), gespeichert als RF 200 trees für Yield-at-Risk
- Sunflower: Bestes Modell RF 200 trees — hoher Sand-Einfluss (19.7%) bestätigt Trockentoleranz
- AWC dominiert beide Modelle (>37%) — Wasserhaltefähigkeit ist der limitierende Faktor für Ölsaaten in Südeuropa

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
- Telegram Bot for Crop + Drug Intelligence (/home/j/bots/telegram_bot.py)
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
