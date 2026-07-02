# Submission — Database MCP Server

The full working implementation is in [`implementation/`](implementation/).

## What was built

A FastMCP server over SQLite (with a swappable PostgreSQL backend) exposing:

- **Tools:** `search`, `insert`, `aggregate`
- **Resources:** `schema://database`, `schema://table/{table_name}`
- **Safety:** schema-validated identifiers + bound parameters (no raw SQL)
- **Bonus:** swappable SQLite/PostgreSQL backend, HTTP/SSE bearer-token auth,
  pagination + output caps, and a structured pytest suite.

See [`implementation/README.md`](implementation/README.md) for setup, tool
descriptions, testing, client configuration, and the demo checklist.

## Fastest way to verify

```bash
cd implementation
uv sync --extra dev --extra postgres
uv run python init_db.py
uv run python verify_server.py   # end-to-end checks, exit 0 on success
uv run pytest -q                 # structured test suite
```

## Client

A Claude Code config is at the repository root: [`.mcp.json`](.mcp.json)
(update the absolute path in `--directory` on another machine).
