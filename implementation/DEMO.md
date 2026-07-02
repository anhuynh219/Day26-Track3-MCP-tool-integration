# Demo script (~2 minutes)

Open one PowerShell terminal in `implementation/`. **Run each command once
before recording** so `uv` / `npx` caches are warm and everything is fast on
camera. Zoom the terminal font in (Ctrl `+`) so text is readable.

---

## Scene 1 — Intro (0:00–0:12)
- **Show:** the `implementation/` tree in VS Code (`db/`, `mcp_server.py`).
- **Say:** "A FastMCP server exposing a SQLite database through three tools —
  `search`, `insert`, `aggregate` — plus two schema resources. Logic is split
  cleanly: `db/` handles databases, `mcp_server.py` handles MCP."

## Scene 2 — Initialise the database (0:12–0:25)
```powershell
uv run python init_db.py
```
- **Say:** "Create and seed the demo database — 8 students across cohorts
  A1/A2/B1, 4 courses, 11 enrollments. It's idempotent, so it's reproducible."

## Scene 3 — Automated verification (0:25–0:52)  ⭐ key scene
```powershell
uv run python verify_server.py
```
- **Say:** "This connects an in-memory client and checks everything: the 3
  tools and 2 resources are discoverable; valid calls work — search with
  filter/order/paging, insert returning the row with its id, aggregate avg by
  cohort; and invalid requests (unknown table/column, bad operator, empty
  insert) are rejected with clear errors. **17/17 PASS.**"

## Scene 4 — Real client: Claude Code (0:52–1:20)
```powershell
claude mcp list
```
- **Say:** "The server connects to a real MCP client — Claude Code shows
  `sqlite-lab-local ✔ Connected`."
- Open `claude` (interactive) and prompt:
  > Dùng MCP server sqlite-lab-local: cho tôi điểm trung bình score theo từng cohort, rồi liệt kê top 2 students điểm cao nhất.
- **Say:** "Claude calls the server's `aggregate` and `search` tools and
  returns the result."

## Scene 5 — Resource (1:20–1:35)
- In the same `claude` session:
  > Đọc resource @sqlite-lab-local:schema://table/students và mô tả các cột.
- **Say:** "The client reads the dynamic per-table schema resource — schema
  context served over MCP."

## Scene 6 — Bonus: HTTP + bearer auth (1:35–1:52)
```powershell
uv run python demo_http_auth.py
```
- **Say:** "Bonus: an authenticated HTTP transport. No token → 401
  Unauthorized; with the token → connected and tools listed. **RESULT: PASS.**"

## Scene 7 — Wrap (1:52–2:00)
- **Show:** `db/base.py` and `db/postgres_adapter.py` briefly.
- **Say:** "The architecture is backend-swappable — the same MCP surface runs
  over SQLite or PostgreSQL. Thanks for watching."

---

### Optional: MCP Inspector (visual tool/resource browser)
```powershell
.\start_inspector.ps1
```
Open the printed URL, click the **Tools** and **Resources** tabs to show the
schemas, run a valid call, then a call to a missing table to show the error.
