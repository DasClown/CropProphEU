#!/usr/bin/env python3
"""Sequential build + train for all 3 crops. Runs one at a time, saves checkpoints."""
import subprocess, sys, time, os, json

BASE = "/home/j/crop-mcp"

def run_step(label, cmd, timeout=3600):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    sys.stdout.flush()
    t0 = time.time()
    r = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True, timeout=timeout)
    elapsed = time.time() - t0
    # Print last 15 lines of stdout
    lines = r.stdout.strip().split("\n")
    for line in lines[-20:]:
        print(f"  {line}")
    if r.returncode != 0:
        err = r.stderr.strip().split("\n")
        for line in err[-5:]:
            print(f"  ❌ {line}")
        print(f"  ❌ FAILED ({elapsed:.0f}s)")
        sys.exit(1)
    print(f"  ✅ Done ({elapsed:.0f}s)")
    sys.stdout.flush()
    return r

for crop in ["wheat", "corn", "barley", "rapeseed", "sunflower"]:
    # Clean checkpoint
    cp_file = "europe_checkpoint.json" if crop == "wheat" else f"europe_checkpoint_{crop}.json"
    cp_path = os.path.join(BASE, cp_file)
    if os.path.exists(cp_path):
        os.remove(cp_path)
        print(f"  Removed {cp_file}")
    
    # Build
    run_step(f"🌾 Build {crop}", ["python3", "-u", "build_europe.py", "--crop", crop])
    
    # Train
    run_step(f"🧠 Train {crop}", ["python3", "-u", "train_europe_fast.py", "--crop", crop])

print(f"\n{'='*60}")
print("✅ ALL DONE - ALL 3 CROPS")
print(f"{'='*60}")
