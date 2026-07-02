# SQLite Lab — Database MCP Server (FastMCP)

A [Model Context Protocol](https://modelcontextprotocol.io) server built
with **FastMCP** that exposes a small SQLite database through three safe,
validated tools and two schema resources.

- **Tools:** `search`, `insert`, `aggregate`
- **Resources:** `schema://database`, `schema://table/{table_name}`
- **Safety:** every identifier is validated against the live schema; every
  value is passed as a bound parameter. No SQL is built from raw input.
- **Backend-agnostic:** the same MCP surface runs over SQLite (default) or
  PostgreSQL, selected by `DATABASE_URL`.
- **Transports:** `stdio` (default) plus optional `http`/`sse` with
  bearer-token authentication.

---

## 1. Requirements

- [uv](https://docs.astral.sh/uv/) (Python package/venv manager). Python
  3.11+ is fetched automatically by uv.
- Optional: **Node.js** (`npx`) to run the MCP Inspector.
- Optional: a running **PostgreSQL** instance to exercise the Postgres
  backend (the SQLite path needs nothing extra).

## 2. Project structure

```text
implementation/
  pyproject.toml        # uv project + deps (fastmcp, psycopg[extra], pytest)
  db/
    __init__.py         # get_adapter() backend factory + exports
    errors.py           # ValidationError / NotFoundError
    base.py             # DatabaseAdapter: shared validation + safe SQL
    sqlite_adapter.py   # SQLite backend (introspection + execution)
    postgres_adapter.py # PostgreSQL backend (same interface)
  init_db.py            # create + seed the demo database (reproducible)
  mcp_server.py         # FastMCP server: tools, resources, transports, auth
  verify_server.py      # repeatable end-to-end verification (exit 0/1)
  tests/test_server.py  # pytest suite (adapter + MCP surface)
  start_inspector.ps1 / .sh
  AGENTS.md
```

Logic is split cleanly: **`db/` knows about databases, `mcp_server.py`
knows about MCP.** The server only ever talks to a `DatabaseAdapter`.

## 3. Quick start

```bash
cd implementation

# 1. Install dependencies into a local venv (add extras for the bonus parts)
uv sync --extra dev --extra postgres

# 2. Create and seed the SQLite database (idempotent -> ./lab.db)
uv run python init_db.py

# 3a. Run the server over stdio (what MCP clients use)
uv run python mcp_server.py

# 3b. Or verify everything end-to-end without a client
uv run python verify_server.py
```

## 4. Data model

A small relational dataset so the tools are easy to demo:

| Table         | Columns                                                    |
| ------------- | ---------------------------------------------------------- |
| `students`    | `id`, `name`, `cohort`, `score`, `created_at`              |
| `courses`     | `id`, `title`, `credits`                                   |
| `enrollments` | `id`, `student_id`, `course_id`, `grade`                   |

Seeded with 8 students across cohorts `A1` / `A2` / `B1`, 4 courses, and
11 enrollments.

## 5. Tools

### `search(table, filters?, columns?, limit=20, offset=0, order_by?, descending=false)`

Read rows with optional filtering, projection, ordering, and pagination.

- **filters** — either shorthand equality `{"cohort": "A1"}` **or** a list
  of conditions `[{"column": "score", "op": "gte", "value": 80}]`.
  Operators: `eq, ne, lt, lte, gt, gte, like, in` (`in` takes a list).
- **columns** — subset of columns to return (default: all).
- **limit / offset** — pagination window; `limit` is capped at **200**.
- Returns `rows` plus metadata: `count`, `limit`, `offset`, `has_more`.

```jsonc
// search all students in cohort A1, top scores first
{ "table": "students", "filters": { "cohort": "A1" },
  "order_by": "score", "descending": true, "limit": 2 }
```

### `insert(table, values)`

Insert one row and return the stored record (via `RETURNING *`).

- **values** — non-empty object mapping columns to values; every column is
  validated. Returns `{ "table", "inserted": { ...row incl. generated id } }`.

```jsonc
{ "table": "students",
  "values": { "name": "Zoe Tran", "cohort": "A1", "score": 91 } }
```

### `aggregate(table, metric, column?, filters?, group_by?)`

Compute `count`, `avg`, `sum`, `min`, or `max`, optionally grouped.

- `count` may omit `column` (counts rows); the others require a numeric
  `column`. `group_by` adds a `group_key` to each result row.

```jsonc
// average score per cohort
{ "table": "students", "metric": "avg", "column": "score",
  "group_by": "cohort" }
```

## 6. Resources

| URI                             | Description                          |
| ------------------------------- | ------------------------------------ |
| `schema://database`             | Full schema (all tables) as JSON.    |
| `schema://table/{table_name}`   | One table's schema as JSON.          |

In Claude Code, reference them as `@sqlite-lab:schema://database` or
`@sqlite-lab:schema://table/students`.

## 7. Safety and validation

Every tool rejects unsafe input **before** any SQL runs:

- unknown table names → `Unknown table '...'`
- unknown column names → `Unknown column '...'`
- unsupported filter operators → `Unsupported operator '...'`
- invalid aggregate metrics / missing column → `Unsupported metric '...'`
- empty inserts → `insert requires a non-empty 'values' object`

Table/column names are only ever interpolated **after** being matched
against the live schema (then quoted); all user values are bound
parameters (`?` for SQLite, `%s` for PostgreSQL).

## 8. Testing and verification

**Repeatable end-to-end check** (spins up an in-memory client against a
freshly-seeded temp DB and checks discovery, valid calls, resource reads,
and clear errors):

```bash
uv run python verify_server.py    # prints a PASS/FAIL report; exit 0 on success
```

**Structured test suite** (adapter-level + MCP-surface via in-memory client):

```bash
uv run pytest -q
```

## 9. MCP Inspector

```bash
# from implementation/
./start_inspector.ps1      # Windows PowerShell
./start_inspector.sh       # macOS / Linux / Git Bash
# or directly:
npx -y @modelcontextprotocol/inspector uv run python mcp_server.py
```

Checklist in the Inspector: the three tools appear with schemas, both
resources appear, a valid call succeeds, and an invalid call (e.g. a
missing table) returns a clear error.

## 10. Client setup — Claude Code

A ready-to-use config lives at the **repository root** in `.mcp.json`:

```json
{
  "mcpServers": {
    "sqlite-lab": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory",
               "d:/Vinuni/Lab/Day26-Track3-MCP-tool-integration/implementation",
               "python", "mcp_server.py"],
      "env": {}
    }
  }
}
```

> On another machine, update the absolute path in `--directory`. Then, in
> the project folder, run `claude` and approve the server, or register it
> explicitly:
>
> ```bash
> claude mcp add sqlite-lab -- uv run --directory /ABS/PATH/implementation python mcp_server.py
> claude mcp list        # should show sqlite-lab: ... - ✓ Connected
> ```

Once connected you can ask, e.g., *"Use sqlite-lab to show the top 2
students by score"* or reference `@sqlite-lab:schema://database`.

<details>
<summary>Other clients (Gemini CLI, Codex)</summary>

**Gemini CLI** (avoid underscores in the alias):

```bash
gemini mcp add sqlite-lab uv "run" "--directory" "/ABS/PATH/implementation" "python" "mcp_server.py" --description "SQLite lab FastMCP server" --timeout 10000
gemini mcp list
```

**Codex** — `~/.codex/config.toml`:

```toml
[mcp_servers.sqlite_lab]
command = "uv"
args = ["run", "--directory", "/ABS/PATH/implementation", "python", "mcp_server.py"]
```

</details>

## 11. Bonus features

- **Swappable backends (SQLite + PostgreSQL behind one interface).** Both
  adapters inherit the *same* `search`/`insert`/`aggregate` from
  `DatabaseAdapter`; only the dialect (placeholder, introspection) differs.
  Select Postgres with `DATABASE_URL=postgresql://user:pw@host:5432/db`.

- **HTTP/SSE transport with bearer-token auth.** Set a token and clients
  must send `Authorization: Bearer <token>`:

  ```bash
  # PowerShell
  $env:MCP_AUTH_TOKEN = "lab-secret-123"
  uv run python mcp_server.py --transport http --port 8077
  ```

  Requests without the token get **401 Unauthorized**; with it they
  connect and can list/call tools. For a one-command, self-contained
  demonstration (starts the server, probes with/without the token, prints
  PASS):

  ```bash
  uv run python demo_http_auth.py
  ```

- **Polish:** pagination (`has_more` + `limit`/`offset`), a hard 200-row
  output cap, and a structured pytest suite.

## 12. Demo checklist (~2 minutes)

1. `uv run python init_db.py` — show the seeded DB.
2. `uv run python verify_server.py` — show all checks PASS.
3. Inspector (or Claude Code): list the 3 tools + 2 resources.
4. Valid calls: search cohort `A1`, insert a student, avg score by cohort.
5. Read `schema://database` and `schema://table/students`.
6. Invalid call: search a missing table → clear error.
7. Bonus: start the HTTP server with a token; show 401 without / success with.
