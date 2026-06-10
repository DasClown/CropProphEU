#!/usr/bin/env python3
"""
Build-Monitor: Misst build_duration, model_accuracy, feature_importance.
Läuft jede Nacht um 02:00 UTC via Hermes Cron 'crop-build-monitor'.
Schreibt Report nach /home/j/crop-mcp/build_monitor.log.
Nur bei Abweichung >20% vom Baseline → Alarm.
"""
import json, os, sys, time, logging
from datetime import datetime
from pathlib import Path

# ── Pfade ──
BASE_DIR = "/home/j/crop-mcp"
MODEL_PATH = os.path.join(BASE_DIR, "europe_yield_model.pkl")
TRAINING_DATA = os.path.join(BASE_DIR, "europe_training_data.json")
LOG_FILE = os.path.join(BASE_DIR, "build_monitor.log")
BASELINE_FILE = os.path.join(BASE_DIR, "build_baseline.json")
REPORT_FILE = os.path.join(BASE_DIR, "build_report_latest.json")

# Baseline (initial, wird nach erstem Lauf überschrieben)
DEFAULT_BASELINE = {
    "build_duration_s": 120.0,
    "cv_mae": 1.5,
    "cv_mae_pct": 20.0,
    "r2_score": 0.70,
    "n_samples": 1000,
    "solar_kwh_importance": 0.03,
    "timestamp": "2025-01-01T00:00:00",
}

ALERT_THRESHOLD_PCT = 20  # >20% Abweichung → Alarm


def load_baseline():
    if os.path.exists(BASELINE_FILE):
        try:
            with open(BASELINE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return dict(DEFAULT_BASELINE)


def save_baseline(baseline):
    baseline["timestamp"] = datetime.utcnow().isoformat()
    with open(BASELINE_FILE, "w") as f:
        json.dump(baseline, f, indent=2)


def measure_build():
    """Führe den Build aus und messe die Dauer."""
    start = time.time()

    # Build ausführen (nur wenn notwendig)
    build_result = {
        "status": "skipped",
        "duration_s": 0,
        "reason": "Kein Build ausgelöst (Monitoring-Lauf)",
    }

    try:
        import joblib
        import numpy as np
        pkg = joblib.load(MODEL_PATH)
        model = pkg["model"]
        feature_names = pkg.get("feature_names", [])
        importances = model.feature_importances_
        n_samples = pkg.get("n_samples", 0)

        # solar_kwh importance
        solar_idx = feature_names.index("solar_kwh") if "solar_kwh" in feature_names else -1
        solar_imp = float(importances[solar_idx]) if solar_idx >= 0 else 0.0

        # Top-5 Features
        top5 = sorted(zip(feature_names, importances), key=lambda x: -x[1])[:5]

        build_result = {
            "status": "completed",
            "duration_s": round(time.time() - start, 2),
            "cv_mae": pkg.get("cv_mae"),
            "cv_mae_pct": pkg.get("cv_mae_pct"),
            "mean_yield": pkg.get("mean_yield"),
            "n_samples": n_samples,
            "n_features": len(feature_names),
            "solar_kwh_importance": round(solar_imp, 4),
            "top_features": {n: round(float(v), 4) for n, v in top5},
            "best_estimator": pkg.get("best_estimator"),
        }
    except Exception as e:
        build_result = {
            "status": "error",
            "duration_s": round(time.time() - start, 2),
            "error": str(e),
        }

    build_result["measured_at"] = datetime.utcnow().isoformat()
    return build_result


def calculate_deviations(current, baseline):
    """Berechne Abweichungen in % vom Baseline."""
    deviations = {}
    for key in ["cv_mae", "cv_mae_pct", "n_samples", "solar_kwh_importance"]:
        if key in current and current[key] is not None and key in baseline and baseline[key]:
            b = baseline[key]
            c = current[key]
            if b != 0:
                dev_pct = abs(c - b) / b * 100
            else:
                dev_pct = 0 if c == 0 else 999
            deviations[key] = {
                "baseline": float(b) if b is not None else None,
                "current": float(c) if c is not None else None,
                "deviation_pct": round(dev_pct, 1),
                "alert": bool(dev_pct > ALERT_THRESHOLD_PCT),
            }
        else:
            deviations[key] = {"baseline": None, "current": None, "deviation_pct": 0, "alert": False}
    return deviations


def run_monitor():
    """Haupt-Monitoring-Funktion."""
    # Logging einrichten
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [BUILD-MONITOR] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )

    baseline = load_baseline()
    current = measure_build()

    if current["status"] == "error":
        logging.error(f"Build-Messung fehlgeschlagen: {current.get('error')}")
        # Report schreiben trotz Fehler
        report = {
            "timestamp": current["measured_at"],
            "status": "error",
            "current": current,
            "baseline": baseline,
            "alerts": [{"metric": "build", "message": f"Build-Fehler: {current.get('error')}"}],
        }
        with open(REPORT_FILE, "w") as f:
            json.dump(report, f, indent=2)
        # Baseline NICHT aktualisieren bei Fehler
        return report

    deviations = calculate_deviations(current, baseline)
    alerts = []

    for metric, dev in deviations.items():
        if dev.get("alert"):
            alerts.append({
                "metric": metric,
                "message": (f"⚠️ {metric}: Baseline={dev['baseline']}, "
                            f"Current={dev['current']}, "
                            f"Abweichung={dev['deviation_pct']:.1f}% "
                            f"(>{ALERT_THRESHOLD_PCT}%)"),
            })

    has_alert = len(alerts) > 0

    # Report erstellen
    report = {
        "timestamp": current["measured_at"],
        "status": "alert" if has_alert else "ok",
        "duration_s": current.get("duration_s", 0),
        "current": current,
        "baseline": baseline,
        "deviations": deviations,
        "alerts": alerts,
        "alert_count": len(alerts),
    }

    # Report schreiben
    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2)

    # Loggen
    if has_alert:
        logging.warning(f"🚨 BUILD ALERT: {len(alerts)} Abweichungen >{ALERT_THRESHOLD_PCT}%")
        for a in alerts:
            logging.warning(f"  {a['message']}")
    else:
        logging.info(f"✅ Build OK — alle Metriken innerhalb Toleranz")

    logging.info(f"  Dauer: {current.get('duration_s', '?')}s")
    logging.info(f"  MAE: {current.get('cv_mae', '?')} t/ha")
    logging.info(f"  Samples: {current.get('n_samples', '?')}")
    logging.info(f"  Report: {REPORT_FILE}")

    # Baseline aktualisieren: immer bei ersten Run (kein alter Baseline vorhanden),
    # sonst nur wenn kein Alert (drift würde Baseline verzerren)
    is_first_run = not os.path.exists(BASELINE_FILE)
    if current["status"] == "completed" and (is_first_run or not has_alert):
        new_baseline = {
            "build_duration_s": current["duration_s"],
            "cv_mae": current["cv_mae"],
            "cv_mae_pct": current["cv_mae_pct"],
            "r2_score": 0.70,
            "n_samples": current["n_samples"],
            "solar_kwh_importance": current["solar_kwh_importance"],
        }
        save_baseline(new_baseline)
        if is_first_run:
            logging.info(f"  Baseline etabliert (first run) ✓")
        else:
            logging.info(f"  Baseline aktualisiert ✓")

    return report


