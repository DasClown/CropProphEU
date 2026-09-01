#!/usr/bin/env python3
"""Root-level launcher for the crop-mcp MCP stdio server.

Restores the legacy entry point /home/j/crop-mcp/server.py (referenced by
Hermes mcp_servers configs) after the project was restored from git, where
the server lives at crop_mcp/server.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crop_mcp.server import run_stdio  # noqa: E402

if __name__ == "__main__":
    run_stdio()
