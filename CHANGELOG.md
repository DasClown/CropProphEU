# Changelog

## 2026-06-29

### Health Check
- ✅ ALL CHECKS PASSED — 18 crop-mcp tools + 28 drug-pipeline tools, 0 issues
- ✅ Live market prices: Wheat 224 €/t, Corn 169 €/t (both LIVE via Yahoo Finance v8 API)
- ✅ Training data 22-28 days old (normal — Eurostat 2025 ~Nov)
- 📦 Committed + pushed: V4.7 — Direct Yahoo Finance API + WASDE/MARS Bulletin Tools (847 new lines)

### Features
- market_prices.py: Switch from yfinance lib to direct Yahoo Finance v8 API (avoids 429 rate limits)
- +3 new tools: wasde_report, wasde_commodity, mars_bulletin → 21 tools total
- New: WASDE PDF parser (USDA global supply/demand for wheat, corn, rice, soybeans)
- New: MARS Bulletin PDF parser (JRC EU crop yield forecasts)

## 2026-06-13

### Health Check
- Script timed out (120s) due to OOM — only 30 MB RAM available
- Root cause: 12+ gateway Prozesse parallel (je 140–280 MB RSS)
- Fix: 3 nicht-essentielle Gateways beendet + 2 duplizierte drug-pipeline-server
- Permanenter Fix: memory guard (< 100 MB → Abbruch) in health_check.py hinzugefügt
- Bugfix: drug-pipeline search_trials count key (total_count statt count)

### Status Report
- crop-mcp Technik: ✅ 15 tools, server import OK, market prices LIVE (Weizen 284€/t, Mais 213€/t)
- crop-mcp Content: ✅ Daten frisch (6–12 Tage alt), Eurostat 2024 verfügbar
- drug-pipeline: ✅ 28 tools, lookup/search/approvals funktionieren

