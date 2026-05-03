# 🌾 crop-mcp

[![Smithery](https://smithery.ai/badge/@crop-mcp/CropProphEU)](https://smithery.ai/servers/crop-mcp/CropProphEU)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/DasClown/CropProphEU?style=flat)](https://github.com/DasClown/CropProphEU/stargazers)

**EU Crop Intelligence MCP Server** — Yield forecasts, market values & risk analysis for 25 EU countries.

Get AI agents to answer: *"How will wheat perform in Baden-Württemberg this year? What's it worth at current market prices?"*

```bash
pip install git+https://github.com/DasClown/CropProphEU.git
# or try it on Smithery: https://smithery.ai/servers/crop-mcp/CropProphEU
```

---

## Features (10 MCP Tools)

| Tool | What it does | 
|------|-------------|
| `yield_and_value` | **NEW** — Combined yield + market value (€/ha) with plain-language summary in German or English (auto-detected via `language` parameter) |
| `europe_yield_forecast` | Pan-European yield forecast (3 crops, 25 countries) with Yield-at-Risk |
| `crop_forecast` | Current season status: temperature, rain, soil moisture, drought index |
| `season_comparison` | Compare this season to historical years |
| `region_health` | All crops for one region in a single call |
| `weather_outlook` | 16-day weather forecast |
| `climate_scenario` | What-if: +2°C, -20% rain? |
| `yield_forecast` | Analog-year yield matching (DE-focused) |
| `list_regions` | 120 NUTS2 regions |
| `list_crops` | Crop parameters (GDD base, season, etc.) |

## Quick Start

### 1. Install

```bash
pip install git+https://github.com/DasClown/CropProphEU.git
```

### 2. Use as MCP Server

via CLI (stdio):
```bash
crop-mcp
```

or via Python:
```python
from crop_mcp import predict_europe_yield

result = predict_europe_yield("DE11", "DE", crop="wheat", gdd=3050, precip_mm=650)
print(f"Yield: {result['predicted_yield_t_ha']} t/ha")
print(f"Revenue: ~{result['predicted_yield_t_ha'] * 235:.0f} €/ha")
```

### 3. Claude Desktop / Cursor / Any MCP Client

Add to your MCP config:
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

### 4. HTTP Server (for Remote Access / Smithery)

```bash
pip install crop-mcp[http]
crop-mcp --http --port 8080
```

Connects via SSE: `http://your-server:8080/sse`

### 5. Docker

```bash
docker build -t crop-mcp .
docker run -p 8080:8080 crop-mcp crop-mcp --http --port 8080
```

---

## Verified Crops

| Crop | Eurostat Code | Samples | Countries | MAE (LOYO) |
|------|:-------------:|:-------:|:---------:|:----------:|
| 🌾 Wheat | C1100 | 1,483 | 25 | 11.2% |
| 🌽 Corn (Maize) | C1500 | 1,648 | 20 | 11.6% |
| 🌿 Barley | C1300 | 1,841 | 25 | 11.3% |

**Rapeseed & Sunflower**: Not supported — no Eurostat yield data available. Tools reject these with a clear error (no silent hallucinations).

---

## Example Output

**German (default):**
```
Weizen – Region DE11 (DE)
Ertrag: 7.68 t/ha (Spanne 6.67–8.63)
...
```

**English (with `language="en"`):**
```
Wheat – Region DE11 (DE)
Yield: 7.68 t/ha (range 6.67–8.63)
Temperature: warm (3050°C GDD)
...
```

All output is available in **German** (default) or **English**. Set `language="en"` when calling `yield_and_value` for English output. The JSON data is always returned in English field names; the `summary` field adapts to the requested language.

---

## Data Sources

| Source | Data | Access |
|--------|------|--------|
| Eurostat | Crop yields (`apro_cpshr`) | Free, no key |
| NASA POWER | GDD, precip, solar, soil moisture | Free, **no rate limits** |
| Open-Meteo | 16-day forecast | Free, no key |
| SoilGrids v2 | SOC, pH, N, CEC, texture | Free REST API |
| Yahoo Finance | **Live** CBOT wheat/corn futures + EUR/USD | Free, no key |

---

## Model Accuracy

| Metric | Value |
|--------|:-----:|
| **LOYO MAE** (Wheat) | 0.598 t/ha (11.2%) |
| **Forward Validation** (Train ≤2022, Test 2023-24) | 0.794 t/ha (**15.0%**) |
| R² (LOYO) | 0.877 |
| R² (Forward) | 0.628 |

**What this means**: The LOYO metric is optimistic because it trains on data from all years including future ones. The **Forward Validation** (train on 2000-2022, predict 2023-2024) is the real-world benchmark: **±15%**. 

The model is most accurate for **core EU countries** (DE, FR, BE, NL, AT, CZ) where training data is dense, and less accurate for outliers like **NL/BE 2024** where unusual weather caused systematic overestimation.

---

## Architecture

```
crop-mcp/
├── crop_mcp/
│   ├── server.py              # 10 MCP tools
│   ├── europe_model_api.py    # Random Forest (200 trees) + Yield-at-Risk
│   ├── market_prices.py       # Live prices via Yahoo Finance + reference
│   ├── core/regions.py        # 120 NUTS2 regions
│   └── sources/               # Weather, soil, NDVI data fetchers
├── models/                    # .pkl files (download from Releases)
├── data/                      # Training data (generated by build)
├── pyproject.toml
└── README.md
```

Key design principles:
- **No hallucination** — every yield prediction traces to verified Eurostat data
- **Live prices** — CBOT wheat/corn via Yahoo Finance, updated hourly
- **Self-updating** — monthly cron job rebuilds models with latest Eurostat data
- **Zero external API keys** — all data sources are free and public

---

## Commercialization

The tool is production-ready today for:
- **Agri-trading desks** — "What's wheat worth in Picardie at current MATIF prices?"
- **Farm advisory** — "How does this season compare to the last 5 years?"
- **Insurance / Risk** — Yield-at-Risk (P10/P50/P90) per region
- **EU policy analysis** — Climate scenario impact on national yields

**Next commercial features**: Market prices per country, historical price correlation, automated PDF reports, multi-year crop rotation planning.

---

## Building & Training

```bash
# Build training data for a specific crop (25 min)
python3 build_europe.py --crop corn

# Train the model (2 min)
python3 train_europe_fast.py --crop corn

# Automatic monthly update (cron)
# Runs every 1st of the month at 06:00
```

---

## License

MIT — free to use, modify, and distribute.

Built with ❤️ for AI agents that need real, verifiable crop intelligence.
