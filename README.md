# 🌾 CropProphEU — EU Crop Intelligence MCP Server

[![CI](https://github.com/DasClown/CropProphEU/actions/workflows/ci.yml/badge.svg)](https://github.com/DasClown/CropProphEU/actions/workflows/ci.yml)
[![Smithery](https://smithery.ai/badge/DasClown/CropProphEU)](https://smithery.ai/servers/DasClown/CropProphEU)
[![Python ≥3.11](https://img.shields.io/badge/python-%3E%3D3.11-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/DasClown/CropProphEU?style=flat)](https://github.com/DasClown/CropProphEU/stargazers)
[![Discussions](https://img.shields.io/github/discussions/DasClown/CropProphEU?style=flat&label=Discussions&color=informational)](https://github.com/DasClown/CropProphEU/discussions)
[![Tests](https://img.shields.io/badge/tests-15%20passing-brightgreen)](tests/)
[![Git LFS](https://img.shields.io/badge/data-LFS-blueviolet)](.gitattributes)

**13 MCP Tools, 5 Crops, 26 EU Countries, 123 NUTS2 Regions** — Yield forecasts, market values (€/ha), risk analysis, environmental risk scoring & portfolio optimization for European agriculture. Built for AI agents, by AI agents.

> *"How will wheat perform in Sachsen-Anhalt this year? What's my best €/ha allocation across 100 ha?"*

```bash
pip install git+https://github.com/DasClown/CropProphEU.git
```

---

## Features (13 MCP Tools)

| # | Tool | What it does | V |
|---|------|-------------|---|
| 1 | `yield_and_value` | Yield + **market value (€/ha)** + plain-language summary (DE/EN) | V4.6 |
| 2 | `europe_yield_forecast` | Pan-European RF forecast with **Yield-at-Risk** (P10/P50/P90) + **NDVI correction** | V4.3 |
| 3 | `crop_forecast` | Current season: GDD, rain, soil moisture, drought index, **frost warnings** | V4.0 |
| 4 | `compare_regions` | Batch-compare 20 regions × 5 crops with live market prices | **V5.1** |
| 5 | `portfolio_optimizer` | AI investment engine: budget → optimal allocation across regions × crops | **V5.1e** |
| 6 | `season_comparison` | Compare this season to historical years | V4.0 |
| 7 | `region_health` | All crops for one region, single call | V4.5 |
| 8 | `weather_outlook` | 16-day weather forecast | V4.0 |
| 9 | `climate_scenario` | What-if: +2°C, -20% rain, etc. | V4.4 |
| 10 | `yield_forecast` | Analog-year yield matching (DE-focused) | V3.0 |
| 11 | `list_regions` | 123 NUTS2 regions across 26 countries | V4.2 |
| 12 | `list_crops` | Crop parameters (GDD base, season, frost sensitivity) | V4.5 |
| 13 | `environmental_risk` | **NEW V5.4** — ERS (forest, erosion, storm, hail) + **wild boar damage risk** for DE | **V5.4** |

---

## Quick Start

### 1. Install

```bash
pip install git+https://github.com/DasClown/CropProphEU.git
```

### 2. Use as MCP Server

CLI (stdio):
```bash
crop-mcp
```

Python API:
```python
from crop_mcp import predict_europe_yield

result = predict_europe_yield("DE11", "DE", crop="wheat", gdd=3050, precip_mm=650)
print(f"Yield: {result['predicted_yield_t_ha']} t/ha")
print(f"Revenue: ~{result['predicted_yield_t_ha'] * 239:.0f} €/ha")
```

### 3. Claude Desktop / Cursor

```json
{
  "mcpServers": {
    "crop": {
      "command": "python3",
      "args": ["-m", "crop_mcp.server"]
    }
  }
}
```

### 4. HTTP Server (Remote / Smithery)

```bash
pip install crop-mcp[http]
crop-mcp --http --port 8080
```

Connect via SSE: `http://your-server:8080/sse`

### 5. Docker

```bash
docker build -t crop-mcp .
docker run -p 8080:8080 crop-mcp crop-mcp --http --port 8080
```

---

## Verified Crops — Data Integrity ✅

**Every prediction traces to a verified Eurostat crop code.** No hallucinations, no silent wrong-crop training.

| Crop | Eurostat Code | Samples | Countries | MAE (LOYO) | R² |
|------|:-------------:|:-------:|:---------:|:----------:|:--:|
| 🌾 **Wheat** | C1100 | 1,603 | **26** (🇪🇺+🇺🇦) | **11.5%** | 0.87 |
| 🌽 **Corn (Maize)** | C1500 | 1,797 | **21** (🇪🇺+🇬🇧) | **11.6%** | 0.72 |
| 🌿 **Barley** | C1300 | **1,885** | **26** (🇪🇺+🇬🇧) | **11.2%** | 0.85 |
| 🌻 **Rapeseed** | **I1110** | **1,825** | **25** | **10.8%** | 0.83 |
| 🌻 **Sunflower** | **I1120** | **1,229** | **17** | **16.1%** | 0.74 |

> ⚠️ **V5.1d Data Fix**: Rapeseed + Sunflower were previously trained on RICE data (wrong Eurostat codes C2000/C2200). **Now corrected to Industrial crop codes I1110/I1120.** DE rapeseed prediction fell from 7.21t to 2.63t — real, not extrapolated.

---

## Why CropProphEU?

| Capability | CropProphEU | Open-Meteo MCP | Gro Intelligence |
|-----------|:-----------:|:--------------:|:----------------:|
| Yield forecasts | ✅ 5 crops | ❌ | ✅ $10K+/yr |
| Soil features | ✅ 11 properties | ❌ | ✅ |
| Yield-at-Risk (P10/P90) | ✅ | ❌ | ✅ |
| Live market prices (€/ha) | ✅ CBOT + MATIF | ❌ | ✅ |
| Climate what-if | ✅ | ❌ | ✅ |
| Frost warnings | ✅ | ✅ | ❌ |
| NDVI satellite correction | ✅ | ❌ | ❌ |
| Portfolio optimizer | ✅ | ❌ | ❌ |
| Multi-language (DE/EN) | ✅ | ❌ | ❌ |
| **Price** | **Free** | Free | **$10K+/yr** |

**Unique**: Only **free** MCP server covering EU agriculture with soil → yield → market value → environmental risk → portfolio optimization in one pipeline.

---

## V5.4 — Environmental Risk Score + Wildschaden 🌍🐗

| Feature | Beschreibung |
|:--------|:------------|
| **Environmental Risk Score** | Komposit aus Waldanteil, Maisfläche, Bodenerosion, Sturm- + Hagelrisiko → 🟢🟡🔴 |
| **Wildschaden DE** | DJV-Jagdstreckendaten + Waldrandindex + Maisflächenanteil → €/ha-Verlustschätzung |
| **Ampel-System** | `🟢 low (<35)`, `🟡 moderate (35-65)`, `🔴 high (≥65)` |
| **MCP Tool** | `environmental_risk(region='DE26')` → sofortige Analyse inkl. Wildschaden |

**Beispiel Maßbach (DE26 Unterfranken):**
```json
{
  "overall_risk": "🔴 high",
  "ers_level": "🟡 moderate",
  "wild_boar_risk": {"level": "🔴 high", "loss_eur_ha": 158},
  "management": ["Waldrandstreifen 3-6m", "Drückjagd Nov-Dez", "8-Tage-Anzeigefrist §36 BayJG"]
}
```

## V5.4 — Testing & CI 🧪

| Maßnahme | Status |
|:---------|:------:|
| **pytest** | 15 Tests, alle passing (`tests/test_crop_mcp.py`) |
| **GitHub Actions** | Automatischer CI-Check bei jedem Push |
| **Git LFS** | `*.pkl` + große `.json` via LFS (aus Git-Tree entfernt) |

Run tests:
```bash
pip install -e ".[test]"
pytest tests/ -v
```

---

## Model Accuracy

| Metric | Value |
|--------|:-----:|
| **LOYO MAE** (Wheat) | 0.599 t/ha (11.5%) |
| **Forward Validation** (Train ≤2022, Test 2023-24) | 0.794 t/ha (15.0%) |
| R² (LOYO) | 0.871 |
| R² (Forward) | 0.628 |

Most accurate for **core EU** (DE, FR, BE, NL, AT, CZ) where training data is dense.

### Per-Crop Performance (V5.2)

| Crop | Algorithm | Top Feature | Key Insight |
|------|:---------:|:-----------:|-------------|
| 🌾 Wheat | RF 200 trees | solar_kwh (35%) | Nord/Süd gradient dominates |
| 🌽 Corn | RF 200 trees | **clay_pct (42%)** | Maize is extremely soil-sensitive |
| 🌿 Barley | Ridge | clay_pct (27%) | Best coverage of all crops |
| 🌻 Rapeseed | RF 200 trees | coarse_pct (28%) | Corrected — now 1,825 real samples |
| 🌻 Sunflower | Ridge | silt_pct (24%) | 17 countries (post-fix) |

---

## Live Market Prices

| Crop | Source | €/t (Mai 2026) | Market |
|------|:------:|:---------------:|--------|
| Wheat | ✅ CBOT ZW=F + MATIF premium | 239 | Euronext MATIF |
| Corn | ✅ CBOT ZC=F + MATIF premium | 189 | Euronext MATIF |
| Barley | ✅ Reference (AMI regional) | 190 | AMI regional exchanges |
| Rapeseed | ✅ Reference | 470 | Euronext MATIF (ECO) |
| Sunflower | ✅ Reference | 420 | ICE / Black Sea |

**Production costs** (€/ha): Wheat 650, Corn 700, Barley 600, Rapeseed 780, Sunflower 650

---

## Data Sources

| Source | Data | Access |
|--------|------|--------|
| **Eurostat** | Crop yields (`apro_cpshr`) — 25+ years, verified codes | Free, no key |
| **NASA POWER** | GDD, precip, solar, soil moisture | Free, no rate limits |
| **Open-Meteo** | 16-day forecast, GDD | Free, no key |
| **SoilGrids v2** (ISRIC) | 11 properties: SOC, pH, N, CEC, clay, sand, silt, **bdod (bulk density), cfvo (coarse fragments), AWC, coarse** | Free REST API |
| **LUCAS Soil** (ESDAC) | Texture ~20K field points + coarse fragments | Free download |
| **Sentinel-2 NDVI** | Vegetation index (Copernicus STAC + Planetary Computer fallback) | Free, no auth |
| **Yahoo Finance** | Live CBOT wheat/corn futures, EUR/USD | Free, no key |

**Zero API keys required** — all sources are free and public.

---

## Example Output

**German (default):**
```
Weizen – Region DEE0 (DE)
Ertrag: 7.35 t/ha (Spanne 6.50–8.20)
Temperatur: warm (2950°C Wärmesumme)
Niederschlag: ausreichend (480 mm)
Bodenfeuchte: feucht (48%)
Modellabweichung: ±11.5% (1603 Samples, 26 Länder)
Vergleich zu 2024: +0.15 t/ha (im Rahmen des Vorjahres)
Marktwert: 1.757 €/ha @ 239 €/t
Kosten: 650 €/ha → Deckungsbeitrag: 1.107 €/ha
```

**English (with `language="en"`):**
```
Wheat – Region DEE0 (DE)
Yield: 7.35 t/ha (range 6.50–8.20)
Temperature: warm (2950°C GDD)
...
```

---

## Architecture

```
crop-mcp/
├── crop_mcp/
|├── server.py                 # 13 MCP tools
│   ├── europe_model_api.py       # RF (200 trees) + Yield-at-Risk + NDVI correction
│   ├── environmental_risk.py     # **NEW V5.4** — ERS + Wildschaden DE
│   ├── ndvi_correction.py        # Sentinel-2 NDVI correction factor (±30%)
│   ├── market_prices.py          # Live CBOT/MATIF via Yahoo Finance
│   ├── feature_cache.py          # Sub-second historical queries
│   ├── simulate_yield.py         # Analog-year matching
│   ├── auto_update.py            # Monthly retrain cron
│   ├── core/regions.py           # 123 NUTS2 regions
│   └── sources/                  # Weather, soil, NDVI, Eurostat, FAOSTAT fetchers
├── models/                       # .pkl files (download from Releases)
├── data/                         # Training data (generated by build)
├── tests/                        # **NEW V5.4** — 15 pytest tests
├── .github/workflows/            # **NEW V5.4** — CI (GitHub Actions)
├── .gitattributes                # **NEW V5.4** — Git LFS tracking
├── pyproject.toml
└── README.md
```

**Key design principles:**
- **No hallucination** — every yield prediction traces to verified Eurostat data
- **Live prices** — CBOT wheat/corn via Yahoo Finance, updated hourly
- **Self-updating** — monthly cron rebuilds models with latest Eurostat data
- **Zero API keys** — all data sources are free and public
- **AI-for-AI** — built for agents, no dashboards

---

## Building & Training

```bash
# Build training data (25 min per crop)
python3 build_europe.py --crop corn

# Train model (2 min)
python3 train_europe_fast.py --crop corn

# Auto-update monthly (cron: 1st of month at 06:00)
```

---

## Commercial Use Cases

- **Agri-trading desks**: "What's wheat worth in Picardie at current MATIF prices?"
- **Farm advisory**: "How does this season compare to the last 5 years?"
- **Insurance / Risk**: Yield-at-Risk (P10/P50/P90) per region + crop
- **EU policy analysis**: Climate scenario impact on national yields
- **Investment**: Portfolio optimizer for 100+ ha allocation decisions

---

## 🤝 Getting Help & Contributing

| Channel | Purpose |
|---------|---------|
| **[💬 GitHub Discussions](https://github.com/DasClown/CropProphEU/discussions)** | Questions before coding, feature ideas, community chat |
| **[🐛 GitHub Issues](https://github.com/DasClown/CropProphEU/issues)** | Bug reports, confirmed feature requests |
| **[📖 CONTRIBUTING.md](CONTRIBUTING.md)** | Development setup, branch naming, commit conventions, code style |

New contributors welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

---

## License

MIT — free to use, modify, and distribute.

Built with ❤️ for AI agents that need real, verifiable crop intelligence.
