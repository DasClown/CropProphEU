#!/usr/bin/env python3
"""
Environmental Risk Score (ERS) + Wildschaden-Risiko
====================================================
Option 1: ERS für alle EU NUTS2-Regionen (Waldanteil, Maisfläche, 
          Klimarisiko, Bodenerosion) — 3-stufig 🟢🟡🔴
Option 2: Wildschaden-Modul DE (DJV-Daten + Corine Land Cover)

V5.4 — Neu: 2026-05-14
"""

import json
import math
import os
from typing import Optional

# ─────────────────────────────────────────────────────────────
# FOREST COVER (% Waldanteil) je NUTS2-Region
# Quelle: Eurostat LULUCF, Corine Land Cover 2018 (geschätzt)
# ─────────────────────────────────────────────────────────────
# Hohe Werte (>40%): Skandinavien, Alpen, süddeutsche Mittelgebirge
# Mittlere Werte (20-40%): Norddeutschland, Frankreich Zentralmassiv
# Niedrige Werte (<20%): Po-Ebene, Pannonische Tiefebene, Ile-de-France
FOREST_COVER_PCT: dict[str, float] = {
    # ── Deutschland ──
    "DE11": 35.0, "DE12": 38.0, "DE13": 42.0, "DE14": 38.0,  # BW
    "DE21": 30.0, "DE22": 32.0, "DE23": 33.0, "DE24": 40.0, "DE25": 38.0, "DE26": 36.0, "DE27": 35.0,  # Bayern
    "DE30": 32.0,  # Berlin
    "DE40": 35.0, "DE41": 37.0, "DE42": 35.0,  # Brandenburg
    "DE50": 20.0,  # Bremen
    "DE60": 25.0, "DE61": 22.0, "DE62": 20.0, "DE63": 25.0, "DE64": 24.0, "DE65": 23.0, "DE66": 22.0, "DE67": 21.0,  # Niedersachsen
    "DE71": 38.0, "DE72": 40.0, "DE73": 38.0,  # Hessen
    "DE80": 22.0, "DE81": 20.0, "DE82": 18.0,  # Mecklenburg-Vorpommern
    "DE91": 22.0, "DE92": 22.0, "DE93": 24.0, "DE94": 23.0,  # Niedersachsen
    "DEA1": 35.0, "DEA2": 33.0, "DEA3": 30.0, "DEA4": 32.0, "DEA5": 34.0,  # NRW
    "DEB1": 38.0, "DEB2": 40.0, "DEB3": 35.0,  # Rheinland-Pfalz
    "DEC0": 35.0,  # Saarland
    "DED2": 28.0, "DED4": 25.0, "DED5": 26.0,  # Sachsen
    "DEE0": 22.0, "DEE1": 20.0, "DEE2": 18.0, "DEE3": 19.0, "DEE4": 17.0, "DEE5": 21.0, "DEE6": 20.0,  # Sachsen-Anhalt
    "DEF0": 12.0,  # Schleswig-Holstein
    "DEG0": 32.0, "DEG1": 30.0,  # Thüringen
    # ── Frankreich ──
    "FR10": 20.0, "FRB0": 22.0, "FRC1": 25.0, "FRC2": 28.0,
    "FRD1": 30.0, "FRD2": 28.0, "FRE1": 18.0, "FRE2": 20.0,
    "FRF1": 18.0, "FRF2": 16.0, "FRF3": 15.0,
    "FRG0": 12.0, "FRH0": 10.0,
    "FRI0": 35.0, "FRI1": 32.0, "FRI2": 30.0,
    "FRJ1": 32.0, "FRJ2": 30.0, "FRK1": 35.0, "FRK2": 38.0,
    "FRL0": 18.0, "FRM0": 15.0,
    "FRY1": 38.0, "FRY2": 35.0, "FRY3": 30.0, "FRY4": 28.0,
    "FRZ1": 18.0, "FRZ2": 20.0,
    # ── Polen ──
    "PL11": 22.0, "PL12": 23.0, "PL21": 30.0, "PL22": 32.0,
    "PL31": 24.0, "PL32": 25.0, "PL33": 26.0, "PL34": 24.0,
    "PL41": 22.0, "PL42": 28.0, "PL43": 25.0,
    "PL51": 28.0, "PL52": 26.0, "PL61": 20.0, "PL62": 22.0, "PL63": 28.0,
    "PL71": 25.0, "PL72": 24.0, "PL81": 26.0, "PL82": 24.0,
    "PL91": 22.0, "PL92": 23.0,
    # ── Rumänien ──
    "RO11": 30.0, "RO12": 32.0, "RO21": 28.0, "RO22": 20.0,
    "RO31": 18.0, "RO32": 20.0, "RO41": 22.0, "RO42": 24.0,
    # ── Ungarn ──
    "HU10": 22.0, "HU11": 20.0, "HU12": 18.0,
    "HU21": 22.0, "HU22": 20.0, "HU23": 18.0,
    "HU31": 25.0, "HU32": 22.0, "HU33": 15.0,
    # ── Italien ──
    "ITC1": 35.0, "ITC2": 38.0, "ITC3": 30.0, "ITC4": 28.0,
    "ITF1": 30.0, "ITF2": 32.0, "ITF3": 25.0, "ITF4": 35.0, "ITF5": 22.0, "ITF6": 28.0,
    "ITG1": 38.0, "ITG2": 40.0, "ITG3": 35.0,
    "ITH1": 25.0, "ITH2": 28.0, "ITH3": 30.0, "ITH4": 32.0, "ITH5": 35.0,
    "ITI1": 35.0, "ITI2": 38.0, "ITI3": 40.0, "ITI4": 42.0,
    # ── Spanien ──
    "ES11": 30.0, "ES12": 35.0, "ES13": 32.0,
    "ES21": 28.0, "ES22": 25.0, "ES23": 30.0, "ES24": 22.0,
    "ES30": 35.0,
    "ES41": 18.0, "ES42": 15.0, "ES43": 22.0,
    "ES51": 28.0, "ES52": 30.0, "ES53": 25.0,
    "ES61": 20.0, "ES62": 18.0, "ES63": 15.0, "ES64": 22.0, "ES65": 21.0,
    "ES70": 12.0,
    # ── UK ──
    "UKC1": 10.0, "UKC2": 12.0, "UKD1": 8.0, "UKD3": 9.0, "UKD4": 10.0, "UKD6": 11.0, "UKD7": 10.0,
    "UKE1": 8.0, "UKE2": 7.0, "UKE3": 8.0, "UKE4": 9.0,
    "UKF1": 12.0, "UKF2": 14.0, "UKF3": 13.0,
    "UKG1": 15.0, "UKG2": 14.0, "UKG3": 16.0,
    "UKH1": 8.0, "UKH2": 10.0, "UKH3": 9.0,
    "UKI3": 12.0, "UKI4": 11.0, "UKI5": 10.0, "UKI6": 12.0,
    "UKJ1": 10.0, "UKJ2": 12.0, "UKJ3": 14.0, "UKJ4": 13.0,
    "UKK1": 8.0, "UKK2": 10.0, "UKK3": 9.0,
    "UKL1": 8.0, "UKL2": 10.0,
    "UKM5": 15.0, "UKM6": 18.0, "UKM7": 14.0, "UKM8": 13.0, "UKM9": 16.0,
    "UKN0": 14.0,
    "UKZ0": 0.0,
    # ── Dänemark ──
    "DK01": 12.0, "DK02": 14.0, "DK03": 15.0, "DK04": 13.0, "DK05": 14.0,
    # ── Niederlande ──
    "NL11": 8.0, "NL12": 6.0, "NL13": 10.0, "NL21": 12.0, "NL22": 14.0,
    "NL23": 10.0, "NL31": 8.0, "NL32": 7.0, "NL33": 6.0, "NL34": 5.0,
    "NL41": 14.0, "NL42": 16.0,
    # ── Belgien ──
    "BE10": 15.0, "BE21": 14.0, "BE22": 16.0, "BE23": 10.0,
    "BE24": 12.0, "BE25": 8.0,
    "BE31": 22.0, "BE32": 18.0, "BE33": 25.0, "BE34": 24.0, "BE35": 22.0,
    # ── Österreich ──
    "AT11": 28.0, "AT12": 35.0, "AT13": 42.0,
    "AT21": 40.0, "AT22": 42.0, "AT31": 38.0, "AT32": 40.0, "AT33": 42.0,
    "AT34": 45.0,
    # ── Schweden ──
    "SE11": 60.0, "SE12": 55.0, "SE21": 65.0, "SE22": 45.0, "SE23": 50.0, "SE31": 70.0, "SE32": 68.0, "SE33": 72.0,
    # ── Finnland ──
    "FI19": 68.0, "FI1B": 70.0, "FI1C": 62.0, "FI1D": 65.0, "FI20": 75.0,
    # ── Bulgarien ──
    "BG31": 28.0, "BG32": 25.0, "BG33": 22.0, "BG34": 20.0, "BG41": 35.0, "BG42": 30.0,
    # ── Tschechien ──
    "CZ01": 25.0, "CZ02": 28.0, "CZ03": 30.0, "CZ04": 28.0, "CZ05": 30.0, "CZ06": 28.0, "CZ07": 30.0, "CZ08": 32.0,
    # ── Kroatien ──
    "HR02": 32.0, "HR03": 35.0, "HR04": 38.0, "HR05": 40.0,
    # ── Irland ──
    "IE04": 10.0, "IE05": 10.0, "IE06": 12.0,
    # ── Litauen ──
    "LT01": 35.0, "LT02": 33.0,
    # ── Lettland ──
    "LV00": 40.0,
    # ── Estland ──
    "EE00": 45.0,
    # ── Slowakei ──
    "SK01": 35.0, "SK02": 30.0, "SK03": 32.0, "SK04": 35.0,
    # ── Slowenien ──
    "SI03": 55.0, "SI04": 58.0,
    # ── Portugal ──
    "PT11": 35.0, "PT15": 30.0, "PT16": 35.0, "PT17": 25.0, "PT18": 22.0,
    # ── Griechenland ──
    "EL51": 25.0, "EL52": 22.0, "EL53": 20.0, "EL54": 28.0,
    "EL61": 18.0, "EL62": 22.0, "EL63": 25.0, "EL64": 24.0, "EL65": 20.0,
    # ── Ukraine ──
    "UA01": 15.0, "UA02": 14.0, "UA03": 16.0, "UA04": 12.0,
    "UA05": 14.0, "UA06": 18.0, "UA07": 15.0, "UA08": 13.0,
    "UA09": 12.0, "UA10": 10.0, "UA11": 8.0, "UA12": 14.0, "UA13": 15.0,
    "UA14": 16.0, "UA15": 18.0, "UA16": 14.0, "UA17": 13.0, "UA18": 12.0, "UA19": 16.0,
    "UA20": 15.0, "UA21": 12.0, "UA22": 10.0, "UA23": 14.0, "UA24": 15.0, "UA25": 13.0, "UA26": 11.0,
    # ── Zypern ──
    "CY00": 18.0,
    # ── Malta ──
    "MT00": 5.0,
}

