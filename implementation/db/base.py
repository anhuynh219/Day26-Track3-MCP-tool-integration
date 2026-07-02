"""Abstract database adapter that defines the MCP-facing surface.

The whole point of this class is that the MCP server never talks to a
specific database. It talks to a :class:`DatabaseAdapter`, and both
:class:`~db.sqlite_adapter.SQLiteAdapter` and
:class:`~db.postgres_adapter.PostgresAdapter` implement the same contract.

Design split
------------
* **Shared, DB-agnostic logic lives here**: request validation
  (identifiers, operators, metrics), safe SQL building with bound
  parameters, and the ``search`` / ``insert`` / ``aggregate`` behaviour.
* **DB-specific logic lives in the subclasses**: how to connect, how to
  introspect the schema, how to execute a statement, and the parameter
  placeholder / identifier-quoting dialect.

Because identifiers (table and column names) can never be passed as bound
parameters in SQL, we validate every identifier against the *live* schema
and only ever interpolate names that we have confirmed exist. All user
*values* are passed as bound parameters. No raw string concatenation of
user input is used to build SQL.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable

from .errors import ValidationError


class DatabaseAdapter(ABC):
    """Common interface + shared safe-SQL logic for every backend."""

    # ---- Dialect knobs (overridden by subclasses) --------------------
    #: Bound-parameter placeholder ("?" for SQLite, "%s" for PostgreSQL).
    placeholder: str = "?"

    # ---- Whitelists --------------------------------------------------
    #: Filter operators we accept, mapped to their SQL spelling.
    OPERATOR_SQL: dict[str, str] = {
        "eq": "=",
        "ne": "!=",
        "lt": "<",
        "lte": "<=",
        "gt": ">",
        "gte": ">=",
        "like": "LIKE",
        "in": "IN",
    }
    #: Aggregate metrics we accept.
    SUPPORTED_METRICS: frozenset[str] = frozenset(
        {"count", "avg", "sum", "min", "max"}
    )
    #: Hard cap on the number of rows a single ``search`` may return.
    MAX_LIMIT: int = 200
    DEFAULT_LIMIT: int = 20

    # ================================================================
    # Abstract, backend-specific pieces
    # ================================================================
    @abstractmethod
    def list_tables(self) -> list[str]:
        """Return the user tables (no internal/system tables)."""

    @abstractmethod
    def get_table_schema(self, table: str) -> dict[str, Any]:
        """Return ``{"table", "columns": [{name,type,nullable,primary_key,default}]}``.

        Must raise :class:`~db.errors.ValidationError` for an unknown table.
        """

    @abstractmethod
    def _execute(
        self,
        sql: str,
        params: Iterable[Any] = (),
        *,
        fetch: str = "all",
        commit: bool = False,
    ) -> Any:
        """Run ``sql`` with bound ``params``.

        ``fetch`` is ``"all"`` (list of dict rows), ``"one"`` (single dict
        row or ``None``), or ``"none"`` (return nothing). ``commit`` flushes
        the transaction for writes.
        """

    def _quote_ident(self, name: str) -> str:
        """Quote an already-validated identifier for this dialect.

        Standard SQL double-quoting works for both SQLite and PostgreSQL.
        """
        return '"' + name.replace('"', '""') + '"'

    # ================================================================
    # Shared schema helpers
    # ================================================================
    def get_full_schema(self) -> dict[str, Any]:
        """Snapshot every table's schema."""
        return {
            "tables": {
                table: self.get_table_schema(table) for table in self.list_tables()
            }
        }

    def _column_names(self, table: str) -> list[str]:
        return [col["name"] for col in self.get_table_schema(table)["columns"]]

    # ================================================================
    # Validation (runs BEFORE any SQL is built)
    # ================================================================
    def _validate_table(self, table: str) -> None:
        if not isinstance(table, str) or not table:
            raise ValidationError("Table name must be a non-empty string.")
        tables = self.list_tables()
        if table not in tables:
            raise ValidationError(
                f"Unknown table {table!r}. Known tables: {sorted(tables)}."
            )

    def _validate_columns(self, table: str, columns: Iterable[str]) -> None:
        known = set(self._column_names(table))
        for col in columns:
            if col not in known:
                raise ValidationError(
                    f"Unknown column {col!r} on table {table!r}. "
                    f"Known columns: {sorted(known)}."
                )

    def _build_where(
        self, table: str, filters: Any
    ) -> tuple[str, list[Any]]:
        """Translate ``filters`` into a safe ``WHERE`` clause + bound params.

        Accepted shapes:

        * ``None`` -> no filtering.
        * A ``dict`` -> shorthand equality, e.g. ``{"cohort": "A1"}``.
        * A ``list`` of ``{"column", "op", "value"}`` objects for richer
          comparisons, e.g. ``[{"column": "score", "op": "gte", "value": 80}]``.
        """
        if filters is None:
            return "", []
        # Normalise the shorthand dict form into the list-of-conditions form.
        if isinstance(filters, dict):
            conditions = [
                {"column": col, "op": "eq", "value": val}
                for col, val in filters.items()
            ]
        elif isinstance(filters, (list, tuple)):
            conditions = list(filters)
        else:
            raise ValidationError(
                "filters must be a dict, a list of conditions, or null."
            )

        if not conditions:
            return "", []

        known = set(self._column_names(table))
        clauses: list[str] = []
        params: list[Any] = []
        for cond in conditions:
            if not isinstance(cond, dict) or "column" not in cond:
                raise ValidationError(
                    "Each filter must be an object with at least a 'column' key."
                )
            column = cond["column"]
            op = cond.get("op", "eq")
            value = cond.get("value")
            if column not in known:
                raise ValidationError(
                    f"Unknown column {column!r} on table {table!r}. "
                    f"Known columns: {sorted(known)}."
                )
            if op not in self.OPERATOR_SQL:
                raise ValidationError(
                    f"Unsupported operator {op!r}. "
                    f"Supported: {sorted(self.OPERATOR_SQL)}."
                )
            ident = self._quote_ident(column)
            if op == "in":
                if not isinstance(value, (list, tuple)) or not value:
                    raise ValidationError(
                        f"Operator 'in' on {column!r} requires a non-empty list value."
                    )
                marks = ", ".join(self.placeholder for _ in value)
                clauses.append(f"{ident} IN ({marks})")
                params.extend(value)
            else:
                clauses.append(f"{ident} {self.OPERATOR_SQL[op]} {self.placeholder}")
                params.append(value)
        return " WHERE " + " AND ".join(clauses), params

    # ================================================================
    # Tool operations (shared across all backends)
    # ================================================================
    def search(
        self,
        table: str,
        columns: list[str] | None = None,
        filters: Any = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = False,
    ) -> dict[str, Any]:
        """SELECT rows with optional projection, filtering, ordering, paging."""
        self._validate_table(table)

        # Projection.
        if columns:
            self._validate_columns(table, columns)
            select_list = ", ".join(self._quote_ident(c) for c in columns)
        else:
            select_list = "*"

        # Paging (clamped so a client can never ask for an unbounded result).
        try:
            limit = int(limit)
            offset = int(offset)
        except (TypeError, ValueError):
            raise ValidationError("limit and offset must be integers.")
        if limit < 0 or offset < 0:
            raise ValidationError("limit and offset must be non-negative.")
        limit = min(limit, self.MAX_LIMIT)

        where_sql, params = self._build_where(table, filters)

        order_sql = ""
        if order_by is not None:
            self._validate_columns(table, [order_by])
            direction = "DESC" if descending else "ASC"
            order_sql = f" ORDER BY {self._quote_ident(order_by)} {direction}"

        # Fetch one extra row to compute has_more without a second query.
        fetch_limit = limit + 1
        sql = (
            f"SELECT {select_list} FROM {self._quote_ident(table)}"
            f"{where_sql}{order_sql} LIMIT {self.placeholder} OFFSET {self.placeholder}"
        )
        rows = self._execute(sql, [*params, fetch_limit, offset], fetch="all")

        has_more = len(rows) > limit
        rows = rows[:limit]
        return {
            "table": table,
            "rows": rows,
            "count": len(rows),
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "columns": columns or self._column_names(table),
        }

    def insert(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        """INSERT one row and return the stored row (via ``RETURNING *``)."""
        self._validate_table(table)
        if not isinstance(values, dict) or not values:
            raise ValidationError(
                "insert requires a non-empty 'values' object mapping columns to values."
            )
        self._validate_columns(table, values.keys())

        cols = list(values.keys())
        col_sql = ", ".join(self._quote_ident(c) for c in cols)
        marks = ", ".join(self.placeholder for _ in cols)
        params = [values[c] for c in cols]
        sql = (
            f"INSERT INTO {self._quote_ident(table)} ({col_sql}) "
            f"VALUES ({marks}) RETURNING *"
        )
        row = self._execute(sql, params, fetch="one", commit=True)
        return {"table": table, "inserted": row}

    def aggregate(
        self,
        table: str,
        metric: str,
        column: str | None = None,
        filters: Any = None,
        group_by: str | None = None,
    ) -> dict[str, Any]:
        """Compute count/avg/sum/min/max, optionally grouped."""
        self._validate_table(table)
        metric = (metric or "").lower()
        if metric not in self.SUPPORTED_METRICS:
            raise ValidationError(
                f"Unsupported metric {metric!r}. "
                f"Supported: {sorted(self.SUPPORTED_METRICS)}."
            )

        if metric == "count":
            # COUNT(*) needs no column; COUNT(col) is allowed if given.
            if column is not None:
                self._validate_columns(table, [column])
                metric_sql = f"COUNT({self._quote_ident(column)})"
            else:
                metric_sql = "COUNT(*)"
        else:
            if not column:
                raise ValidationError(
                    f"Metric {metric!r} requires a numeric 'column'."
                )
            self._validate_columns(table, [column])
            metric_sql = f"{metric.upper()}({self._quote_ident(column)})"

        where_sql, params = self._build_where(table, filters)

        group_sql = ""
        select_prefix = ""
        if group_by is not None:
            self._validate_columns(table, [group_by])
            grp = self._quote_ident(group_by)
            select_prefix = f"{grp} AS group_key, "
            group_sql = f" GROUP BY {grp} ORDER BY {grp}"

        sql = (
            f"SELECT {select_prefix}{metric_sql} AS value "
            f"FROM {self._quote_ident(table)}{where_sql}{group_sql}"
        )
        rows = self._execute(sql, params, fetch="all")
        return {
            "table": table,
            "metric": metric,
            "column": column,
            "group_by": group_by,
            "rows": rows,
        }

    # ---- context-manager sugar (optional) ----------------------------
    def close(self) -> None:  # pragma: no cover - overridden if needed
        """Release any held resources. Default is a no-op."""

    def __enter__(self) -> "DatabaseAdapter":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
