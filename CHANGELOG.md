# Changelog

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