# ─────────────────────────────────────────────────────────────
# SOIL EROSION RISK (t/ha/a) — RUSLE2015 JRC Schätzung
# Werte: 0-20 t/ha/a. >10 = hoch, 5-10 = mittel, <5 = niedrig
# ─────────────────────────────────────────────────────────────
SOIL_EROSION_T_HA: dict[str, float] = {
    # DE: Norddeutsches Tiefland <5, Mittelgebirge 5-10
    "DE11": 6.0, "DE12": 7.0, "DE13": 8.0, "DE14": 7.0,
    "DE21": 5.0, "DE22": 4.0, "DE23": 3.0, "DE24": 6.0, "DE25": 5.0, "DE26": 4.0, "DE27": 5.0,
    "DE30": 2.0,
    "DE40": 3.0, "DE41": 4.0, "DE42": 3.0,
    "DE50": 1.0,
    "DE60": 3.0, "DE61": 3.0, "DE71": 6.0, "DE72": 7.0, "DE73": 6.0,
    "DE80": 2.0, "DE91": 3.0, "DEE0": 5.0,
    "DEF0": 2.0, "DEG0": 5.0,
    # FR: Becken <5, Zentralmassiv >10
    "FR10": 3.0, "FRB0": 4.0, "FRF1": 6.0, "FRF2": 5.0, "FRF3": 4.0,
    "FRG0": 3.0, "FRH0": 5.0,
    "FRI0": 8.0, "FRJ1": 10.0,
    # PL: Norden <5, Süden >8
    "PL41": 5.0, "PL42": 4.0, "PL51": 7.0, "PL52": 8.0, "PL61": 4.0, "PL63": 3.0,
    # ES: Trockengebiete >10, feuchter Norden <5
    "ES42": 8.0, "ES61": 10.0, "ES24": 6.0, "ES43": 7.0,
    # IT: Po-Ebene <3, Alpen >8, Apennin >6
    "ITC4": 3.0, "ITF5": 4.0, "ITF3": 3.0, "ITC2": 5.0,
    # Default für unbekannte Regionen
    "_default": 5.0,
}

