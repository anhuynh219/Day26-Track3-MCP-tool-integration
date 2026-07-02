"""FastMCP server exposing a SQLite database through three tools.

Tools
-----
* ``search``    - read rows with filters, projection, ordering, paging.
* ``insert``    - add one row and return the stored record.
* ``aggregate`` - compute count / avg / sum / min / max, optionally grouped.

Resources
---------
* ``schema://database``            - the full database schema as JSON.
* ``schema://table/{table_name}``  - one table's schema as JSON.

The server never builds SQL from raw user input: every identifier is
validated against the live schema and every value is bound as a parameter
(see :mod:`db.base`). Backend selection (SQLite vs PostgreSQL) is handled by
:func:`db.get_adapter`, so the same MCP surface works over either database.

Run it
------
    uv run python mcp_server.py                      # stdio (default)
    uv run python mcp_server.py --transport http     # HTTP on :8000
    MCP_AUTH_TOKEN=secret uv run python mcp_server.py --transport http   # + bearer auth
"""

from __future__ import annotations

import argparse
import json
import os

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from db import DatabaseAdapter, ValidationError, get_adapter

INSTRUCTIONS = """\
This server exposes a small relational database (students, courses,
enrollments) through safe, validated tools.

Use `search` to read rows, `insert` to add a row, and `aggregate` for
count/avg/sum/min/max. Read `schema://database` for the whole schema or
`schema://table/{table_name}` for one table before constructing filters,
so you use real column names. Unknown tables/columns, unsupported
operators, and empty inserts are rejected with clear errors.
"""


def create_server(adapter: DatabaseAdapter, name: str = "SQLite Lab MCP Server") -> FastMCP:
    """Build a FastMCP server bound to ``adapter``.

    Kept as a factory so tests can inject an adapter pointed at a temporary
    database, while the module-level ``mcp`` uses the configured backend.
    """
    mcp = FastMCP(name, instructions=INSTRUCTIONS)

    # -- helper: turn validation problems into clear client-facing errors --
    def _guard(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValidationError as exc:
            raise ToolError(str(exc)) from exc

    # ================================================================
    # Tools
    # ================================================================
    @mcp.tool
    def search(
        table: str,
        filters: dict | list | None = None,
        columns: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = False,
    ) -> dict:
        """Read rows from a table with optional filtering, projection, ordering and paging.

        Parameters
        ----------
        table:
            Name of the table to read (must exist).
        filters:
            Either a shorthand equality object like ``{"cohort": "A1"}`` or a
            list of conditions like
            ``[{"column": "score", "op": "gte", "value": 80}]``.
            Supported operators: eq, ne, lt, lte, gt, gte, like, in.
        columns:
            Optional list of columns to return. Defaults to all columns.
        limit / offset:
            Pagination window. ``limit`` is capped at 200.
        order_by / descending:
            Optional column to sort by and sort direction.

        Returns a payload with ``rows`` plus paging metadata
        (``count``, ``limit``, ``offset``, ``has_more``).
        """
        return _guard(
            adapter.search,
            table,
            columns=columns,
            filters=filters,
            limit=limit,
            offset=offset,
            order_by=order_by,
            descending=descending,
        )

    @mcp.tool
    def insert(table: str, values: dict) -> dict:
        """Insert a single row and return the stored record.

        Parameters
        ----------
        table:
            Target table (must exist).
        values:
            Non-empty object mapping column names to values. Every column is
            validated against the table schema. Values are bound as
            parameters, never concatenated into SQL.

        Returns ``{"table": ..., "inserted": {<full stored row incl. generated id>}}``.
        """
        return _guard(adapter.insert, table, values)

    @mcp.tool
    def aggregate(
        table: str,
        metric: str,
        column: str | None = None,
        filters: dict | list | None = None,
        group_by: str | None = None,
    ) -> dict:
        """Compute an aggregate metric over a table.

        Parameters
        ----------
        table:
            Table to aggregate over.
        metric:
            One of ``count``, ``avg``, ``sum``, ``min``, ``max``.
            ``count`` may omit ``column`` (counts rows); the others require a
            numeric ``column``.
        column:
            Column to aggregate (required for avg/sum/min/max).
        filters:
            Same shape as ``search`` filters.
        group_by:
            Optional column to group by; each result row then carries a
            ``group_key``.

        Returns ``{"metric": ..., "rows": [{"value": ...}, ...]}``.
        """
        return _guard(
            adapter.aggregate,
            table,
            metric,
            column=column,
            filters=filters,
            group_by=group_by,
        )

    # ================================================================
    # Resources
    # ================================================================
    @mcp.resource("schema://database", mime_type="application/json")
    def database_schema() -> str:
        """The full database schema (all tables and their columns) as JSON."""
        return json.dumps(adapter.get_full_schema(), indent=2, default=str)

    @mcp.resource("schema://table/{table_name}", mime_type="application/json")
    def table_schema(table_name: str) -> str:
        """The schema of a single table as JSON.

        Raises a clear error if ``table_name`` does not exist.
        """
        try:
            schema = adapter.get_table_schema(table_name)
        except ValidationError as exc:
            raise ToolError(str(exc)) from exc
        return json.dumps(schema, indent=2, default=str)

    return mcp


# Module-level server used by stdio, the MCP Inspector, and clients.
adapter = get_adapter()
mcp = create_server(adapter)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SQLite Lab MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default=os.environ.get("MCP_TRANSPORT", "stdio"),
        help="Transport to run (default: stdio).",
    )
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("MCP_PORT", "8000"))
    )
    parser.add_argument("--path", default=os.environ.get("MCP_PATH", "/mcp"))
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.transport in ("http", "sse"):
        # Bonus: optional bearer-token auth for network transports. When
        # MCP_AUTH_TOKEN is set, clients must send `Authorization: Bearer <token>`.
        token = os.environ.get("MCP_AUTH_TOKEN")
        if token:
            from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

            mcp.auth = StaticTokenVerifier(
                {token: {"client_id": "sqlite-lab", "scopes": []}}
            )
            print(f"[auth] Bearer token required on {args.transport} transport.")
        else:
            print(
                "[auth] No MCP_AUTH_TOKEN set - running "
                f"{args.transport} transport without authentication."
            )
        mcp.run(transport=args.transport, host=args.host, port=args.port, path=args.path)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
