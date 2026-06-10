# ERA5 / Copernicus CDS — Integrationsplan für CropProphEU

> Erstellt: 2026-06-10  
> Ziel: ERA5-Klimadaten als zusätzliche Datenquelle für GDD-Berechnung und Ertragsmodellierung

---

## 1. ERA5-Land vs ERA5 Single Levels — Vergleich für GDD

### ERA5-Land (bevorzugt)
| Merkmal | Wert |
|---------|------|
| Auflösung | **0.1° × 0.1°** (~11 km) |
| Zeitraum | 1950–heute (mit ~3 Monaten Verzögerung) |
| Zeitliche Auflösung | Stündlich |
| Variablen | 2m-Temperatur, Niederschlag, Solarstrahlung (ssrd), Bodenfeuchte, etc. |
| Update | Täglich (mit Verzögerung) |
| Lizenz | Free / Open (CDS) |

**Vorteil für GDD:** Die höhere räumliche Auflösung (11 km vs 31 km) erfasst lokale Topographie-Effekte besser. Für wärmeliebende Kulturen wie Mais in südlichen EU-Regionen relevant.

### ERA5 Single Levels
| Merkmal | Wert |
|---------|------|
| Auflösung | **0.25° × 0.25°** (~31 km) |
| Zeitraum | 1940–heute |
| Zeitliche Auflösung | Stündlich |
| Variablen | 2m-Temperatur, total_precipitation, ssrd, Druck, Wind, etc. |
| Update | Täglich |

**Nachteil für GDD:** Gröbere Raster → Mittelung über größere Flächen → Verwässerung von Spitzenwerten (Heat-Stress, Frost). ERA5-Land ist für lokale Agrarmodellierung klar überlegen.

### Fazit GDD
| Aspekt | ERA5 (Single) | ERA5-Land | Bewertung |
|--------|--------------|-----------|-----------|
| GDD-Genauigkeit | Mittel | **Hoch** | ERA5-Land +1 Pkt |
| Datenvolumen | Niedriger | Höher | ERA5 +1 Pkt |
| Verfügbarkeit | Seit 1940 | Seit 1950 | Gleichwertig |
| Aktualität | ~3 Monate Verzögerung | ~3 Monate Verzögerung | Gleichwertig |

**→ Empfehlung: ERA5-Land verwenden für GDD. ERA5 Single Levels nur als Fallback.**

---

## 2. Auflösungsvergleich

| Quelle | Auflösung | Typ | Temperatur | Niederschlag | Solarstrahlung | Update | GDD-tauglich |
|--------|-----------|-----|-----------|-------------|----------------|--------|-------------|
| **ERA5-Land** | **0.1° (~11 km)** | Reanalyse | ✅ stündlich | ✅ stündlich | ✅ stündlich (ssrd) | ~3 Mo Verzögerung | ⭐⭐⭐ |
| ERA5 Single Levels | 0.25° (~31 km) | Reanalyse | ✅ stündlich | ✅ stündlich | ✅ stündlich | ~3 Mo Verzögerung | ⭐⭐ |
| **NASA POWER** | **0.5° (~55 km)** | Satellit + Modell | ✅ täglich | ✅ täglich | ✅ täglich | ~5 Tage Verzug | ⭐ |
| **Open-Meteo** | **~0.5° (postal)** | Gitter + Vorhersage | ✅ stündlich | ✅ stündlich | ✅ stündlich | Realtime + Forecast | ⭐⭐ |

### Bedeutung für Ertragsmodellierung

- **ERA5-Land (0.1°):** Erfasst Mikroklima-Effekte — Hanglagen, Flusstäler, städtische Wärmeinseln. Wichtig für EU-Regionen mit heterogener Topographie (Italien, Spanien, Österreich).
- **NASA POWER (0.5°):** Ein Rasterpunkt deckt ~3.000 km² ab. Für große, homogene Ebenen (Norddeutschland, Beauce/Frankreich) ausreichend. Aber: Überschätzt Tiefsttemperaturen in Tallagen.
- **Open-Meteo (0.5°):** Ähnlich NASA POWER, aber mit Forecast-Fähigkeit (7–16 Tage). Für Echtzeit-GDD aktuell besser als historische ERA5-Daten.

### NUTS2-Konsequenz
Ein NUTS2-Region (z.B. DEE0 Sachsen-Anhalt, ~20.000 km²) wird abgedeckt durch:
- **ERA5-Land:** ~165 Rasterpunkte → Mittelwertbildung sinnvoll
- **NASA POWER:** ~7 Rasterpunkte → zu grob
- **Open-Meteo:** ~7 Rasterpunkte → zu grob

---

## 3. Verfügbare Variablen im CDS

| Variable | CDS-Name | Einheit | CropProphEU-Relevanz |
|----------|----------|---------|---------------------|
| 2m-Temperatur | `2m_temperature` | K | **GDD-Berechnung** (Tagesmittel aus Stundenwerten) |
| Total Precipitation | `total_precipitation` | m | **Wasserbilanz** für Ertragsmodell |
| Surface Solar Radiation Downwards | `surface_solar_radiation_downwards` | J/m² | **PAR / Strahlungsnutzung** — bisher nicht genutzt |

