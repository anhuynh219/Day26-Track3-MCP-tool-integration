"""Typed errors for the database layer.

These are raised by the adapters *before* any SQL is executed whenever a
request cannot be run safely (unknown table, unknown column, unsupported
operator, bad aggregate, empty insert, ...). The MCP server layer catches
them and re-raises as ``ToolError`` so clients receive a clear message.
"""


class DatabaseError(Exception):
    """Base class for every error raised by the database layer."""


class ValidationError(DatabaseError):
    """Raised when a request cannot be safely executed.

    Examples: unknown table/column, unsupported filter operator,
    invalid aggregate metric, empty insert payload.
    """


class NotFoundError(DatabaseError):
    """Raised when a requested object (e.g. a table) does not exist."""
