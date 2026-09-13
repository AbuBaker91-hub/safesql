"""Exactly one statement, always."""

from app.guard import guard


def test_select_then_delete_blocked(allowed_tables):
    result = guard("SELECT 1; DELETE FROM customer", allowed_tables)
    assert not result.ok
    assert result.block_reason == "multi_statement"


def test_two_selects_blocked(allowed_tables):
    result = guard("SELECT 1; SELECT 2", allowed_tables)
    assert not result.ok
    assert result.block_reason == "multi_statement"


def test_trailing_semicolon_is_fine(allowed_tables):
    result = guard("SELECT name FROM artist LIMIT 5;", allowed_tables)
    assert result.ok
