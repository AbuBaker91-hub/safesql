"""The remaining guard rules: unparseable input, comments, SELECT INTO."""

from app.guard import guard


def test_unparseable_blocked(allowed_tables):
    result = guard("SELEC banana FRO artist", allowed_tables)
    assert not result.ok
    assert result.block_reason == "unparseable"


def test_empty_blocked(allowed_tables):
    result = guard("", allowed_tables)
    assert not result.ok
    assert result.block_reason == "unparseable"


def test_line_comment_blocked(allowed_tables):
    result = guard("SELECT name FROM artist -- sneaky", allowed_tables)
    assert not result.ok
    assert result.block_reason == "comment"


def test_block_comment_blocked(allowed_tables):
    result = guard("SELECT /* hidden */ name FROM artist", allowed_tables)
    assert not result.ok
    assert result.block_reason == "comment"


def test_select_into_blocked(allowed_tables):
    result = guard("SELECT * INTO backup_artist FROM artist", allowed_tables)
    assert not result.ok
    assert result.block_reason == "select_into"


def test_union_of_selects_passes(allowed_tables):
    sql = "SELECT name FROM artist UNION SELECT title FROM album LIMIT 50"
    result = guard(sql, allowed_tables)
    assert result.ok
