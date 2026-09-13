# SafeSQL — chat-to-SQL with read-only guardrails and an MCP server

**The model proposes, the database disposes.**

Ask questions in plain language over a real Postgres database. The LLM only ever *proposes* SQL; deterministic code parses it, validates it, rewrites it, and runs it as a SELECT-only role with limits, timeouts and a full audit trail.

## 1. Problem

Teams want "just let people ask the database questions", but handing an LLM a database connection is how you lose a table. Text-to-SQL demos that trust the model are one hallucinated `DROP` away from an incident. The fix is boring and structural: let the model write SQL, and let code that cannot hallucinate decide what actually runs.

## 2. What it does

- Chat UI: ask a question, get a one-sentence summary, a results table, and a collapsible "SQL that ran" block with the model's rationale and every rewrite the guard applied.
- `guard()` — a pure function, no DB, no LLM — parses each proposal with **sqlglot** and blocks anything that is not one clean SELECT on allow-listed tables (exact rules below).
- Execution runs as Postgres role `readonly_app` inside a `READ ONLY` transaction with a 5s statement timeout: three independent layers under the guard.
- One repair attempt: on a database error, the error message is fed back to the model once; a second failure is an honest `failed` answer showing both attempts.
- Every question is logged to a `queries` table, and every stage (generate, guard, execute, summarize) writes an audit row.
- **MCP server** (`mcp_server.py`): tools `describe_schema` and `query_readonly` reuse the exact same guard and executor, so Claude Desktop / Claude Code can query the demo DB safely.
- Demo data: the Chinook music store (artists, albums, tracks, invoices, customers).

