#!/usr/bin/env python3
"""crop-mcp CLI — Start the MCP server or HTTP server.

Usage:
  crop-mcp                # Start stdio MCP server
  crop-mcp --http         # Start HTTP/SSE server on port 8080
  crop-mcp --http --port 8080 --host 0.0.0.0
  crop-mcp --list-tools   # List available tools
  crop-mcp --version      # Show version
"""

import sys, json

def main():
    args = sys.argv[1:]
    
    if "--version" in args:
        from crop_mcp import __version__
        print(f"crop-mcp v{__version__}")
        return
    
    if "--list-tools" in args:
        from crop_mcp.server import TOOLS
        for name, meta in sorted(TOOLS.items()):
            desc = meta["description"][:80] + "..." if len(meta["description"]) > 80 else meta["description"]
            print(f"  {name:25s} {desc}")
        return
    
    if "--http" in args or "--sse" in args:
        host = "0.0.0.0"
        port = 8080
        for i, a in enumerate(args):
            if a == "--host" and i + 1 < len(args):
                host = args[i + 1]
            if a == "--port" and i + 1 < len(args):
                port = int(args[i + 1])
        try:
            from mcp.server.sse import SseServerTransport
            from starlette.applications import Starlette
            from starlette.routing import Mount, Route
            import uvicorn
        except ImportError:
            print("HTTP mode requires: pip install mcp[httpx] uvicorn")
            sys.exit(1)
        
        from crop_mcp.server import mcp_server
        
        sse = SseServerTransport("/messages/")
        
        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send,
                mcp_server.create_initialization_options()
            ) as session:
                await mcp_server.run(session, request.app)
        
        app = Starlette(
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ],
        )
        print(f"🌾 crop-mcp HTTP server listening on http://{host}:{port}/sse")
        uvicorn.run(app, host=host, port=port)
        return
    
    # Default: stdio MCP server
    from crop_mcp.server import run_stdio
    run_stdio()

if __name__ == "__main__":
    main()
