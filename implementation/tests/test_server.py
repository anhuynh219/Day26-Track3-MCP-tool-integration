"""Structured tests for the SQLite Lab MCP server.

Two layers are exercised:

* the :class:`SQLiteAdapter` directly (validation + SQL behaviour), and
* the tools/resources through an in-memory FastMCP ``Client`` (the real
  MCP surface a client would use).

Each test uses its own freshly-seeded temp database, so tests are isolated
and repeatable. ``asyncio_mode = auto`` (see pyproject.toml) lets the async
tests run without extra decorators.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from db import SQLiteAdapter, ValidationError
from init_db import create_database
from mcp_server import create_server


@pytest.fixture()
def adapter(tmp_path: Path) -> SQLiteAdapter:
    db_path = tmp_path / "test.db"
    create_database(db_path)
    return SQLiteAdapter(db_path)


@pytest.fixture()
def client(adapter: SQLiteAdapter) -> Client:
    return Client(create_server(adapter, name="Test Server"))


# ======================================================================
# Adapter-level tests (validation + SQL)
# ======================================================================
class TestAdapterValidation:
    def test_search_unknown_table(self, adapter: SQLiteAdapter):
        with pytest.raises(ValidationError, match="Unknown table"):
            adapter.search("ghosts")

    def test_search_unknown_column(self, adapter: SQLiteAdapter):
        with pytest.raises(ValidationError, match="Unknown column"):
            adapter.search("students", columns=["nope"])

    def test_unsupported_operator(self, adapter: SQLiteAdapter):
        with pytest.raises(ValidationError, match="Unsupported operator"):
            adapter.search(
                "students", filters=[{"column": "score", "op": "between", "value": 1}]
            )

    def test_empty_insert(self, adapter: SQLiteAdapter):
        with pytest.raises(ValidationError, match="non-empty"):
            adapter.insert("students", {})

    def test_bad_aggregate_metric(self, adapter: SQLiteAdapter):
        with pytest.raises(ValidationError, match="Unsupported metric"):
            adapter.aggregate("students", "median", column="score")

    def test_aggregate_requires_column(self, adapter: SQLiteAdapter):
        with pytest.raises(ValidationError, match="requires a numeric"):
            adapter.aggregate("students", "avg")

    def test_in_operator_needs_list(self, adapter: SQLiteAdapter):
        with pytest.raises(ValidationError, match="non-empty list"):
            adapter.search(
                "students", filters=[{"column": "cohort", "op": "in", "value": "A1"}]
            )


class TestAdapterBehaviour:
    def test_search_filter_order_paging(self, adapter: SQLiteAdapter):
        res = adapter.search(
            "students",
            filters={"cohort": "A1"},
            order_by="score",
            descending=True,
            limit=2,
        )
        assert res["count"] == 2
        assert res["has_more"] is True
        assert res["rows"][0]["name"] == "Alice Nguyen"

    def test_limit_is_capped(self, adapter: SQLiteAdapter):
        res = adapter.search("students", limit=10_000)
        assert res["limit"] == adapter.MAX_LIMIT

    def test_insert_returns_row_with_id(self, adapter: SQLiteAdapter):
        res = adapter.insert(
            "students", {"name": "New Kid", "cohort": "C1", "score": 70}
        )
        assert res["inserted"]["name"] == "New Kid"
        assert isinstance(res["inserted"]["id"], int)

    def test_aggregate_group_by(self, adapter: SQLiteAdapter):
        res = adapter.aggregate(
            "students", "avg", column="score", group_by="cohort"
        )
        groups = {r["group_key"] for r in res["rows"]}
        assert {"A1", "A2", "B1"} <= groups

    def test_count_star_no_column(self, adapter: SQLiteAdapter):
        res = adapter.aggregate("students", "count")
        assert res["rows"][0]["value"] == 8

    def test_in_operator(self, adapter: SQLiteAdapter):
        res = adapter.search(
            "students",
            filters=[{"column": "cohort", "op": "in", "value": ["A1", "B1"]}],
        )
        cohorts = {r["cohort"] for r in res["rows"]}
        assert cohorts == {"A1", "B1"}


# ======================================================================
# MCP-surface tests (through the in-memory client)
# ======================================================================
class TestMcpSurface:
    async def test_tools_discoverable(self, client: Client):
        async with client:
            names = {t.name for t in await client.list_tools()}
        assert {"search", "insert", "aggregate"} <= names

    async def test_resources_discoverable(self, client: Client):
        async with client:
            resources = {str(r.uri) for r in await client.list_resources()}
            templates = {t.uriTemplate for t in await client.list_resource_templates()}
        assert "schema://database" in resources
        assert "schema://table/{table_name}" in templates

    async def test_search_via_client(self, client: Client):
        async with client:
            res = await client.call_tool(
                "search", {"table": "students", "filters": {"cohort": "A1"}}
            )
        assert res.data["count"] == 3

    async def test_insert_via_client(self, client: Client):
        async with client:
            res = await client.call_tool(
                "insert",
                {"table": "students", "values": {"name": "Q", "cohort": "Z9", "score": 1}},
            )
        assert res.data["inserted"]["cohort"] == "Z9"

    async def test_full_schema_resource(self, client: Client):
        async with client:
            content = await client.read_resource("schema://database")
        schema = json.loads(content[0].text)
        assert set(schema["tables"]) == {"students", "courses", "enrollments"}

    async def test_table_schema_template(self, client: Client):
        async with client:
            content = await client.read_resource("schema://table/courses")
        schema = json.loads(content[0].text)
        names = [c["name"] for c in schema["columns"]]
        assert "credits" in names

    async def test_invalid_call_raises_tool_error(self, client: Client):
        async with client:
            with pytest.raises(ToolError, match="Unknown table"):
                await client.call_tool("search", {"table": "nope"})
