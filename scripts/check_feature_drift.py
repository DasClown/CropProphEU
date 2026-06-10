#!/usr/bin/env python3
"""
Feature-Drift Check: Lädt das trainierte Modell (.pkl) und prüft Feature-Importance.
Warnt wenn solar_kwh > 50% der Gesamt-Importance ausmacht (→ Überanpassung/Drift-Signal).

Cron: wöchentlich Mo 05:00 UTC via Hermes Cron 'check-feature-drift-mo'
"""
import json, os, sys, logging
from datetime import datetime

MODEL_PATHS = [
    "/home/j/crop-mcp/europe_yield_model.pkl",
    "/home/j/crop-mcp/europe_yield_model_barley.pkl",
    "/home/j/crop-mcp/europe_yield_model_corn.pkl",
    "/home/j/crop-mcp/europe_yield_model_rapeseed.pkl",
    "/home/j/crop-mcp/europe_yield_model_sunflower.pkl",
]

WARNING_THRESHOLD = 0.50  # solar_kwh > 50% → Warning
LOG_FILE = "/home/j/crop-mcp/build_monitor.log"


def check_feature_drift(model_path, log_file=LOG_FILE):
    """Lade Modell und prüfe Feature-Importance auf Drift."""
    crop_name = "wheat"
    for name in ["barley", "corn", "rapeseed", "sunflower"]:
        if name in model_path:
            crop_name = name
            break

    try:
        import joblib
        import numpy as np
        pkg = joblib.load(model_path)
    except Exception as e:
        msg = f"❌ [{crop_name}] Modell-Load fehlgeschlagen: {e}"
        print(msg)
        logging.warning(msg)
        return {"status": "error", "model": model_path, "error": str(e)}

    model = pkg.get("model")
    feature_names = pkg.get("feature_names", [])
    importances = model.feature_importances_

    if "solar_kwh" not in feature_names:
        msg = f"⚠️ [{crop_name}] 'solar_kwh' nicht in feature_names gefunden"
        print(msg)
        return {"status": "skip", "reason": "solar_kwh not in features"}

    idx = feature_names.index("solar_kwh")
    solar_imp = float(importances[idx])
    total_imp = float(sum(importances))
    solar_ratio = solar_imp / max(total_imp, 1e-10)

    # Top-10 Feature Importances
    top10 = sorted(
        zip(feature_names, importances),
        key=lambda x: -x[1]
    )[:10]

    result = {
        "timestamp": datetime.utcnow().isoformat(),
        "model": model_path,
        "crop": crop_name,
        "solar_kwh_importance": round(solar_imp, 4),
        "solar_kwh_ratio": round(solar_ratio, 4),
        "solar_warning": solar_ratio > WARNING_THRESHOLD,
        "top_features": {n: round(float(v), 4) for n, v in top10},
        "n_features": len(feature_names),
        "n_samples": pkg.get("n_samples", "?"),
        "cv_mae": pkg.get("cv_mae", "?"),
    }

    # Loggen
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )

    if solar_ratio > WARNING_THRESHOLD:
        msg = (f"🚨 DRIFT WARNING [{crop_name}]: solar_kwh = {solar_imp:.4f} "
               f"({solar_ratio*100:.1f}% der total Importance) — Schwellwert {WARNING_THRESHOLD*100:.0f}% überschritten!")
        logging.warning(msg)
        result["alert"] = True
    else:
        msg = (f"✅ [{crop_name}] solar_kwh = {solar_imp:.4f} ({solar_ratio*100:.1f}%) — Normalbereich")
        logging.info(msg)

    print(f"\n📊 Top 10 Features [{crop_name}]:")
    for n, v in top10:
        marker = " ← DRIFT" if n == "solar_kwh" and solar_ratio > WARNING_THRESHOLD else ""
        print(f"  {n:.<30} {v:.4f}{marker}")

    return result


def check_all_models():
    """Prüfe alle existierenden Modell-Dateien."""
    print(f"\n{'='*60}")
    print(f"🔍 FEATURE DRIFT CHECK — {datetime.utcnow().isoformat()}")
    print(f"{'='*60}")

    results = []
    for path in MODEL_PATHS:
        if os.path.exists(path):
            r = check_feature_drift(path)
            results.append(r)
        else:
            print(f"  ℹ️  Nicht gefunden: {path}")

    alerts = [r for r in results if r.get("alert") or r.get("status") == "error"]

    print(f"\n{'='*60}")
    print(f"✅ Drift Check abgeschlossen — {len(results)} Modelle geprüft")
    if alerts:
        print(f"⚠️  {len(alerts)} Alerts ausgelöst")
    print(f"{'='*60}")
    print(f"Log: {LOG_FILE}")

    return results


if __name__ == "__main__":
    check_all_models()
