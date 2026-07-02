# Launch the MCP Inspector against this server (stdio transport).
# Requires Node.js (npx). Opens the Inspector UI in your browser.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:NPM_CONFIG_CACHE = Join-Path $PSScriptRoot ".npm-cache"
npx -y @modelcontextprotocol/inspector uv run python mcp_server.py
