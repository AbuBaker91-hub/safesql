"""SafeSQL MCP server (stdio): the same guard + read-only execution, for Claude.

Tools:
  describe_schema()      tables, columns, foreign keys, sample rows
  query_readonly(sql)    run a SELECT through the guard as role readonly_app

Run from the repo root (see README for the Claude Desktop / Claude Code config):
  python mcp_server.py
"""

from pathlib import Path

from aiforge_core import audit
from aiforge_core.db import connect, run_migrations

try:  # mcp >= 2 renamed FastMCP to MCPServer; same decorator API
    from mcp.server.mcpserver import MCPServer as FastMCP
except ModuleNotFoundError:  # pragma: no cover - mcp 1.x
    from mcp.server.fastmcp import FastMCP

from app.execute import _jsonable, run_readonly
from app.guard import guard
from app.schema import build_schema_info

ROOT = Path(__file__).resolve().parent
mcp = FastMCP("safesql")
_state: dict = {}


def state() -> dict:
    if not _state:
        conn = connect()
        run_migrations(conn, ROOT / "migrations")
        _state["conn"] = conn
        _state["schema"] = build_schema_info(conn)
    return _state


@mcp.tool()
def describe_schema() -> str:
    """Describe the demo database: tables, columns, foreign keys, sample rows."""
    return state()["schema"].summary


@mcp.tool()
def query_readonly(sql: str) -> dict:
    """Run one SELECT through the SafeSQL guard (read-only role, LIMIT capped at 200).

    Anything that is not a single clean SELECT on allow-listed tables is blocked.
    """
    s = state()
    conn = s["conn"]
    qid = conn.execute(
        "INSERT INTO queries (question, proposed_sql, status) VALUES (%s, %s, 'failed') RETURNING id",
        (f"[mcp] {sql[:200]}", sql),
    ).fetchone()[0]
    ref = str(qid)
    result = guard(sql, s["schema"].allowed_tables)
    audit.record(conn, "guard", ref=ref, input_hash=audit.input_hash(sql), ok=result.ok,
                 detail=result.block_reason or "; ".join(result.rewrites) or "clean")
    if not result.ok:
        conn.execute("UPDATE queries SET status='blocked', block_reason=%s WHERE id=%s",
                     (result.block_reason, qid))
        return {"status": "blocked", "block_reason": result.block_reason}
    try:
        columns, rows = run_readonly(result.sql)
    except Exception as e:
        audit.record(conn, "execute", ref=ref, ok=False, detail=str(e)[:500])
        conn.execute("UPDATE queries SET status='failed', final_sql=%s WHERE id=%s",
                     (result.sql, qid))
        return {"status": "failed", "sql": result.sql, "error": str(e)}
    audit.record(conn, "execute", ref=ref, ok=True, detail=f"rows={len(rows)}")
    conn.execute(
        "UPDATE queries SET status='ok', final_sql=%s, rows_returned=%s WHERE id=%s",
        (result.sql, len(rows), qid),
    )
    return {
        "status": "ok",
        "sql": result.sql,
        "rewrites": result.rewrites,
        "columns": columns,
        "rows": [[_jsonable(v) for v in row] for row in rows],
    }


if __name__ == "__main__":
    mcp.run()
