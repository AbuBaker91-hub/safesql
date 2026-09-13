"""The repair loop: one retry with the DB error appended, then an honest failure.

Uses test_db for the queries/audit tables; the "database" that executes the
guarded SQL is a stub, so the errors are deterministic.
"""

import psycopg
from aiforge_core import audit

from app.execute import process_question
from app.schema import SchemaInfo

SCHEMA = SchemaInfo(
    summary="table artist\n  columns: artist_id integer, name text\n",
    allowed_tables=frozenset({"artist"}),
)

GOOD_ROWS = (["name"], [("AC/DC",), ("Accept",)])


def sql_calls(mock_provider):
    return [c for c in mock_provider.calls if c["prompt_name"] == "sql"]


def test_error_then_repair_succeeds(test_db, mock_provider, mock_router):
    mock_provider.set(
        "sql",
        [
            {"sql": "SELECT nme FROM artist LIMIT 5", "rationale": "first try", "tables": ["artist"]},
            {"sql": "SELECT name FROM artist LIMIT 5", "rationale": "fixed column", "tables": ["artist"]},
        ],
    )
    mock_provider.set("summarize", {"sentence": "Two artists were returned."})

    executed: list[str] = []

    def fake_run(sql: str):
        executed.append(sql)
        if len(executed) == 1:
            raise psycopg.Error('column "nme" does not exist')
        return GOOD_ROWS

    result = process_question(
        "list artists", conn=test_db, router=mock_router, schema_info=SCHEMA, run=fake_run
    )

    assert result["status"] == "ok"
    assert result["rows"] == [["AC/DC"], ["Accept"]]
    # generate was called exactly twice: the original and one repair.
    calls = sql_calls(mock_provider)
    assert len(calls) == 2
    # the repair prompt contains the database error message.
    assert 'column "nme" does not exist' in calls[1]["prompt"]
    # the failed first attempt is reported alongside the success.
    assert len(result["attempts"]) == 1
    assert "nme" in result["attempts"][0]["sql"]


def test_second_error_ends_failed_with_two_attempts(test_db, mock_provider, mock_router):
    mock_provider.set(
        "sql",
        [
            {"sql": "SELECT nme FROM artist LIMIT 5", "rationale": "", "tables": ["artist"]},
            {"sql": "SELECT nom FROM artist LIMIT 5", "rationale": "", "tables": ["artist"]},
        ],
    )
    mock_provider.set("summarize", {"sentence": "unused"})

    def always_fail(sql: str):
        raise psycopg.Error("column does not exist")

    result = process_question(
        "list artists", conn=test_db, router=mock_router, schema_info=SCHEMA, run=always_fail
    )

    assert result["status"] == "failed"
    assert result["block_reason"] == "execution_failed"
    assert len(sql_calls(mock_provider)) == 2
    # both attempts recorded in the response...
    assert len(result["attempts"]) == 2
    assert result["attempts"][0]["sql"] != result["attempts"][1]["sql"]
    # ...in the queries table...
    status, proposed, final = test_db.execute(
        "SELECT status, proposed_sql, final_sql FROM queries WHERE id = %s", (result["id"],)
    ).fetchone()
    assert status == "failed"
    assert proposed and final
    # ...and in the audit log: two generate, two guard, two execute rows.
    stages = [r["stage"] for r in audit.rows_for(test_db, str(result["id"]))]
    assert stages.count("generate") == 2
    assert stages.count("guard") == 2
    assert stages.count("execute") == 2


def test_happy_path_audits_every_stage_once(test_db, mock_provider, mock_router):
    mock_provider.set(
        "sql", {"sql": "SELECT name FROM artist LIMIT 5", "rationale": "", "tables": ["artist"]}
    )
    mock_provider.set("summarize", {"sentence": "Two artists were returned."})

    result = process_question(
        "list artists", conn=test_db, router=mock_router, schema_info=SCHEMA,
        run=lambda sql: GOOD_ROWS,
    )

    assert result["status"] == "ok"
    assert result["summary"] == "Two artists were returned."
    stages = [r["stage"] for r in audit.rows_for(test_db, str(result["id"]))]
    assert stages == ["generate", "guard", "execute", "summarize"]


def test_blocked_proposal_is_recorded(test_db, mock_provider, mock_router):
    mock_provider.set(
        "sql", {"sql": "DELETE FROM artist", "rationale": "", "tables": ["artist"]}
    )

    result = process_question(
        "delete everything", conn=test_db, router=mock_router, schema_info=SCHEMA,
        run=lambda sql: GOOD_ROWS,
    )

    assert result["status"] == "blocked"
    assert result["block_reason"] == "not_select"
    assert result["rows"] == []
    row = test_db.execute(
        "SELECT status, block_reason FROM queries WHERE id = %s", (result["id"],)
    ).fetchone()
    assert row == ("blocked", "not_select")
