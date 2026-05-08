# Contributing — CropProphEU 🌾

🎉 Danke, dass du zu **CropProphEU** beitragen willst!  
EU Crop Intelligence für AI Agents — Ertragsprognosen, Wetterdaten, Bodenanalyse und Marktpreise.

## 📋 Inhaltsverzeichnis

- [Verhaltenskodex](#verhaltenskodex)
- [Wie kann ich beitragen?](#wie-kann-ich-beitragen)
- [💬 Discussions](#-discussions)
- [Issues](#issues)
  - [Bug Reports](#bug-reports)
  - [Feature Requests](#feature-requests)
- [Pull Requests](#pull-requests)
  - [Vorbereitung](#vorbereitung)
  - [Branch-Naming](#branch-naming)
  - [Commit-Naming](#commit-naming)
  - [Code-Style](#code-style)
  - [Tests](#tests)
  - [CHANGELOG](#changelog)
- [Entwicklungsumgebung](#entwicklungsumgebung)
- [Release-Prozess](#release-prozess)
- [Datenquellen & Limits](#datenquellen--limits)

---

## Verhaltenskodex

Sei respektvoll, konstruktiv und sachlich. Dieses Projekt lebt von offener Zusammenarbeit.

## Wie kann ich beitragen?

- **🐛 Bugs melden** → Issue aufmachen (Template nutzen)
- **💡 Feature vorschlagen** → Issue aufmachen (Template nutzen)
- **🔧 Code beitragen** → PR stellen (siehe unten)
- **📖 Dokumentation verbessern** → README / Wiki PR
- **💬 An Discussions teilnehmen** — Fragen & Ideen vorab diskutieren
- **⭐ Star geben** — hilft bei Sichtbarkeit!

## 💬 Discussions

Neben Issues haben wir **GitHub Discussions**! Hier kannst du:
- **Fragen stellen** — „Wie prognostiziere ich Weizenerträge für Niedersachsen?"
- **Ideen diskutieren** — bevor du einen Feature Request schreibst
- **Show & Tell** — zeig, was du mit dem Tool gebaut hast (z.B. Portfolio-Optimierung)
- **Regionsdaten vorschlagen** — fehlt ein Land oder eine NUTS2-Region?

👉 https://github.com/DasClown/CropProphEU/discussions

## Issues

### Bug Reports

Nutze das **Bug Report Template**. Wichtig:
- **Region + Kultur** — welche NUTS2-Region, welche Kultur (Weizen, Mais, Raps, etc.)?
- **MCP Client & Version** — Claude Desktop, Cursor, custom?
- **Tool + Parameter** — welches Tool mit welchen Parametern?
- **Logs / Fehlermeldungen** — stdout/stderr, Traceback

### Feature Requests

Nutze das **Feature Request Template**. Wichtig:
- **Problem & Lösung** — nicht nur die Lösung, auch das Problem dahinter
- **Use Case** — Ertragsprognose, Standortanalyse, Marktpreise?
- **Datenquelle** — falls bekannt: Eurostat, NASA POWER, Open-Meteo, Destatis

## Pull Requests

### Vorbereitung

1. Forke das Repository
2. Erstelle einen Feature-Branch
3. Implementiere deine Änderung
4. Füge Tests hinzu (wenn möglich)
5. Stelle den PR gegen `main`

### Branch-Naming

```
fix/fehler-kurzbeschreibung
feat/feature-name
docs/was-wurde-geaendert
chore/aufgabe
```

### Commit-Naming

Conventional Commits:

```
feat: neue Funktion XYZ
fix: yield prediction error behoben
docs: README erweitert
refactor: data layer extrahiert
chore: CI Pipeline aktualisiert
test: Tests für predict_yield
```

### Code-Style

- **Python 3.10+** Typannotationen (Type Hints) — Pflicht
- **Pydantic v2** für Datenmodelle
- **Docstrings** — Google Style oder NumPy Style
- **Max 100 Zeichen pro Zeile**
- Lint mit `ruff` vor dem Commit:
  ```bash
  ruff check .
  ruff format --check .
  ```

### Tests

- Tests liegen in `tests/`
- pytest mit:
  ```bash
  pytest -v
  ```
- Jeder neue Tool-Endpoint braucht mindestens einen Happy-Path-Test

### CHANGELOG

Jeder PR muss einen Eintrag in `CHANGELOG.md` haben:

```markdown
## YYYY-MM-DD

### Added
- ...

### Changed
- ...

### Fixed
- ...
```

## Entwicklungsumgebung

```bash
# Clone
git clone https://github.com/DasClown/CropProphEU.git
cd CropProphEU

# Venv (optional)
python -m venv venv
source venv/bin/activate

# Dev install
pip install -e ".[http]"

# Test
pytest -v
```

## Release-Prozess

1. `CHANGELOG.md` finalisieren
2. Version in `pyproject.toml` aktualisieren
3. Taggen: `git tag v5.X && git push origin v5.X`
4. GitHub Release mit Release Notes erstellen

## Datenquellen & Limits

| Quelle | Rate Limit | Kosten |
|--------|-----------|--------|
| NASA POWER | 10 req/s | 💰 Frei |
| Open-Meteo | ~500 req/min | 💰 Frei |
| Eurostat | 30 req/min | 💰 Frei |
| Destatis | 60 req/min | 💰 Frei |

---

**Noch Fragen?** Schreib ein Issue, starte eine Discussion oder ping @DasClown auf GitHub! 🚀
