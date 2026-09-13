"""Dangerous functions are blocked by name."""

import pytest

from app.guard import guard


def test_pg_sleep_blocked(allowed_tables):
    result = guard("SELECT pg_sleep(10)", allowed_tables)
    assert not result.ok
    assert result.block_reason == "denied_function"


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT lo_import('/etc/passwd')",
        "SELECT * FROM dblink('host=evil', 'SELECT 1') AS t(x int)",
        "SELECT name, pg_sleep(1) FROM artist",
    ],
)
def test_denied_functions_blocked(sql, allowed_tables):
    result = guard(sql, allowed_tables)
    assert not result.ok
    assert result.block_reason == "denied_function"


def test_normal_functions_pass(allowed_tables):
    result = guard("SELECT upper(name), count(*) FROM artist GROUP BY name", allowed_tables)
    assert result.ok
