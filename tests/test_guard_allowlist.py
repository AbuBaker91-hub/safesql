"""Only tables from the schema summary may be referenced."""

from app.guard import guard


def test_unknown_table_blocked(allowed_tables):
    result = guard("SELECT * FROM secrets", allowed_tables)
    assert not result.ok
    assert result.block_reason == "unknown_table"


def test_unknown_table_in_join_blocked(allowed_tables):
    sql = "SELECT a.name FROM artist a JOIN passwords p ON p.id = a.artist_id"
    result = guard(sql, allowed_tables)
    assert not result.ok
    assert result.block_reason == "unknown_table"


def test_other_schema_blocked(allowed_tables):
    result = guard("SELECT * FROM private.artist", allowed_tables)
    assert not result.ok
    assert result.block_reason == "unknown_table"


def test_public_qualified_allowed(allowed_tables):
    result = guard("SELECT name FROM public.artist LIMIT 5", allowed_tables)
    assert result.ok


def test_quoted_mixed_case_matches_case_insensitively(allowed_tables):
    # Identifier comparison is normalized: quoted or cased spellings of an
    # allow-listed table are accepted by the guard.
    result = guard('SELECT "Name" FROM "ARTIST" LIMIT 5', allowed_tables)
    assert result.ok


def test_cte_name_is_not_an_unknown_table(allowed_tables):
    sql = "WITH top AS (SELECT artist_id FROM album) SELECT * FROM top"
    result = guard(sql, allowed_tables)
    assert result.ok
