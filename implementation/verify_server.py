"""Repeatable end-to-end verification of the MCP server.

Connects an in-memory FastMCP client to a server backed by a throwaway,
freshly-seeded SQLite database and checks the full rubric story:

1. the server starts and the three tools are discoverable
2. the schema resource and per-table template are discoverable
3. valid tool calls return useful results
4. reading the schema resources works
5. invalid tool calls fail with clear errors

Run it any time:

    uv run python verify_server.py

Exit code is 0 only if every check passes, so it doubles as a smoke test.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path

# The negative tests below deliberately trigger tool errors. FastMCP logs
# those at ERROR level with full tracebacks, which would bury the readable
# report, so we quiet its loggers here (the errors are the expected result).
os.environ.setdefault("FASTMCP_LOG_LEVEL", "CRITICAL")
for _name in ("FastMCP", "fastmcp", "mcp"):
    logging.getLogger(_name).setLevel(logging.CRITICAL)

from fastmcp import Client
from fastmcp.exceptions import ToolError

from db import SQLiteAdapter
from init_db import create_database
from mcp_server import create_server

PASS = "PASS"
FAIL = "FAIL"


class Report:
    """Tiny pass/fail accumulator with pretty printing."""

    def __init__(self) -> None:
        self.results: list[tuple[bool, str, str]] = []

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        self.results.append((ok, label, detail))
        marker = PASS if ok else FAIL
        line = f"  [{marker}] {label}"
        if detail:
            line += f"\n         -> {detail}"
        print(line)

    @property
    def ok(self) -> bool:
        return all(ok for ok, _, _ in self.results)

    def summary(self) -> str:
        passed = sum(1 for ok, _, _ in self.results if ok)
        return f"{passed}/{len(self.results)} checks passed"


def section(title: str) -> None:
    print(f"\n=== {title} ===")


async def expect_error(client: Client, tool: str, args: dict) -> str:
    """Call a tool expecting failure; return the error message (or '')."""
    try:
        await client.call_tool(tool, args)
    except ToolError as exc:
        return str(exc)
    except Exception as exc:  # pragma: no cover - unexpected client error type
        return f"{type(exc).__name__}: {exc}"
    return ""


async def run() -> bool:
    report = Report()

    # Fresh, reproducible database in a temp dir so inserts don't accumulate.
    tmpdir = tempfile.mkdtemp(prefix="mcp-verify-")
    db_path = Path(tmpdir) / "verify.db"
    create_database(db_path)
    server = create_server(SQLiteAdapter(db_path), name="Verify Server")

    async with Client(server) as client:
        section("1. Tool discovery")
        tools = {t.name for t in await client.list_tools()}
        for name in ("search", "insert", "aggregate"):
            report.check(name in tools, f"tool '{name}' is discoverable")

        section("2. Resource discovery")
        resources = {str(r.uri) for r in await client.list_resources()}
        templates = {t.uriTemplate for t in await client.list_resource_templates()}
        report.check(
            "schema://database" in resources, "full schema resource is discoverable"
        )
        report.check(
            "schema://table/{table_name}" in templates,
            "per-table schema template is discoverable",
        )

        section("3. Valid tool calls")
        res = await client.call_tool(
            "search",
            {
                "table": "students",
                "filters": {"cohort": "A1"},
                "order_by": "score",
                "descending": True,
                "limit": 2,
            },
        )
        data = res.data
        report.check(
            data["count"] == 2 and data["has_more"] and data["rows"][0]["name"] == "Alice Nguyen",
            "search (filter + order + paging)",
            f"count={data['count']} has_more={data['has_more']} top={data['rows'][0]['name']}",
        )

        res = await client.call_tool(
            "insert",
            {"table": "students", "values": {"name": "Zoe Test", "cohort": "A1", "score": 100}},
        )
        inserted = res.data["inserted"]
        report.check(
            inserted["name"] == "Zoe Test" and "id" in inserted,
            "insert returns the stored row with generated id",
            f"inserted id={inserted.get('id')}",
        )

        res = await client.call_tool(
            "aggregate", {"table": "students", "metric": "count"}
        )
        report.check(
            res.data["rows"][0]["value"] == 9,
            "aggregate count(*) after insert",
            f"value={res.data['rows'][0]['value']}",
        )

        res = await client.call_tool(
            "aggregate",
            {"table": "students", "metric": "avg", "column": "score", "group_by": "cohort"},
        )
        groups = {r["group_key"]: round(r["value"], 2) for r in res.data["rows"]}
        report.check(
            "A1" in groups and "A2" in groups,
            "aggregate avg(score) grouped by cohort",
            json.dumps(groups),
        )

        section("4. Resource reads")
        full = await client.read_resource("schema://database")
        schema = json.loads(full[0].text)
        report.check(
            set(schema["tables"]) == {"students", "courses", "enrollments"},
            "read schema://database",
            f"tables={sorted(schema['tables'])}",
        )
        one = await client.read_resource("schema://table/students")
        table_schema = json.loads(one[0].text)
        col_names = [c["name"] for c in table_schema["columns"]]
        report.check(
            "score" in col_names and "cohort" in col_names,
            "read schema://table/students",
            f"columns={col_names}",
        )

        section("5. Invalid tool calls (must fail clearly)")
        msg = await expect_error(client, "search", {"table": "ghosts"})
        report.check("Unknown table" in msg, "unknown table rejected", msg)

        msg = await expect_error(
            client, "search", {"table": "students", "columns": ["nope"]}
        )
        report.check("Unknown column" in msg, "unknown column rejected", msg)

        msg = await expect_error(
            client,
            "search",
            {"table": "students", "filters": [{"column": "score", "op": "between", "value": 1}]},
        )
        report.check("Unsupported operator" in msg, "unsupported operator rejected", msg)

        msg = await expect_error(
            client, "aggregate", {"table": "students", "metric": "median", "column": "score"}
        )
        report.check("Unsupported metric" in msg, "bad aggregate metric rejected", msg)

        msg = await expect_error(client, "insert", {"table": "students", "values": {}})
        report.check("non-empty" in msg, "empty insert rejected", msg)

        # read a missing table via the resource template
        try:
            await client.read_resource("schema://table/ghosts")
            resource_err = ""
        except Exception as exc:
            resource_err = str(exc)
        report.check(
            "Unknown table" in resource_err,
            "unknown table rejected via schema resource template",
            resource_err,
        )

    section("Summary")
    print(f"  {report.summary()}")
    return report.ok


def main() -> None:
    ok = asyncio.run(run())
    print("\nRESULT:", "ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