[▶ Watch the 30-second demo video](docs/safesql-demo.mp4) · [Try the live demo](https://safesql.vercel.app)

**Ask a question — results table plus a one-sentence summary built from the rows:**

![Good question: results table and summary](docs/screenshots/02-good-question-table-summary.png)

**Expand "SQL that ran" — the model's rationale and every rewrite the guard applied:**

![SQL block with rationale and the LIMIT 200 rewrite](docs/screenshots/03-sql-block-rewrites.png)

**Ask for something destructive — blocked with the exact reason, and the attempted SQL shown:**

![Blocked DROP TABLE with reason "not a SELECT"](docs/screenshots/04-blocked-delete.png)

**Every question lands in the history with its status and latency:**

![History panel with ok and blocked queries](docs/screenshots/05-history.png)

## 3. Architecture

```mermaid
flowchart LR
  UI[static UI /] --> API[FastAPI /ask]
  MCP[Claude via MCP] --> G
  API --> R[aiforge-core Router]
  R --> P1[Gemini 2.5 Flash]
  R --> P2[Groq llama-3.3-70b]
  R -->|SqlProposal| G[guard.py sqlglot]
  G -->|blocked + reason| API
  G -->|rewritten SELECT| X[execute.py readonly_app READ ONLY 5s]
  X --> DB[(Postgres: chinook tables, queries, audit_log)]
  X --> S[summarize.py]
  S --> API
```

The model never sees the database. It sees a compact schema summary (`GET /schema`): table names, columns with types, foreign keys, three sample rows per table. Those table names are also the guard's allow-list.

**Routes**: `POST /ask {question}` → `{summary, columns, rows, sql, rationale, rewrites, status, block_reason, attempts}` · `GET /queries` history · `GET /schema` transparency · `GET /health`.

### MCP server for Claude

Add to `claude_desktop_config.json` (or `.mcp.json` for Claude Code) — adjust the paths:

```json
{
  "mcpServers": {
    "safesql": {
      "command": "/path/to/safesql/.venv/bin/python",
      "args": ["/path/to/safesql/mcp_server.py"],
      "env": { "DATABASE_URL": "postgresql://app:app@localhost:5432/app",
               "READONLY_DATABASE_URL": "postgresql://readonly_app:readonly@localhost:5432/app" }
    }
  }
}
```

Then ask Claude to "list the tables and count the invoices" — its queries go through the same guard and show up in the history with their status.

## 4. Guardrails

All deterministic, all tested, all enforced by parsing (sqlglot, postgres dialect) — never by regex on strings:

- Unparseable SQL → blocked (`unparseable`); more than one statement → blocked (`multi_statement`).
- The single statement must be a SELECT; CTEs are fine, data-modifying CTEs and any DML/DDL node anywhere in the tree are not (`not_select`).
- No comments (`comment`), no `SELECT ... INTO` (`select_into`).
- Denied functions: `pg_sleep`, `pg_read_file`, `lo_import`, `dblink` (`denied_function`).
- No `pg_catalog`, `information_schema`, or `pg_*` relations (`system_table`).
- Only allow-listed tables from the schema summary, compared on sqlglot-normalized identifiers, i.e. case-insensitively and quote-aware (`unknown_table`).
- Missing `LIMIT` → `LIMIT 200` injected; `LIMIT > 200` → lowered. Every rewrite is returned and shown in the UI.
- Even past the guard: SELECT-only role, `READ ONLY` transaction, 5000ms statement timeout, per-IP rate limit.

## 5. Limits

- One database, one schema (`public`); no cross-schema or multi-DB routing.
- The guard's allow-list check is table-level, not column-level.
- Case-insensitive allow-list matching can accept a quoted spelling (e.g. `"Artist"`) that Postgres itself will then reject; that surfaces as a normal execution error and repair attempt, never a security hole.
- One repair attempt, then an honest failure — no agentic retry loops.
- When `READONLY_DATABASE_URL` is not set (managed Postgres with a single connection string, e.g. Neon), execution connects with `DATABASE_URL` and drops privileges with `SET LOCAL ROLE readonly_app` inside the `READ ONLY` transaction — the SELECT-only role, read-only transaction and 5s timeout all still apply; there is just no separate login.
- The offline demo (`LLM_PROVIDER_ORDER=mock`) uses canned proposals, so the answers rotate through a fixed set; real questions need a free Gemini or Groq key.
- Chinook sample database © Luis Rocha, committed as `db/chinook.sql` (v1.4.5, lowercase identifiers) under its [license](https://github.com/lerocha/chinook-database/blob/master/LICENSE.md).

## 6. Run

```bash
cp .env.example .env      # add GEMINI_API_KEY, or set LLM_PROVIDER_ORDER=mock for keyless
make setup                # venv, deps, postgres via docker, migrations + chinook + roles
make demo                 # http://localhost:8000
```

Or fully containerized: `docker compose up --build` (defaults to the keyless mock provider).

### Deploy (Vercel + Neon, free tier)

The repo is serverless-ready: `api/index.py` exposes the ASGI app, `vercel.json` routes everything to it, and `requirements.txt` holds the runtime deps. Cold starts only run idempotent migrations and build the schema summary (a handful of catalog queries) — the 600 KB Chinook dump is **never** loaded at cold start.

1. Neon: create a free project, copy the pooled `DATABASE_URL`.
2. Seed the remote database **once** from your machine (migrations + Chinook + readonly role):

   ```bash
   # bash:        DATABASE_URL="postgres://<neon-owner-url>" .venv/bin/python -m app.seed
   # PowerShell:  $env:DATABASE_URL="postgres://<neon-owner-url>"; .venv\Scripts\python.exe -m app.seed
   ```

3. Vercel: import the repo, set env vars `DATABASE_URL` and `LLM_PROVIDER_ORDER=mock` (keyless demo) — no `READONLY_DATABASE_URL` needed; execution falls back to `SET LOCAL ROLE readonly_app` (see Limits).
4. Confirm `https://<app>.vercel.app/health` returns `{"ok": true}`.

### Deploy (Render + Neon, free tier)

1. Neon: create a free project, enable the `vector` extension, copy `DATABASE_URL`; run `db/roles.sql` once and set `READONLY_DATABASE_URL` with the `readonly_app` credentials.
2. Render: new Web Service from this repo, Docker runtime, add the env vars, health check `/health`.
3. First boot runs migrations and loads Chinook automatically (idempotent).
4. Confirm `https://<app>.onrender.com/health` returns `{"ok": true}`.
5. Rate limit stays on; the free Gemini quota is enough for demo traffic.

## 7. Tests

`make test` — no API keys, no network; guard tests need no database at all.

- `test_guard_dml` — DELETE/UPDATE/INSERT/DROP and data-modifying CTEs are blocked as `not_select`.
- `test_guard_multi` — `SELECT 1; DELETE …` is blocked as `multi_statement`.
- `test_guard_limit` — missing LIMIT injected, `LIMIT 5000` lowered to 200, small limits untouched.
- `test_guard_system` — `pg_catalog`, `information_schema`, bare `pg_*` views blocked as `system_table`.
- `test_guard_denylist` — `pg_sleep`, `pg_read_file`, `lo_import`, `dblink` blocked as `denied_function`.
- `test_guard_allowlist` — unknown tables blocked as `unknown_table`; quoted/cased spellings of allowed tables and CTE names pass.
- `test_guard_misc` — unparseable input, comments, `SELECT INTO`, UNION handling.
- `test_repair_loop` — a DB error triggers exactly one regenerate (the error is in the second prompt); a second error ends `failed` with both attempts in the response, the `queries` row, and the audit log; the happy path audits generate → guard → execute → summarize exactly once.
- `test_readonly_role` — an INSERT as `readonly_app` raises `InsufficientPrivilege` against a real Postgres.

## 8. Keywords

chat to SQL, natural language to SQL, text-to-SQL guardrails, read-only database tool, SQL validation, MCP server, AI analytics assistant, PostgreSQL, sqlglot, FastAPI.
