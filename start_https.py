#!/usr/bin/env python3
"""Start crop-mcp HTTPS server for Smithery scanning."""
import sys, os, time

os.chdir("/home/j/crop-mcp")
log = open("/tmp/crop-https.log", "w", buffering=1)
sys.stdout = log
sys.stderr = log

print(f"[{time.strftime('%H:%M:%S')}] Starting crop-mcp HTTPS server...")
sys.stdout.flush()

try:
    from crop_mcp.server import run_http
    import asyncio, uvicorn
    
    # Override run_http to add SSL
    from crop_mcp.server import server
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    from starlette.responses import JSONResponse
    from crop_mcp.server import TOOLS
    
    sse = SseServerTransport("/messages/")
    
    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            read_stream, write_stream = streams
            await server.run(read_stream, write_stream, server.create_initialization_options())
    
    async def handle_root(request):
        return JSONResponse({
            "server": "crop-mcp",
            "version": "4.6.0",
            "description": "EU Crop Intelligence MCP Server",
            "tools": list(TOOLS.keys()),
        })
    
    async def handle_server_card(request):
        tools_list = []
        for name, meta in TOOLS.items():
            tools_list.append({
                "name": name,
                "description": meta["description"],
                "inputSchema": meta["input_schema"],
            })
        return JSONResponse({
            "serverInfo": {"name": "crop-mcp", "version": "4.6.0"},
            "tools": tools_list,
            "resources": [],
            "prompts": [],
        })
    
    app = Starlette(routes=[
        Route("/", endpoint=handle_root),
        Route("/.well-known/mcp/server-card.json", endpoint=handle_server_card),
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ])
    
    config = uvicorn.Config(
        app, host="0.0.0.0", port=8443,
        ssl_certfile="/tmp/crop-cert.pem",
        ssl_keyfile="/tmp/crop-key.pem",
    )
    srv = uvicorn.Server(config)
    print(f"[{time.strftime('%H:%M:%S')}] crop-mcp HTTPS on https://0.0.0.0:8443/sse")
    sys.stdout.flush()
    asyncio.run(srv.serve())
except Exception as e:
    import traceback
    print(f"[{time.strftime('%H:%M:%S')}] ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)