# ─────────────────────────────────────────────────────────────
# CLIMATE HAZARD INDEX (Sturm + Hagel + Überschwemmung)
# Jeweils 1-5 basierend auf ESWD/European Severe Weather DB
# ─────────────────────────────────────────────────────────────
STORM_RISK: dict[str, int] = {
    # DE: Norden mehr Sturm, Süden mehr Hagel
    "DE91": 4, "DEF0": 4, "DE80": 4,  # Norddeutschland → höheres Sturmrisiko
    "DE21": 2, "DE22": 2, "DE26": 2, "DE24": 2,  # Bayern → Hagel > Sturm
    "DEE0": 3, "DEG0": 3,  # Mitteldeutschland → mäßig
    "DE71": 3, "DE72": 3, "DE73": 3,
    "DE11": 3, "DE12": 3, "DE13": 4, "DE14": 3,
    # FR: Nordwesten mehr Sturm
    "FRF1": 3, "FRF2": 3, "FRF3": 3, "FRB0": 3,
    "FRG0": 4, "FRH0": 4,
    "FRI0": 3, "FRJ1": 2,
    # UK: generell hohes Sturmrisiko
    "UKH1": 4, "UKJ2": 3, "UKF1": 4, "UKE0": 4,
    # IT: niedriges Sturmrisiko, aber Hagel in Po-Ebene
    "ITC4": 2, "ITF5": 3, "ITF3": 2,
    # ES: niedrig
    "ES42": 2, "ES61": 2, "ES24": 2,
    # HU/RO: Trockenheit > Sturm
    "HU10": 2, "HU33": 2, "RO31": 2, "RO11": 2,
    "_default": 2,
}

