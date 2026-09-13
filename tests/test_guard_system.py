"""System catalogs are never queryable."""

from app.guard import guard


def test_pg_catalog_blocked(allowed_tables):
    result = guard("SELECT * FROM pg_catalog.pg_tables", allowed_tables)
    assert not result.ok
    assert result.block_reason == "system_table"


def test_information_schema_blocked(allowed_tables):
    result = guard("SELECT table_name FROM information_schema.tables", allowed_tables)
    assert not result.ok
    assert result.block_reason == "system_table"


def test_unqualified_pg_view_blocked(allowed_tables):
    result = guard("SELECT * FROM pg_tables", allowed_tables)
    assert not result.ok
    assert result.block_reason == "system_table"


def test_pg_catalog_in_subquery_blocked(allowed_tables):
    sql = "SELECT name FROM artist WHERE name IN (SELECT usename FROM pg_catalog.pg_user)"
    result = guard(sql, allowed_tables)
    assert not result.ok
    assert result.block_reason == "system_table"
