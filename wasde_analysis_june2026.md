# WASDE June 2026 — Anchor Forecast Verifikation

**Erstellt:** 2026-06-12 (Cron Job)
**Quellen:** USDA WASDE-672 (2026-06-11), USDA FAS World Agricultural Production (June 2026)
**Anchors:** Pre-WASDE, 2026-05-15, Bitcoin-verifiziert via OpenTimestamps

---

## 1. WASDE June 2026 — Kernzahlen

### EU Wheat (2026/27 Projection)

| Kennzahl | Mai WASDE | **Juni WASDE** | Δ |
|----------|-----------|----------------|---|
| Anbaufläche | 23.60 Mha | **23.60 Mha** | 0 |
| Ertrag | 5.76 t/ha | **5.76 t/ha** | 0 |
| **Produktion** | 136.00 MMT | **136.00 MMT** | 0 |
| Exporte | 31.00 MMT | **31.00 MMT** | 0 |
| Endbestände | 14.97 MMT | **14.63 MMT** | −0.34 |

### EU Corn (Maize, 2026/27 Projection)

| Kennzahl | Mai WASDE | **Juni WASDE** | Δ |
|----------|-----------|----------------|---|
| Anbaufläche | 7.80 Mha | **7.80 Mha** | 0 |
| Ertrag | 7.37 t/ha | **7.37 t/ha** | 0 |
| **Produktion** | 57.50 MMT | **57.50 MMT** | 0 |
| Endbestände | 5.38 MMT | **5.38 MMT** | 0 |

### EU Rapeseed (2026/27 Projection)

| Kennzahl | Mai WASDE | **Juni WASDE** | Δ |
|----------|-----------|----------------|---|
| Anbaufläche | 6.30 Mha | **6.30 Mha** | 0 |
| Ertrag | 3.29 t/ha | **3.25 t/ha** | −0.04 |
| **Produktion** | 20.70 MMT | **20.50 MMT** | −0.20 |

### Global (2026/27 Projection)

| Kennzahl | Mai WASDE | **Juni WASDE** | Δ |
|----------|-----------|----------------|---|
| Weizen-Produktion | 819.06 MMT | **820.06 MMT** | +1.00 |
| Weizen-Endbestände | 275.04 MMT | **275.42 MMT** | +0.38 |
| Mais-Produktion | 1,295.38 MMT | **1,300.38 MMT** | +5.00 |
| Mais-Endbestände | 277.54 MMT | **281.22 MMT** | +3.68 |

**Fazit:** Juni-WASDE brachte **keine nennenswerten Änderungen** für EU-Kulturen. Leichte globale Anpassungen: Russland-Weizen +2 MMT, Australien −2 MMT. EU unverändert.

---

## 2. Anchor-Forecasts vs. USDA

### Anchor-Status (alle Bitcoin-verifiziert ✅)

| Anchor | Region | Crop | Yield (t/ha) | Anchored | Status |
|--------|--------|------|-------------|----------|--------|
| DEE0_wheat | Sachsen-Anhalt | Weizen | **7.35** | 2026-05-15 | ✅ Confirmed |
| DE00_wheat | DE national (proxy) | Weizen | **7.36** | 2026-05-15 | ✅ Confirmed |
| FR00_wheat | FR national (proxy) | Weizen | **5.65** | 2026-05-15 | ✅ Confirmed |
| DE00_rapeseed | DE national (proxy) | Raps | **2.63** | 2026-05-15 | ✅ Confirmed |
| market_prices | EU Spot | Preise | Siehe Tabelle | 2026-05-16 | ✅ Confirmed |

### Vergleichstabelle

| Region | Crop | Unser Forecast | USDA EU-Avg | Abweichung | Bewertung |
|--------|------|---------------|-------------|-----------|-----------|
| **DE00** | Wheat | **7.36 t/ha** | 5.76 t/ha (EU) | +27.8% ✅ | DE liegt historisch 25–35% über EU-Schnitt — **plausibel** |
| **FR00** | Wheat | **5.65 t/ha** | 5.76 t/ha (EU) | −1.9% ⚠️ | FR liegt historisch ~20% über EU-Schnitt. 5.65 ist **zu niedrig** (methodisch schwach: nur 8/22 NUTS2) |
| **DEE0** | Wheat | **7.35 t/ha** | ~6.2 t/ha (DE-avg Est.) | +18.5% ✅ | Sachsen-Anhalt typischerweise über DE-Schnitt — **plausibel** |
| **DE00** | Rapeseed | **2.63 t/ha** | 3.25 t/ha (EU) | −19.1% ⚠️ | DE-Raps liegt historisch nahe am EU-Schnitt. 2.63 ist zu niedrig — **methodisch schwach** (Datenfix v5.1d bestätigt Problem) |

