"""SQLite implementation of :class:`~db.base.DatabaseAdapter`.

Only the backend-specific pieces live here: connecting, schema
introspection via ``PRAGMA``, and statement execution. Everything about
*what* a safe query looks like is inherited from the base class.

A fresh connection is opened per call. That keeps the adapter trivially
thread-safe (FastMCP runs tool functions in worker threads), which matters
because a single ``sqlite3`` connection may not be shared across threads.
For a local file database this overhead is negligible.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .base import DatabaseAdapter
from .errors import ValidationError


class SQLiteAdapter(DatabaseAdapter):
    placeholder = "?"

    def __init__(self, path: str | Path):
        self.path = str(path)

    # ---- connection --------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ---- introspection ----------------------------------------------
    def list_tables(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            ).fetchall()
        return [r["name"] for r in rows]

    def get_table_schema(self, table: str) -> dict[str, Any]:
        if table not in self.list_tables():
            raise ValidationError(
                f"Unknown table {table!r}. Known tables: {sorted(self.list_tables())}."
            )
        with self._connect() as conn:
            # PRAGMA does not accept bound parameters; the table name is
            # already confirmed to be a real table above, so it is safe.
            info = conn.execute(
                f"PRAGMA table_info({self._quote_ident(table)})"
            ).fetchall()
        columns = [
            {
                "name": row["name"],
                "type": row["type"] or "",
                "nullable": not bool(row["notnull"]),
                "primary_key": bool(row["pk"]),
                "default": row["dflt_value"],
            }
            for row in info
        ]
        return {"table": table, "columns": columns}

    # ---- execution ---------------------------------------------------
    def _execute(
        self,
        sql: str,
        params: Iterable[Any] = (),
        *,
        fetch: str = "all",
        commit: bool = False,
    ) -> Any:
        with self._connect() as conn:
            cur = conn.execute(sql, tuple(params))
            if fetch == "all":
                result: Any = [dict(row) for row in cur.fetchall()]
            elif fetch == "one":
                row = cur.fetchone()
                result = dict(row) if row is not None else None
            else:  # "none"
                result = None
            if commit:
                conn.commit()
        return result