### Weitere relevante ERA5-Land Variablen

| Variable | Relevanz |
|----------|----------|
| `volumetric_soil_water_layer_1` (Bodenfeuchte 0–7 cm) | Dürrestress-Indikator |
| `temperature_of_soil_level_1` (Bodentemperatur 0–7 cm) | Aussaatfenster, Keimung |
| `evaporation_from_bare_soil` | Wasserbilanz-Verfeinerung |
| `snow_depth_water_equivalent` | Winterkulturen, Frostschutz |

**Fokus Phase 1:** `2m_temperature` (GDD) + `total_precipitation` + `surface_solar_radiation_downwards`

---

## 4. API-Endpunkte und CDS-Key

### CDS (Copernicus Data Store)

```
API-Endpunkt: https://cds.climate.copernicus.eu/api
CDS-Key:      (persönlicher API-Key, Registrierung unter https://cds.climate.copernicus.eu/user/register)
```

### Authentifizierung

```python
import cdsapi

c = cdsapi.Client(
    url="https://cds.climate.copernicus.eu/api",
    key="<UID>:<API-KEY>"  # aus ~/.cdsapirc
)
```

Oder via Environment: `CDSAPI_URL` und `CDSAPI_KEY`

### Dataset-IDs

| Dataset | CDS-ID |
|---------|--------|
| ERA5-Land hourly | `reanalysis-era5-land` |
| ERA5 Single Levels hourly | `reanalysis-era5-single-levels` |

### Beispiel-Request (ERA5-Land, Deutschland, ganzes Jahr)

```python
c.retrieve(
    "reanalysis-era5-land",
    {
        "variable": ["2m_temperature", "total_precipitation", "surface_solar_radiation_downwards"],
        "year": "2024",
        "month": ["01","02","03","04","05","06","07","08","09","10","11","12"],
        "day": [f"{d:02d}" for d in range(1,32)],
        "time": [f"{h:02d}:00" for h in range(0,24)],
        "area": [55, 5, 47, 16],  # N/W/S/E Bounding Box DE
        "format": "netcdf"
    },
    "era5_land_de_2024.nc"
)
```

---

## 5. Datenvolumen pro NUTS2-Region (~100 Calls)

### Annahmen
- 1 NUTS2-Region (z.B. DEE0): ~20.000 km²
- ERA5-Land 0.1° → ~165 Rasterpunkte pro Region
- 1 Jahr = 365 Tage × 24 Stunden = 8.760 Zeitschritte
- 3 Variablen: Temperatur + Precipitation + Solarstrahlung

### Volumenabschätzung

| Szenario | Pro Request | 18 NUTS2-Regionen | 100 Calls (ganzes EU-Modell) |
|----------|-------------|-------------------|------------------------------|
| 1 Jahr, 1 Variable, Ganzdeutschland | ~50 MB | ~900 MB | — |
| 1 Jahr, 3 Variablen, 1 Region | ~15 MB | ~270 MB | ~1,5 GB |
| 5 Jahre, 3 Variablen, 1 Region | ~75 MB | ~1,35 GB | ~7,5 GB |
| 10 Jahre (Training), 3 Var., 1 Region | ~150 MB | ~2,7 GB | ~15 GB |

### CDS-Download-Limits
- CDS hat **kein explizites Volumen-Limit** aber **Request-Limit**: max. ~1 TB/Monat (fair use)
- Ein Request darf max. ~500 MB answer → ggf. aufteilen (1 Request pro Monat, nicht pro Jahr)
- Queueing: CDS stellt Requests in eine Warteschlange — große Requests brauchen 5–30 min

### Strategie
- **1 Region = 1 Request pro Monat** (statt 1 Request pro Jahr) → kleinere Antworten, schnellere Queue
- **18 Regionen × 12 Monate = 216 Requests** für 1 Jahr komplette Coverage
- Für Trainingsdaten: **1 Request pro Region (5 Jahre)** = 18 Requests
- **Gesamt First-Build: ~250 Requests**, ~5 GB NetCDF-Daten

---

## 6. Caching-Strategie

### Layer 1: NetCDF-Datei-Cache
```
/home/j/crop-mcp/cache/cds/
├── era5_land_2m_temperature_DEE0_2024.nc
├── era5_land_2m_temperature_DEE0_2025.nc
├── era5_land_total_precipitation_DEE0_2024.nc
└── ...
```

**Prinzip:** Heruntergeladene NetCDFs bleiben erhalten. Nur fehlende Monate/Jahre werden nachgeladen.

### Layer 2: Aggregierter NUTS2-Cache (für Modell-Training)
```
/home/j/crop-mcp/cache/cds/aggregated/
├── DEE0_daily_2024.csv
├── DEE0_daily_2025.csv
└── ...
```