HAIL_RISK: dict[str, int] = {
    # DE: Baden-Württemberg + Bayern = Hagel-Hotspots
    "DE11": 4, "DE12": 4, "DE13": 3, "DE14": 4,
    "DE21": 4, "DE22": 4, "DE23": 3, "DE24": 3, "DE25": 3, "DE26": 3, "DE27": 3,
    "DE71": 3, "DE72": 3, "DE73": 3,
    "DE91": 2, "DEE0": 2, "DEF0": 1, "DE80": 1,
    # FR: Zentralmassiv + Südosten
    "FRI0": 3, "FRJ1": 3, "FRK2": 3,
    "FRB0": 2, "FRF1": 2, "FRF2": 2, "FRF3": 2,
    # IT: Po-Ebene Hagel
    "ITC4": 3, "ITF5": 3, "ITF3": 3,
    # Andere
    "UKH1": 1, "UKJ2": 2, "ES42": 2, "ES61": 2,
    "HU10": 3, "HU33": 3,
    "_default": 2,
}

# ─────────────────────────────────────────────────────────────
# MAISFLÄCHENANTEIL (% der Ackerfläche) — geschätzt aus Eurostat
# ─────────────────────────────────────────────────────────────
CORN_ARABLE_SHARE: dict[str, float] = {
    # DE: Norden/Westen mehr Mais
    "DE91": 25.0, "DE92": 22.0, "DE93": 24.0, "DE94": 23.0,
    "DEE0": 12.0, "DEG0": 14.0, "DEF0": 8.0, "DE80": 8.0,
    "DE21": 18.0, "DE22": 20.0, "DE23": 15.0, "DE24": 12.0, "DE25": 14.0, "DE26": 16.0, "DE27": 14.0,
    "DE11": 10.0, "DE12": 12.0, "DE13": 8.0, "DE14": 10.0,
    "DE71": 15.0, "DE72": 14.0, "DE73": 12.0,
    # FR
    "FRB0": 18.0, "FRE1": 22.0, "FRI0": 25.0, "FRJ1": 20.0,
    "FRG0": 20.0, "FRH0": 25.0, "FRF1": 12.0, "FRF2": 14.0, "FRF3": 10.0,
    # PL
    "PL41": 15.0, "PL12": 12.0, "PL51": 10.0,
    # RO (Mais-intensive Länder)
    "RO31": 35.0, "RO11": 28.0, "RO21": 25.0, "RO41": 30.0,
    # HU
    "HU33": 35.0, "HU21": 28.0, "HU31": 22.0,
    # IT
    "ITC4": 30.0, "ITF5": 28.0, "ITF3": 25.0, "ITC2": 22.0,
    # ES
    "ES42": 20.0, "ES24": 15.0, "ES43": 18.0,
    "_default": 10.0,
}

