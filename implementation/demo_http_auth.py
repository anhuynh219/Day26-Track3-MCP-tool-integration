"""Self-contained demo of the HTTP transport + bearer-token auth (bonus).

Runs the whole thing in ONE command (great for a demo video / grading):

    uv run python demo_http_auth.py

It starts the server as a subprocess on an HTTP port with a required token,
then connects a client twice:

* without a token  -> expect 401 Unauthorized (rejected)
* with the token   -> expect success (tools listed)

Prints a PASS/FAIL line and exits 0 only if auth behaves correctly.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
from pathlib import Path

from fastmcp import Client

TOKEN = "lab-secret-123"
HERE = Path(__file__).resolve().parent


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _try_connect(url: str, auth: str | None) -> tuple[bool, str]:
    try:
        async with Client(url, auth=auth) as client:
            tools = [t.name for t in await client.list_tools()]
            return True, f"connected, tools={tools}"
    except Exception as exc:  # noqa: BLE001 - we report whatever went wrong
        msg = str(exc) or type(exc).__name__
        return False, f"{type(exc).__name__}: {msg[:120]}"


def _wait_for_port(port: int, timeout: float = 30.0) -> bool:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


async def main() -> int:
    port = _free_port()
    url = f"http://127.0.0.1:{port}/mcp"

    env = {**os.environ, "MCP_AUTH_TOKEN": TOKEN}
    proc = subprocess.Popen(
        [sys.executable, str(HERE / "mcp_server.py"),
         "--transport", "http", "--port", str(port)],
        env=env,
        cwd=str(HERE),
    )
    try:
        if not _wait_for_port(port):
            print("FAIL: server did not start")
            return 1
        print(f"Server running on {url} (MCP_AUTH_TOKEN required)\n")

        ok_no, detail_no = await _try_connect(url, auth=None)
        print(f"[no token]   {'CONNECTED' if ok_no else 'REJECTED'} -> {detail_no}")

        ok_yes, detail_yes = await _try_connect(url, auth=TOKEN)
        print(f"[with token] {'CONNECTED' if ok_yes else 'REJECTED'} -> {detail_yes}")

        passed = (not ok_no) and ok_yes
        print("\nRESULT:", "PASS (auth enforced correctly)" if passed
              else "FAIL (auth did not behave as expected)")
        return 0 if passed else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
