"""Read-only execution and the ask pipeline (generate -> guard -> execute -> summarize).

Execution always runs as the SELECT-only role `readonly_app` (READONLY_DATABASE_URL),
inside a READ ONLY transaction with a 5 second statement timeout — three layers
under the guard, so even a guard bug cannot write.

On a database error there is exactly one repair attempt: generate is called
again with the error message appended, the new SQL is guarded and executed.
If that also fails, the question ends as status "failed" with both attempts
recorded (response, queries row, audit log).
"""

import datetime
import decimal
import os
import time
import uuid
from collections.abc import Callable

import psycopg
from aiforge_core import audit
from aiforge_core.llm import AllProvidersFailed, Router, ValidationFailed

from .generate import propose_sql
from .guard import guard
from .schema import SchemaInfo
from .summarize import summarize_rows

RunFn = Callable[[str], tuple[list[str], list[tuple]]]


def readonly_url() -> str:
    return os.environ.get(
        "READONLY_DATABASE_URL", "postgresql://readonly_app:readonly@localhost:5432/app"
    )


def run_readonly(sql: str, url: str | None = None) -> tuple[list[str], list[tuple]]:
    """Run one statement as readonly_app: READ ONLY transaction, 5s timeout."""
    with psycopg.connect(url or readonly_url()) as conn:  # autocommit off: a real txn
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = 5000")
            cur.execute(sql)
            columns = [d.name for d in cur.description] if cur.description else []
            rows = cur.fetchall()
    return columns, rows


def _jsonable(value):
    if isinstance(value, bool | int | float | str) or value is None:
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, datetime.date | datetime.datetime | datetime.time):
        return value.isoformat()
    if isinstance(value, uuid.UUID | bytes | memoryview):
        return str(value)
    return str(value)


def process_question(
    question: str,
    *,
    conn: psycopg.Connection,
    router: Router,
    schema_info: SchemaInfo,
    run: RunFn = run_readonly,
) -> dict:
    """The full pipeline for one question. Audits every stage; ref = query id."""
    start = time.monotonic()
    qid = conn.execute(
        "INSERT INTO queries (question, status) VALUES (%s, 'failed') RETURNING id",
        (question,),
    ).fetchone()[0]
    ref = str(qid)

    attempts: list[dict] = []
    result: dict = {
        "id": qid,
        "question": question,
        "status": "failed",
        "summary": "",
        "columns": [],
        "rows": [],
        "sql": "",
        "rationale": "",
        "rewrites": [],
        "block_reason": "",
        "attempts": attempts,
    }

    def finish(
        status: str,
        *,
        block_reason: str = "",
        rows_returned: int = 0,
        prompt_version: str = "",
        proposed_sql: str = "",
        final_sql: str = "",
    ) -> dict:
        latency_ms = int((time.monotonic() - start) * 1000)
        conn.execute(
            """UPDATE queries SET proposed_sql=%s, final_sql=%s, status=%s, block_reason=%s,
               rows_returned=%s, latency_ms=%s, prompt_version=%s WHERE id=%s""",
            (proposed_sql, final_sql, status, block_reason, rows_returned, latency_ms,
             prompt_version, qid),
        )
        result.update(status=status, block_reason=block_reason, latency_ms=latency_ms)
        return result

    error: str | None = None
    for attempt in (1, 2):
        # --- generate ---
        try:
            gen = propose_sql(router, question, schema_info.summary, error=error)
        except (ValidationFailed, AllProvidersFailed) as e:
            audit.record(conn, "generate", ref=ref, input_hash=audit.input_hash(question),
                         ok=False, detail=str(e)[:500])
            result["summary"] = "The model could not produce a valid SQL proposal."
            return finish("failed", block_reason="generation_failed")
        proposal = gen.data
        audit.record(conn, "generate", ref=ref, input_hash=audit.input_hash(question),
                     prompt_version=gen.prompt_version, ok=True,
                     detail=f"provider={gen.provider} attempt={attempt}")

        # --- guard ---
        guarded = guard(proposal.sql, schema_info.allowed_tables)
        audit.record(conn, "guard", ref=ref, input_hash=audit.input_hash(proposal.sql),
                     ok=guarded.ok,
                     detail=guarded.block_reason or "; ".join(guarded.rewrites) or "clean")
        if not guarded.ok:
            attempts.append({"sql": proposal.sql, "error": f"blocked: {guarded.block_reason}"})
            result.update(sql=proposal.sql, rationale=proposal.rationale)
            return finish("blocked", block_reason=guarded.block_reason,
                          prompt_version=gen.prompt_version, proposed_sql=proposal.sql)

        # --- execute ---
        try:
            columns, rows = run(guarded.sql)
        except psycopg.Error as e:
            error = str(e).strip() or type(e).__name__
            attempts.append({"sql": guarded.sql, "error": error})
            audit.record(conn, "execute", ref=ref, input_hash=audit.input_hash(guarded.sql),
                         ok=False, detail=error[:500])
            if attempt == 2:
                result.update(sql=guarded.sql, rationale=proposal.rationale,
                              rewrites=guarded.rewrites)
                result["summary"] = "Both SQL attempts failed against the database."
                return finish("failed", block_reason="execution_failed",
                              prompt_version=gen.prompt_version,
                              proposed_sql=proposal.sql, final_sql=guarded.sql)
            continue  # one repair attempt: regenerate with the error appended
        audit.record(conn, "execute", ref=ref, input_hash=audit.input_hash(guarded.sql),
                     ok=True, detail=f"rows={len(rows)}")

        # --- summarize ---
        safe_rows = [[_jsonable(v) for v in row] for row in rows]
        try:
            summ = summarize_rows(router, question, columns, safe_rows[:5])
            summary = summ.data.sentence
            audit.record(conn, "summarize", ref=ref, input_hash=audit.input_hash(safe_rows[:5]),
                         prompt_version=summ.prompt_version, ok=True,
                         detail=f"provider={summ.provider}")
        except (ValidationFailed, AllProvidersFailed) as e:
            summary = f"Query ran read-only and returned {len(rows)} row(s)."
            audit.record(conn, "summarize", ref=ref, ok=False, detail=str(e)[:500])

        result.update(summary=summary, columns=columns, rows=safe_rows, sql=guarded.sql,
                      rationale=proposal.rationale, rewrites=guarded.rewrites)
        return finish("ok", rows_returned=len(rows), prompt_version=gen.prompt_version,
                      proposed_sql=proposal.sql, final_sql=guarded.sql)

    return result  # pragma: no cover — loop always returns
