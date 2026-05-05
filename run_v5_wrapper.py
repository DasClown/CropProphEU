#!/usr/bin/env python3 -u
"""Wrapper that runs build and logs to file."""
import sys, subprocess

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

log = open("/tmp/build_v5.log", "w", buffering=1)
proc = subprocess.Popen(
    [sys.executable, "-u", "build_v5.py"],
    cwd="/home/j/crop-mcp",
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)

for line in iter(proc.stdout.readline, b""):
    text = line.decode(errors="replace")
    sys.stdout.write(text)
    sys.stdout.flush()
    log.write(text)
    log.flush()

proc.wait()
log.close()
print(f"Exit: {proc.returncode}")