Nach Download → stündliche NetCDF → Tageswerte aggregieren (GDD, Tagesniederschlag, Tagesstrahlung) → Region-Mittelwert → CSV speichern

### Layer 3: Feature-Cache (für ML-Modell)
```
/home/j/crop-mcp/data/cds_features/
├── wheat_features_2024.csv    # Enthält GDD, Precipitation, Solarradiation per NUTS2
└── ...
```

### Lifecycle
| Phase | Aktion | Caching-Ebene |
|-------|--------|---------------|
| Erst-Download | Alle Regionen, 5 Jahre, 3 Variablen | Layer 1 (Rohdaten) |
| Aggregation | Stunden → Tag → NUTS2-Mittelwert | Layer 2 (CSV) |
| Feature Engineering | GDD akkumulieren, Klimanormale berechnen | Layer 3 (ML-Features) |
| Monatliches Update | Neue Monate nachladen, neu aggregieren | Layer 1 (inkrementell) |

---

## 7. Aufwandsschätzung für Integration ins Modell

### Phase 1: Basis (3–5 Tage)
| Aufgabe | Aufwand | Details |
|---------|---------|---------|
| CDS-Account + API-Key einrichten | 0,5 h | Registrierung, ~/.cdsapirc |
| Download-Skript ERA5-Land | 4 h | Parametrisiert: Region, Jahr, Variablen |
| NetCDF-Parsing und Tagesaggregation | 3 h | Stunden → Tageswerte (GDD, Precip, Strahlung) |
| NUTS2-Region-Mittelung | 2 h | Rasterpunkte → Regionsmittel |
| Caching-Layer 1 + 2 | 2 h | Dateiorganisation, Prüfung auf Cache-Hit |
| **Summe** | **~12 h** | |

### Phase 2: Feature Engineering (3–4 Tage)
| Aufgabe | Aufwand | Details |
|---------|---------|---------|
| GDD-akkumulieren (Saat–Ernte) | 3 h | Basis- und Cutoff-Temperatur pro Kultur |
| Klimanormale (1981–2010) berechnen | 2 h | Langjähriges Mittel für Anomalie-Scores |
| Extremwert-Indikatoren (Frost, Hitzestress) | 3 h | Tage > 30°C, < 0°C während Wachstumsphase |
| Solarstrahlung → PAR → Biomasse | 2 h | Strahlungsnutzungseffizienz (RUE) |
| Integration ins bestehende Feature-Set | 4 h | CSV-Format an `build_europe.py` anpassen |
| **Summe** | **~14 h** | |

### Phase 3: Modell-Integration und Validierung (5–7 Tage)
| Aufgabe | Aufwand | Details |
|---------|---------|---------|
| ERA5-Features in Training-Pipeline | 6 h | `build_europe.py` erweitern, neue Spalten |
| Modell-Neutraining + Hyperparameter | 8 h | LightGBM mit neuen Features, Feature-Importance |
| Kreuzvalidierung: ERA5 vs NASA POWER | 4 h | Gleiches Modell, unterschiedliche Wetterquellen |
| MAE-Vergleich | 2 h | Ist ERA5 ein signifikanter Verbesserung? |
| Fallback-Logik (NASA POWER wenn ERA5 nicht verfügbar) | 4 h | Failover bei CDS-Ausfall |
| **Summe** | **~24 h** | |

### Gesamtaufwand
| Phase | Stunden | Tage (bei 6 h/Tag) |
|-------|---------|--------------------|
| Phase 1: Basis | 12 h | 2 Tage |
| Phase 2: Feature Engineering | 14 h | 2,5 Tage |
| Phase 3: Modell-Integration | 24 h | 4 Tage |
| **Gesamt** | **50 h** | **~8–9 Arbeitstage** |

### Risiken
| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| CDS-Queue zu langsam | Mittel | Hoch | Requests auf Monatsbasis, parallele Requests |
| API-Key nicht verfügbar | Gering | Blockierend | ASAP registrieren |
| ERA5-Land zu große Datenmenge | Mittel | Mittel | Nur 1 Variable pro Request, komprimiertes NetCDF |
| ERA5 bringt keine Verbesserung | Mittel | Mittel | Vorab-Test mit 2 Regionen vor Vollintegration |
| ~3 Monate Verzögerung vs ~5 Tage (NASA POWER) | Hoch | Niedrig | Für historisches Training egal; für Echtzeit NASA POWER nutzen |

---

## 8. Nächste Schritte

1. **CDS-Registrierung** → https://cds.climate.copernicus.eu/user/register → API-Key generieren
2. **Test-Download** → 1 Region, 1 Monat, 3 Variablen → Pipeline testen
3. **GDD-Vergleich** → ERA5-Land GDD vs Open-Meteo GDD für 3 Teststationen
4. **Feature-Importance-Test** → LightGBM mit/ohne ERA5-Features trainieren
5. **Go/No-Go** → Entscheidung ob Vollintegration (Phase 3) basierend auf MAE-Verbesserung
