"""Anything that is not a plain SELECT is blocked. No DB, no LLM."""

from app.guard import guard


def test_delete_blocked(allowed_tables):
    result = guard("DELETE FROM customer", allowed_tables)
    assert not result.ok
    assert result.block_reason == "not_select"


def test_drop_blocked(allowed_tables):
    result = guard("DROP TABLE artist", allowed_tables)
    assert not result.ok
    assert result.block_reason == "not_select"


def test_update_blocked(allowed_tables):
    result = guard("UPDATE customer SET email = 'x@x.com'", allowed_tables)
    assert not result.ok
    assert result.block_reason == "not_select"


def test_insert_blocked(allowed_tables):
    result = guard("INSERT INTO artist (artist_id, name) VALUES (999, 'x')", allowed_tables)
    assert not result.ok
    assert result.block_reason == "not_select"


def test_data_modifying_cte_blocked(allowed_tables):
    sql = "WITH gone AS (DELETE FROM customer RETURNING *) SELECT count(*) FROM gone"
    result = guard(sql, allowed_tables)
    assert not result.ok
    assert result.block_reason == "not_select"


def test_plain_select_passes(allowed_tables):
    result = guard("SELECT name FROM artist LIMIT 10", allowed_tables)
    assert result.ok
    assert result.block_reason == ""
