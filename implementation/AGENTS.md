# Agent instructions

Use the `sqlite-lab` MCP server whenever a task needs database schema
context or SQL-backed record lookup over the students / courses /
enrollments dataset.

Guidelines:

- Read `schema://database` (or `schema://table/{table_name}`) first so you
  reference real table and column names.
- Use `search` to read rows (supports filters, ordering, and pagination),
  `insert` to add a row, and `aggregate` for count / avg / sum / min / max.
- The server validates every request. If a call fails, read the error
  message: it names the unknown table/column, unsupported operator, or bad
  metric and lists the valid options.
