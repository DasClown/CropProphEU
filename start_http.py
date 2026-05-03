#!/usr/bin/env python3
"""Start crop-mcp HTTP server and log to file."""
import sys, os, time

os.chdir("/home/j/crop-mcp")
log = open("/tmp/crop-http.log", "w", buffering=1)
sys.stdout = log
sys.stderr = log

print(f"[{time.strftime('%H:%M:%S')}] Starting crop-mcp HTTP server...")
sys.stdout.flush()

try:
    from crop_mcp.server import run_http
    import asyncio
    asyncio.run(run_http(host="0.0.0.0", port=8080))
except Exception as e:
    import traceback
    print(f"[{time.strftime('%H:%M:%S')}] ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)
