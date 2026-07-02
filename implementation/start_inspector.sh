#!/usr/bin/env bash
# Launch the MCP Inspector against this server (stdio transport).
# Requires Node.js (npx). Opens the Inspector UI in your browser.
set -euo pipefail
cd "$(dirname "$0")"
export NPM_CONFIG_CACHE="$PWD/.npm-cache"
npx -y @modelcontextprotocol/inspector uv run python mcp_server.py
