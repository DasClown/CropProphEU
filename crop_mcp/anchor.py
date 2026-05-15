#!/usr/bin/env python3
"""
OpenTimestamps-based Forecast Anchoring — V5.4f
=================================================
Proof-of-Forecast via OpenTimestamps (Bitcoin-anchored).
Zero gas costs, zero keys, zero wallet setup.

Usage:
    from crop_mcp.anchor import anchor_forecast, verify_anchor
    
    result = anchor_forecast({
        "region": "DEE0",
        "crop": "wheat",
        "predicted_yield_t_ha": 7.35,
        "p10": 6.50,
        "p90": 8.20,
        "timestamp": "2026-05-15T12:00:00",
        "model_version": "V5.4",
    })
    print(f"Anchored! Tx: {result['ots_hash']}")
"""

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone

ANCHOR_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".anchors")
OTS_BIN = "ots"

def _ensure_dir():
    """Create .anchors/ directory if it doesn't exist."""
    os.makedirs(ANCHOR_DIR, exist_ok=True)

def _extract_forecast_data(forecast_output: dict) -> dict:
    """Extract the core forecast data to be anchored (excludes metadata)."""
    # Normalize: remove non-deterministic fields
    core = {
        "region": forecast_output.get("region", forecast_output.get("region_code", "")),
        "crop": forecast_output.get("crop", ""),
        "predicted_yield_t_ha": forecast_output.get("predicted_yield_t_ha", 
                    forecast_output.get("yield_t_ha", 0)),
        "p10": forecast_output.get("p10", 0),
        "p90": forecast_output.get("p90", 0),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_version": forecast_output.get("model_version", "V5.4"),
        "tool": "environmental_risk" if "ers_score" in forecast_output else "europe_yield_forecast",
    }
    # Add ERS-specific fields
    if "ers_score" in forecast_output:
        core["ers_score"] = forecast_output["ers_score"]
        core["ers_level"] = forecast_output["ers_level"]
    return core

def compute_hash(data: dict) -> str:
    """SHA256 hash of normalized JSON (sorted keys for reproducibility)."""
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2)
    return hashlib.sha256(raw.encode()).hexdigest()

def anchor_forecast(forecast_output: dict | None = None, **kwargs) -> dict:
    """
    Anchor a forecast output via OpenTimestamps.

    Accepts either a dict (forecast_output) or individual keyword arguments
    (region, crop, predicted_yield_t_ha, p10, p90, model_version, label).

    Steps:
    1. Extract core forecast data
    2. Compute SHA256 hash
    3. Write hash to temp file
    4. Submit to OTS calendar (batched -> Bitcoin blockchain)
    5. Save .ots proof file locally
    6. Return anchor info

    Returns dict with 'ots_hash', 'ots_file', 'timestamp', 'explorer_url'.
    """
    _ensure_dir()

    # If kwargs provided, build dict from them
    if forecast_output is None and kwargs:
        forecast_output = kwargs
    core_data = _extract_forecast_data(forecast_output)
    forecast_hash = compute_hash(core_data)
    
    # 2. Write hash to a temp file for OTS
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    region = core_data.get("region", "unknown")
    crop = core_data.get("crop", "unknown")
    hash_file = os.path.join(ANCHOR_DIR, f"{region}_{crop}_{ts}.txt")
    ots_file = hash_file + ".ots"
    
    with open(hash_file, "w") as f:
        f.write(forecast_hash + "\n")
    
    # 3. Submit to OTS calendar
    try:
        result = subprocess.run(
            [OTS_BIN, "stamp", hash_file],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            raise RuntimeError(f"OTS stamp failed: {result.stderr[:200]}")
        
        # Verify .ots file was created
        if not os.path.exists(ots_file):
            # Try to find it - ots sometimes appends .ots to the original
            ots_candidate = hash_file + ".ots"
            if os.path.exists(ots_candidate):
                ots_file = ots_candidate
            else:
                # Check if it created a file without .ots extension
                for f in os.listdir(ANCHOR_DIR):
                    if f.endswith(".ots") and region in f and crop in f:
                        ots_file = os.path.join(ANCHOR_DIR, f)
                        break
                else:
                    raise RuntimeError(f"OTS did not create .ots file (checked in {ANCHOR_DIR})")
        
        # 4. Verify the stamp
        verify_result = subprocess.run(
            [OTS_BIN, "verify", ots_file],
            capture_output=True, text=True, timeout=30
        )
        verified = "Success" in verify_result.stdout or "Pending" in verify_result.stdout
        
    except FileNotFoundError:
        # OTS CLI not installed — fall back to hash-only mode
        return {
            "status": "warning",
            "message": "OpenTimestamps CLI not installed. Install with: pip install opentimestamps-client",
            "ots_hash": forecast_hash,
            "ots_file": None,
            "timestamp": core_data["timestamp"],
            "verified": False,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"OTS anchoring failed: {str(e)[:200]}",
            "ots_hash": forecast_hash,
            "timestamp": core_data["timestamp"],
        }
    
    # 5. Return result
    result_data = {
        "status": "anchored",
        "message": "Forecast hash submitted to OpenTimestamps. Pending Bitcoin confirmation (~1-24h).",
        "ots_hash": forecast_hash,
        "ots_file": ots_file,
        "timestamp": core_data["timestamp"],
        "chain": "bitcoin (via OpenTimestamps)",
        "verification": 'ots verify "' + ots_file + '"',
        "verified": "Pending" in verify_result.stdout if verified else False,
        "anchor_data": core_data,
        "explorer_url": "https://opentimestamps.org/",
    }
    
    # 6. Save anchor metadata
    meta_file = ots_file.replace(".ots", ".json")
    with open(meta_file, "w") as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)
    
    return result_data

def verify_anchor(ots_path: str, original_data: dict | None = None) -> dict:
    """
    Verify a previously anchored forecast.
    
    If original_data is provided, also checks that the hash matches.
    """
    if not os.path.exists(ots_path):
        return {"status": "error", "message": f"OTS file not found: {ots_path}"}
    
    try:
        result = subprocess.run(
            [OTS_BIN, "verify", ots_path],
            capture_output=True, text=True, timeout=30
        )
        
        if original_data:
            core_data = _extract_forecast_data(original_data)
            forecast_hash = compute_hash(core_data)
            
            # Check hash in .ots file matches
            with open(ots_path.replace(".ots", ".txt"), "r") as f:
                stored_hash = f.read().strip()
            hash_match = stored_hash == forecast_hash
        else:
            forecast_hash = None
            hash_match = None
        
        return {
            "status": "verified",
            "ots_verify_output": result.stdout + result.stderr,
            "hash_match": hash_match,
            "forecast_hash": forecast_hash,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}

def list_anchors() -> list[dict]:
    """List all anchored forecasts stored locally."""
    _ensure_dir()
    anchors = []
    for f in sorted(os.listdir(ANCHOR_DIR), reverse=True):
        if f.endswith(".json") and not f.endswith("_meta.json"):
            path = os.path.join(ANCHOR_DIR, f)
            try:
                with open(path) as fh:
                    anchors.append(json.load(fh))
            except Exception:
                anchors.append({"file": f, "error": "parse_failed"})
    return anchors

if __name__ == "__main__":
    # Selftest
    test_data = {
        "region": "DEE0",
        "crop": "wheat",
        "predicted_yield_t_ha": 7.35,
        "p10": 6.50,
        "p90": 8.20,
        "model_version": "V5.4",
    }
    print("Test anchoring...")
    r = anchor_forecast(test_data)
    print(json.dumps(r, indent=2))
