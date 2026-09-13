"""LIMIT is injected when missing and lowered when too large."""

from app.guard import guard


def test_limit_injected(allowed_tables):
    result = guard("SELECT * FROM track", allowed_tables)
    assert result.ok
    assert "LIMIT 200" in result.sql
    assert "LIMIT 200 added" in result.rewrites


def test_limit_lowered(allowed_tables):
    result = guard("SELECT * FROM track LIMIT 5000", allowed_tables)
    assert result.ok
    assert "LIMIT 200" in result.sql
    assert "5000" not in result.sql
    assert "LIMIT lowered to 200" in result.rewrites


def test_small_limit_untouched(allowed_tables):
    result = guard("SELECT * FROM track LIMIT 5", allowed_tables)
    assert result.ok
    assert "LIMIT 5" in result.sql
    assert result.rewrites == []


def test_cte_query_gets_limit(allowed_tables):
    sql = "WITH t AS (SELECT genre_id FROM track) SELECT count(*) AS n FROM t"
    result = guard(sql, allowed_tables)
    assert result.ok
    assert "LIMIT 200" in result.sql