# ─────────────────────────────────────────────────────────────
# SCHWARZWILD-DICHTE DE (Jagdstrecke pro 100 ha Wald)
# Quelle: DJV Jagdbericht 2023/2024, Bundesländer-Schätzungen
# Werte: Stück Schwarzwild pro 100 ha Waldfläche
# ─────────────────────────────────────────────────────────────
WILD_BOAR_PER_100HA_FOREST: dict[str, float] = {
    # DE Bundesländer → NUTS2 Mapping
    "DE11": 8.5, "DE12": 8.5, "DE13": 8.5, "DE14": 8.5,   # BW (ges.)
    "DE21": 12.0, "DE22": 12.0, "DE23": 12.0, "DE24": 12.0, "DE25": 12.0, "DE26": 12.0, "DE27": 12.0,  # BY (ges.)
    "DE30": 5.0,  # Berlin
    "DE40": 18.0, "DE41": 18.0, "DE42": 18.0,  # BB → höchste Dichte (ASF-Kernzone)
    "DE50": 4.0,  # Bremen
    "DE60": 15.0, "DE61": 15.0, "DE62": 15.0, "DE63": 15.0, "DE64": 15.0, "DE65": 15.0, "DE66": 15.0, "DE67": 15.0,  # NI
    "DE71": 11.0, "DE72": 11.0, "DE73": 11.0,  # HE
    "DE80": 14.0, "DE81": 14.0, "DE82": 14.0,  # MV
    "DE91": 10.0, "DE92": 10.0, "DE93": 10.0, "DE94": 10.0,  # NI (Rest)
    "DEA1": 9.0, "DEA2": 9.0, "DEA3": 9.0, "DEA4": 9.0, "DEA5": 9.0,  # NW
    "DEB1": 12.0, "DEB2": 12.0, "DEB3": 12.0,  # RP
    "DEC0": 10.0,  # SL
    "DED2": 16.0, "DED4": 16.0, "DED5": 16.0,  # SN (ASF-Betroffen)
    "DEE0": 15.0, "DEE1": 15.0, "DEE2": 15.0, "DEE3": 15.0, "DEE4": 15.0, "DEE5": 15.0, "DEE6": 15.0,  # ST
    "DEF0": 8.0,  # SH
    "DEG0": 13.0, "DEG1": 13.0,  # TH
}

# ─────────────────────────────────────────────────────────────
# DUMMY-VALUES für unbekannte Codes
# ─────────────────────────────────────────────────────────────
def _safe_get(d: dict, key: str, default=None):
    """Get value from dict, fallback to _default or provided default."""
    if key in d:
        return d[key]
    if "_default" in d:
        return d["_default"]
    return default