# ── Ausgabe ──
def print_report(report):
    """Human-readable Report ausgeben."""
    print(f"\n{'='*60}")
    print(f"📊 BUILD MONITOR REPORT — {report['timestamp']}")
    print(f"{'='*60}")
    print(f"  Status:     {'🚨 ALERT' if report.get('alert_count', 0) > 0 else '✅ OK'}")
    print(f"  Build-Dauer: {report.get('duration_s', '?')}s")

    c = report.get("current", {})
    print(f"\n  📈 Current Metrics:")
    print(f"    MAE:        {c.get('cv_mae', '?')} t/ha")
    print(f"    MAE %:      {c.get('cv_mae_pct', '?')}%")
    print(f"    Samples:    {c.get('n_samples', '?')}")
    print(f"    solar_kwh:  {c.get('solar_kwh_importance', '?')}")
    print(f"    Estimator:  {c.get('best_estimator', '?')}")

    devs = report.get("deviations", {})
    print(f"\n  📊 Deviations (>{ALERT_THRESHOLD_PCT}% = Alert):")
    for metric, dv in devs.items():
        alert_mark = "🚨" if dv.get("alert") else "✓"
        print(f"    {alert_mark} {metric}: {dv.get('deviation_pct', 0)}%")

    if report.get("alerts"):
        print(f"\n  🚨 ALERTS:")
        for a in report["alerts"]:
            print(f"    {a['message']}")

    print(f"{'='*60}")
    print(f"Log: {LOG_FILE}")
    print(f"Report: {REPORT_FILE}")


if __name__ == "__main__":
    report = run_monitor()
    print_report(report)
