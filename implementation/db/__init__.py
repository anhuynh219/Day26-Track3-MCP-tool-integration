"""Database layer for the SQLite Lab MCP server.

Public surface:

* :class:`DatabaseAdapter` - the backend-agnostic contract.
* :class:`SQLiteAdapter` / :class:`PostgresAdapter` - concrete backends.
* :func:`get_adapter` - pick a backend from configuration.
* :class:`ValidationError` / :class:`NotFoundError` - typed errors.
"""

from __future__ import annotations

import os
from pathlib import Path

from .base import DatabaseAdapter
from .errors import DatabaseError, NotFoundError, ValidationError
from .sqlite_adapter import SQLiteAdapter

#: Default SQLite database file, kept next to the implementation package.
DEFAULT_SQLITE_PATH = Path(__file__).resolve().parent.parent / "lab.db"


def get_adapter(database_url: str | None = None) -> DatabaseAdapter:
    """Return the adapter selected by configuration.

    Selection order:

    1. Explicit ``database_url`` argument.
    2. ``DATABASE_URL`` environment variable.
    3. Fallback to the bundled SQLite file (:data:`DEFAULT_SQLITE_PATH`).

    A ``postgres://`` / ``postgresql://`` URL selects
    :class:`PostgresAdapter`; anything else is treated as a SQLite path
    (``sqlite:///path`` or a bare filesystem path).
    """
    url = database_url or os.environ.get("DATABASE_URL")

    if url and url.startswith(("postgres://", "postgresql://")):
        from .postgres_adapter import PostgresAdapter

        return PostgresAdapter(url)

    if url and url.startswith("sqlite:///"):
        return SQLiteAdapter(url[len("sqlite:///") :])

    if url:
        return SQLiteAdapter(url)

    return SQLiteAdapter(DEFAULT_SQLITE_PATH)


__all__ = [
    "DatabaseAdapter",
    "SQLiteAdapter",
    "get_adapter",
    "DEFAULT_SQLITE_PATH",
    "DatabaseError",
    "ValidationError",
    "NotFoundError",
]