# ─────────────────────────────────────────────────────────────
# OPTION 1: ENVIRONMENTAL RISK SCORE (ERS)
# ─────────────────────────────────────────────────────────────
def compute_ers(
    region_code: str,
    country: str = "",
    forest_pct: float | None = None,
    corn_share: float | None = None,
    erosion: float | None = None,
    storm: int | None = None,
    hail: int | None = None,
) -> dict:
    """
    Environmental Risk Score (ERS) für eine NUTS2-Region.
    
    Returns dict mit Einzelwerten, Gesamtscore und Ampel.
    """
    # Daten holen (aus dicts oder übergebenen Werten)
    fc = forest_pct if forest_pct is not None else _safe_get(FOREST_COVER_PCT, region_code, 20.0)
    cs = corn_share if corn_share is not None else _safe_get(CORN_ARABLE_SHARE, region_code, 10.0)
    er = erosion if erosion is not None else _safe_get(SOIL_EROSION_T_HA, region_code, 5.0)
    sr = storm if storm is not None else _safe_get(STORM_RISK, region_code, 2)
    hr = hail if hail is not None else _safe_get(HAIL_RISK, region_code, 2)
    
    # Teil-Scores (jeweils 0-100)
    # Waldanteil: Risiko steigt mit hohem Waldanteil (Wildschweine!)
    forest_score = min(100, fc * 2.0)
    
    # Maisflächenanteil: Risiko steigt mit mehr Mais (Nahrung für Wildschweine)
    corn_score = min(100, cs * 2.5)  # 40% Mais → 100 Score
    
    # Bodenerosion: linear
    erosion_score = min(100, er * 8.0)  # 12.5 t/ha → 100
    
    # Sturmrisiko: 1-5 → 0-100
    storm_score = (sr - 1) * 25
    
    # Hagelrisiko: 1-5 → 0-100
    hail_score = (hr - 1) * 25
    
    # Gewichteter Gesamtscore
    # Wald + Mais = Wildrisiko (35%), Erosion (20%), Sturm (25%), Hagel (20%)
    wild_component = forest_score * 0.5 + corn_score * 0.5
    total = (
        wild_component * 0.35 +
        erosion_score * 0.20 +
        storm_score * 0.25 +
        hail_score * 0.20
    )
    
    # Ampel
    if total >= 65:
        traffic_light = "🔴 high"
        level = "high"
    elif total >= 35:
        traffic_light = "🟡 moderate"
        level = "moderate"
    else:
        traffic_light = "🟢 low"
        level = "low"
    
    return {
        "region_code": region_code,
        "ers_score": round(total, 1),
        "ers_level": level,
        "ers_traffic_light": traffic_light,
        "components": {
            "forest_cover_pct": round(fc, 1),
            "forest_risk_score": round(forest_score, 1),
            "corn_arable_share_pct": round(cs, 1),
            "corn_risk_score": round(corn_score, 1),
            "soil_erosion_t_ha": round(er, 1),
            "erosion_score": round(erosion_score, 1),
            "storm_risk_1_5": sr,
            "storm_score": round(storm_score, 1),
            "hail_risk_1_5": hr,
            "hail_score": round(hail_score, 1),
            "wild_component_score": round(wild_component, 1),
        },
        "description": (
            f"Environmental Risk: {traffic_light} "
            f"(Score: {total:.0f}/100. Forest: {fc:.0f}%, "
            f"Corn: {cs:.0f}%, Erosion: {er:.1f} t/ha/a, "
            f"Storm: {sr}/5, Hail: {hr}/5)"
        ),
    }


