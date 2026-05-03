# Crop-MCP: Kostenvergleich

## Token-Kosten pro Tool-Call

| Tool | Output Tokens | Vergleich |
|------|:------------:|-----------|
| `europe_yield_forecast` | ~93 | 📄 Eine Textnachricht |
| `climate_scenario` | ~118 | 📄 Kurzer Absatz |
| `crop_forecast` | ~139 | 📄 Kurzer Absatz |
| `season_comparison` | ~112 | 📄 Kurzer Absatz |
| `weather_outlook` | ~145 | 📄 Wochenbericht |
| `list_regions` | ~659 | 📚 Nur bei Bedarf |
| **Ø pro Analyse** | **~100-150** | **Extrem effizient** |

## Vergleich: Mit vs. Ohne Crop-MCP

### Szenario: "Wie steht der Weizen in Sachsen-Anhalt?"

**Ohne crop-mcp (Browser-Workflow):**
```
→ web_search("Sachsen-Anhalt weather 2026"):           ~2.000 tokens
→ Browser navigate (Open-Meteo):                       ~8.000 tokens  
→ Browser navigate (NASA POWER):                       ~8.000 tokens
→ web_search("Eurostat wheat yields DE"):              ~2.000 tokens
→ Agent analysiert Rohdaten:                           ~3.000 tokens
→ Schreibt Zusammenfassung:                            ~800 tokens
────────────────────────────────────────────
Total: ~23.800 tokens  💸
```

**Ohne crop-mcp (open-meteo-mcp + manuelle Analyse):**
```
→ open-meteo historical data:                          ~500 tokens
→ Agent berechnet GDD selbst:                          ~2.000 tokens
→ Agent sucht Eurostat-Yields:                         ~2.000 tokens
→ Agent vergleicht manuell:                            ~3.000 tokens
────────────────────────────────────────────
Total: ~7.500 tokens  💸
```

**Mit crop-mcp:**
```
→ crop_forecast("wheat", "DEE0"):                      ~139 tokens
→ europe_yield_forecast("wheat", "DEE0"):              ~93 tokens
→ Agent schreibt Analyse:                              ~600 tokens
────────────────────────────────────────────
Total: ~832 tokens  ✅
```

### Token-Einsparung: **96-97%** pro Analyse

## Kosten-Rechnung (DeepSeek V4 Flash ~$0.15/M tokens)

| Ansatz | Tokens/Analyse | Kosten/Analyse | 100 Analysen |
|--------|:--------------:|:--------------:|:------------:|
| Browser-Workflow | ~23.800 | ~$0.0036 | $0.36 |
| open-meteo-mcp only | ~7.500 | ~$0.0011 | $0.11 |
| **crop-mcp** | **~832** | **~$0.00012** | **$0.01** |

Selbst bei günstigen Modellen ist crop-mcp **10-30x billiger** als der manuelle Weg — nicht weil Tokens teuer sind, sondern weil der Agent Zeit und Kontextfenster spart.

## Warum das wichtig ist

1. **Agenten-Kontext ist teuer**: Große Outputs fressen das Kontextfenster → mehr API-Calls fürs gleiche Gespräch
2. **Latenz**: Browser-Workflows brauchen 30-60s. crop-mcp antwortet in <1s
3. **Rate-Limits**: Browser-Seiten ratelimiten aggressiv (Open-Meteo 429 nach 50 Calls). NASA POWER + SoilGrids sind ratelimit-frei
4. **Reliability**: Browser-Stealth-Detection, CAPTCHAs, Session-Timeouts — alles nicht existent bei crop-mcp

## Positioning: Einziger MCP-Server seiner Art

| Server | Tools | Datenquellen | Yield? | Soil? | EU-wide? | What-If? |
|--------|:----:|:------------:|:------:|:-----:|:--------:|:--------:|
| open-meteo-mcp | 1 | 1 (Open-Meteo) | ❌ | ❌ | ❌ | ❌ |
| nexusforegetools/eu-agriculture | ~3 | 1 (Eurostat) | ✅ roh | ❌ | ✅ | ❌ |
| ancientwhispers54/leafengines | ~2 | 1 (unbekannt) | ❌ | ❌ | ❌ | ❌ |
| **crop-mcp 4.0** | **9** | **5 (POWER, OM, SoilGrids, LUCAS, Eurostat)** | **✅ ML** | **✅** | **✅ 25 Länder** | **✅** |
| Gro Intelligence | API | $10K+/yr | ✅ | ✅ | ❌ | ❌ |
| EU MARS Bulletin | PDF | 1 (JRC) | ✅ 4-6% | ❌ | ✅ | ❌ |
