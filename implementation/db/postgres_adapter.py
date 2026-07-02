"""PostgreSQL implementation of :class:`~db.base.DatabaseAdapter`.

This exists to prove the MCP surface is backend-agnostic: it reuses every
bit of validation and safe-SQL building from the base class and only swaps
in the PostgreSQL dialect (``%s`` placeholders, ``information_schema``
introspection, ``psycopg`` execution).

It is entirely optional. The server selects it only when ``DATABASE_URL``
points at PostgreSQL (``postgres://`` / ``postgresql://``). ``psycopg`` is
imported lazily so the SQLite path never depends on it.
"""

from __future__ import annotations

from typing import Any, Iterable

from .base import DatabaseAdapter
from .errors import ValidationError


class PostgresAdapter(DatabaseAdapter):
    placeholder = "%s"

    def __init__(self, dsn: str, schema: str = "public"):
        self.dsn = dsn
        self.schema = schema

    # ---- connection --------------------------------------------------
    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - env dependent
            raise RuntimeError(
                "PostgreSQL support needs the 'psycopg' package. "
                "Install it with:  uv sync --extra postgres"
            ) from exc
        return psycopg.connect(self.dsn)

    # ---- introspection ----------------------------------------------
    def list_tables(self) -> list[str]:
        sql = (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = %s AND table_type = 'BASE TABLE' "
            "ORDER BY table_name"
        )
        rows = self._raw_all(sql, (self.schema,))
        return [r["table_name"] for r in rows]

    def get_table_schema(self, table: str) -> dict[str, Any]:
        if table not in self.list_tables():
            raise ValidationError(
                f"Unknown table {table!r}. Known tables: {sorted(self.list_tables())}."
            )
        cols = self._raw_all(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s "
            "ORDER BY ordinal_position",
            (self.schema, table),
        )
        pk_rows = self._raw_all(
            "SELECT kcu.column_name FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            " AND tc.table_schema = kcu.table_schema "
            "WHERE tc.constraint_type = 'PRIMARY KEY' "
            "  AND tc.table_schema = %s AND tc.table_name = %s",
            (self.schema, table),
        )
        pk = {r["column_name"] for r in pk_rows}
        columns = [
            {
                "name": c["column_name"],
                "type": c["data_type"],
                "nullable": c["is_nullable"] == "YES",
                "primary_key": c["column_name"] in pk,
                "default": c["column_default"],
            }
            for c in cols
        ]
        return {"table": table, "columns": columns}

    # ---- execution ---------------------------------------------------
    def _raw_all(self, sql: str, params: Iterable[Any]) -> list[dict[str, Any]]:
        from psycopg.rows import dict_row

        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, tuple(params))
                return list(cur.fetchall())

    def _execute(
        self,
        sql: str,
        params: Iterable[Any] = (),
        *,
        fetch: str = "all",
        commit: bool = False,
    ) -> Any:
        from psycopg.rows import dict_row

        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, tuple(params))
                if fetch == "all":
                    result: Any = list(cur.fetchall())
                elif fetch == "one":
                    result = cur.fetchone()
                else:
                    result = None
            if commit:
                conn.commit()
        return result