# ─────────────────────────────────────────────────────────────
# OPTION 2: WILDSCHADEN-RISIKO DEUTSCHLAND
# ─────────────────────────────────────────────────────────────
def compute_wild_boar_risk(
    region_code: str,
    forest_pct: float | None = None,
    corn_share: float | None = None,
    is_germany: bool = True,
) -> dict:
    """
    Wildschaden-Risiko für deutsche NUTS2-Regionen.
    
    Basiert auf:
    - DJV-Schwarzwilddichte (Stück/100 ha Wald)
    - Waldanteil in der Region
    - Maisflächenanteil (Nahrungsangebot)
    - Waldrand-Wahrscheinlichkeit (geschätzt)
    """
    # Nur für DE Regionen sinnvoll, sonst Proxy
    if not is_germany:
        wb_density = 8.0
    else:
        wb_density = _safe_get(WILD_BOAR_PER_100HA_FOREST, region_code, 8.0)
    
    fc = forest_pct if forest_pct is not None else _safe_get(FOREST_COVER_PCT, region_code, 20.0)
    cs = corn_share if corn_share is not None else _safe_get(CORN_ARABLE_SHARE, region_code, 10.0)
    
    # Waldrand-Index: höher wenn Wald- und Ackerflächen durchmischt
    # Maximal bei ~40% Wald: genug Wald für Deckung, genug Acker für Nahrung
    if fc < 5:
        edge_index = 0.1  # Kein Wald → kein Wildschweinproblem
    elif fc < 20:
        edge_index = 0.5 + fc / 100  # Wenig Wald → wenig Konfliktfläche
    elif fc < 45:
        edge_index = 1.0 - abs(fc - 35) / 100  # Optimal bei 35% Wald
    else:
        edge_index = 0.4 + (50 - fc) / 100  # Viel Wald → Wild hält sich im Wald auf
    
    edge_index = max(0.1, min(1.0, edge_index))
    
    # Roh-Score: 0-100
    raw_score = (wb_density / 20.0 * 50) + (edge_index * 30) + (min(cs, 40) / 40 * 20)
    raw_score = min(100, raw_score)
    
    # Ampel
    if raw_score >= 55:
        level = "high"
        traffic = "🔴"
        warning = "Hohes Wildschadenrisiko. Waldrand-Management + Jagddruck empfohlen."
    elif raw_score >= 30:
        level = "moderate"
        traffic = "🟡"
        warning = "Mäßiges Wildschadenrisiko. Beobachtung empfohlen."
    else:
        level = "low"
        traffic = "🟢"
        warning = "Niedriges Wildschadenrisiko."
    
    # Schätzung des finanziellen Risikos (€/ha/a für Mais)
    if is_germany:
        if level == "high":
            estimated_loss_eur_ha = 120 + (raw_score - 55) * 3  # 120-255 €/ha
        elif level == "moderate":
            estimated_loss_eur_ha = 30 + (raw_score - 30) * 2  # 30-80 €/ha
        else:
            estimated_loss_eur_ha = 0  # <30 €/ha
        estimated_loss_eur_ha = round(min(250, max(0, estimated_loss_eur_ha)))
    else:
        estimated_loss_eur_ha = None  # Nur für DE geschätzt
    
    return {
        "region_code": region_code,
        "wild_boar_risk_score": round(raw_score, 1),
        "wild_boar_risk_level": level,
        "wild_boar_traffic_light": f"{traffic} {level}",
        "components": {
            "wild_boar_density_per_100ha_forest": round(wb_density, 1),
            "forest_cover_pct": round(fc, 1),
            "forest_edge_index": round(edge_index, 3),
            "corn_arable_share_pct": round(cs, 1),
        },
        "estimated_loss_eur_per_ha": estimated_loss_eur_ha,
        "management_notes": [
            "Waldrand-Management: 3-6m Randstreifen reduziert Schaden 30-40%",
            "Bayern: 8-Tage-Anzeigefrist §36 BayJG beachten",
            "Drückjagd Nov-Dez auf Maisfeldern vor Ernte",
            "Nach Mais → Sommergerste/Hafer im Waldrandbereich",
        ] if level in ("high", "moderate") else [],
        "warning": warning,
        "description": (
            f"Wildschaden: {traffic} {level} "
            f"(Score: {raw_score:.0f}/100. Schwarzwilddichte: {wb_density:.1f}/100ha, "
            f"Wald: {fc:.0f}%, Mais: {cs:.0f}%)"
            + (f" → Geschätzter Verlust: ~{estimated_loss_eur_ha} €/ha/a für Mais"
               if estimated_loss_eur_ha else "")
        ),
    }


