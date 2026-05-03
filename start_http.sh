#!/bin/bash
cd /home/j/crop-mcp
exec python3 -c "
import sys
sys.stdout = open('/tmp/crop-http.log', 'w', buffering=1)
sys.stderr = sys.stdout

print('Starting crop-mcp HTTP server...')
from crop_mcp.server import run_http
import asyncio
asyncio.run(run_http(host='0.0.0.0', port=8080))
" 2>&1
