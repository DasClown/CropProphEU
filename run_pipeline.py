#!/usr/bin/env python3
"""Build + Train pipeline for all 3 crops with V4.7 soil features."""
import subprocess, sys, time, os

CROPS = ["wheat", "corn", "barley"]
BASE = "/home/j/crop-mcp"

for crop in CROPS:
    print(f"\n{'='*60}")
    print(f"🌾 {crop.upper()}: Build + Train")
    print(f"{'='*60}")
    
    # Clean old checkpoints
    for f in os.listdir(BASE):
        if f.startswith(f"europe_checkpoint_{crop}") or (crop == "wheat" and f == "europe_checkpoint.json"):
            os.remove(os.path.join(BASE, f))
            print(f"  Removed old checkpoint: {f}")
    
    # Step 1: Build training data
    print(f"\n  📦 Building training data for {crop}...")
    t0 = time.time()
    r = subprocess.run(
        ["python3", "-u", "build_europe.py", "--crop", crop],
        cwd=BASE, capture_output=True, text=True, timeout=900
    )
    elapsed = time.time() - t0
    print(f"  ⏱  Build: {elapsed:.0f}s")
    
    # Show last relevant lines
    out_lines = r.stdout.strip().split("\n")
    for line in out_lines[-10:]:
        print(f"    {line}")
    if r.returncode != 0:
        err = r.stderr.strip().split("\n")
        for line in err[-5:]:
            print(f"    ❌ {line}")
        print(f"  ❌ BUILD FAILED for {crop}")
        sys.exit(1)
    
    # Step 2: Train model
    print(f"\n  🧠 Training model for {crop}...")
    t0 = time.time()
    r = subprocess.run(
        ["python3", "-u", "train_europe_fast.py", "--crop", crop],
        cwd=BASE, capture_output=True, text=True, timeout=300
    )
    elapsed = time.time() - t0
    print(f"  ⏱  Train: {elapsed:.0f}s")
    
    out_lines = r.stdout.strip().split("\n")
    for line in out_lines[-12:]:
        print(f"    {line}")
    if r.returncode != 0:
        err = r.stderr.strip().split("\n")
        for line in err[-5:]:
            print(f"    ❌ {line}")
        print(f"  ❌ TRAIN FAILED for {crop}")
        sys.exit(1)

print(f"\n{'='*60}")
print("✅ ALL 3 CROPS BUILT AND TRAINED")
print(f"{'='*60}")