# ─────────────────────────────────────────────────────────────
# COMPOSITE: Vollständige Umweltrisiko-Analyse
# ─────────────────────────────────────────────────────────────
def full_environmental_risk(
    region_code: str,
    country: str = "",
) -> dict:
    """
    Vollständige Umweltrisiko-Analyse für eine Region.
    Kombiniert ERS + Wildschaden.
    """
    is_de = country == "DE" or region_code.startswith("DE")
    
    ers = compute_ers(region_code, country)
    wild = compute_wild_boar_risk(region_code, is_germany=is_de)
    
    # Gesamt-Risiko (höchster Einzelwert ausschlaggebend)
    max_score = max(ers["ers_score"], wild["wild_boar_risk_score"] if is_de else ers["ers_score"])
    
    if max_score >= 65:
        overall = "🔴 high"
    elif max_score >= 35:
        overall = "🟡 moderate"
    else:
        overall = "🟢 low"
    
    result = {
        "region_code": region_code,
        "country": country,
        "overall_risk": overall,
        "overall_score": round(max_score, 1),
        "environmental_risk_score": ers,
        "wild_boar_risk": wild if is_de else {
            "note": "Wild boar risk model currently available for DE only",
            "wild_boar_risk_score": 0,
            "wild_boar_risk_level": "n/a",
        },
        "summary": (
            f"🌍 {region_code}: Umwelt {ers['ers_traffic_light']}"
            + (f" | 🐗 Wildschwein {wild['wild_boar_traffic_light']}"
               if is_de else "")
        ),
    }
    return result


# ─────────────────────────────────────────────────────────────
# ERS für alle NUTS2 (compare_regions-Support)
# ─────────────────────────────────────────────────────────────
def batch_ers(region_codes: list[str]) -> list[dict]:
    """ERS für eine Liste von Regionen."""
    results = []
    for code in region_codes:
        try:
            country = code[:2]
            r = full_environmental_risk(code, country)
            results.append(r)
        except Exception as e:
            results.append({
                "region_code": code,
                "error": str(e)[:100],
            })
    return results


# ─────────────────────────────────────────────────────────────
# Selftest
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    
    print("=" * 60)
    print("OPTION 1: Environmental Risk Score (ERS)")
    print("=" * 60)
    
    test_regions = [
        ("DE26", "DE"),   # Unterfranken (Maßbach!)
        ("DE91", "DE"),   # Niedersachsen (Mais intensiv)
        ("DEE0", "DE"),   # Sachsen-Anhalt
        ("DEF0", "DE"),   # Schleswig-Holstein
        ("FRB0", "FR"),   # Centre-Val de Loire
        ("ITC4", "IT"),   # Lombardei
        ("HU33", "HU"),   # Dél-Alföld (Trocken!)
        ("RO31", "RO"),   # Sud-Muntenia
        ("ES42", "ES"),   # Castilla y León
        ("UA11", "UA"),   # Ukraine Odessa
    ]
    
    for code, country in test_regions:
        r = full_environmental_risk(code, country)
        print(f"\n{code} ({country}):")
        print(f"  Gesamt: {r['overall_risk']} (Score: {r['overall_score']:.0f})")
        print(f"  ERS: {r['environmental_risk_score']['ers_traffic_light']} "
              f"(Score: {r['environmental_risk_score']['ers_score']:.0f})")
        wb = r.get("wild_boar_risk", {})
        if wb.get("wild_boar_risk_level") and wb["wild_boar_risk_level"] != "n/a":
            print(f"  Wildschwein: {wb['wild_boar_traffic_light']} "
                  f"(Verlust: ~{wb.get('estimated_loss_eur_per_ha', 'n/a')} €/ha/a)")
        print(f"  {r['summary']}")
    
    print("\n")
    print("=" * 60)
    print("VERGLEICH: Maßbach-relevante DE-Regionen")
    print("=" * 60)
    
    for code, country in [("DE26", "DE"), ("DE71", "DE"), ("DE21", "DE"), ("DEE0", "DE")]:
        r = full_environmental_risk(code, country)
        wb = r.get("wild_boar_risk", {})
        print(f"  {code} → ERS: {r['environmental_risk_score']['ers_traffic_light']:12s} | "
              f"Wild: {wb.get('wild_boar_traffic_light', 'n/a'):12s} | "
              f"Verlust: {wb.get('estimated_loss_eur_per_ha', 'n/a')} €/ha")