### Marktpreise (anchored 2026-05-16)

| Asset | Anchor-Preis | Aktuell (geschätzt) | Tendenz |
|:------|:-----------:|:------------------:|:-------:|
| Weizen | **236 €/t** | ~230–240 €/t | ⚖️ Stabil |
| Mais | **179 €/t** | ~175–185 €/t | ⚖️ Stabil |
| Raps | **470 €/t** | ~460–475 €/t | ⚖️ Stabil |
| Gerste | **190 €/t** | ~185–195 €/t | ⚖️ Stabil |
| Sonnenblumen | **420 €/t** | ~410–425 €/t | ⚖️ Stabil |

*WASDE hatte nur marginale Auswirkungen auf EU-Preise. Kein signifikanter Move nach dem Report.*

---

## 3. Qualitätsbewertung

### ✅ Stärken

1. **DE00 Weizen (7.36 t/ha)**: Liegt im erwarteten Korridor. Das Modell gibt eine realistische Schätzung für DE-National. Kein Widerspruch zu USDA-Daten (können auf EU-Ebene nicht direkt widerlegt werden).
2. **Bitcoin-Verifikation**: Alle 4+1 Anchors sind auf der Bitcoin-Blockchain bestätigt (Blocks 949437, 949443, 949478). Der Zeitstempel ist unanfechtbar.
3. **Timing**: 27 Tage vor WASDE geanchored — das ist der Proof-of-Concept.

### ⚠️ Schwächen

1. **FR00 Weizen (5.65 t/ha)**: Nur 8 der 22 französischen NUTS2-Regionen im Modell. Der USDA EU-Schnitt (5.76 t/ha) passt fast genau — das ist aber Zufall, nicht Validierung. FR liegt historisch bei 7.0–7.5 t/ha.
2. **DE00 Raps (2.63 t/ha)**: Der Datenfix (v5.1d) hat das Problem nur teilweise behoben. Vergleicht man mit dem EU-Schnitt (3.25 t/ha) oder historischen DE-Werten (3.5–4.0 t/ha), liegt der Anchor zu niedrig.
3. **Methodische Lücke**: WASDE gibt keine länderspezifischen Erträge für DE. Der Vergleich läuft immer über die Brücke "EU yield ± historischer Faktor" — keine direkte Validierung möglich.

### 🎯 Lessons Learned

| Issue | Lesson | Action |
|-------|--------|--------|
| FR00 Modellabdeckung | Nur 8/22 NUTS2 = unzureichend | FR Coverage auf ≥18 Regionen ausbauen (V5.5) |
| DE00 Rapsdaten | Eurostat I1110 lieferte Ausreißer | Manuellen Korrekturmechanismus implementieren |
| WASDE-Aggregation | Keine DE-spezifischen Zahlen | Destatis + MARS Crop Bulletin als Brücke nutzen |
| 27-Tage-Fenster | Kein Wetter-Update möglich | Zweiten Anchor Mitte Juni vor Ernte erwägen |

---

## 4. Nächste Validierungsschritte

- [ ] **MARS Crop Bulletin** (Mitte Juni) — NUTS2-Vergleich für DEE0
- [ ] **Destatis Erntemeldung** (Herbst 2026 / Jan 2027) — finales Yield-Delta
- [ ] **Zweiter Anchor** vor der Ernte (Juli) — Wetter-Update
- [ ] **UK + Ukraine Coverage** (V5.0) — nächste WASDE abdecken

---

## 5. Zusammenfassung

> **Der Proof-of-Concept ist gelungen:** 27 Tage vor WASDE wurden 4+1 Ertrags- und Preis-Anchors auf der Bitcoin-Blockchain gesichert. Die Juni-WASDE 2026 brachte keine Überraschungen für EU-Kulturen — alle EU-Schätzungen blieben stabil. Unsere DE-Weizen-Anchor (7.36 t/ha) liegt im realistischen Bereich. Die Schwachstellen FR00 und Raps sind dokumentiert und werden in V5.5 adressiert.

---

*Report generiert am 2026-06-12 um ~06:00 UTC via CropProphEU Cron Job*
*Quelle: USDA WASDE-672 (usda.gov/oce/commodity/wasde/wasde0626v2.pdf)*
