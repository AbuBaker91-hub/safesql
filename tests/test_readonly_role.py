"""The read-only role really cannot write, even if every other layer failed."""

import psycopg
import pytest

from app.execute import run_readonly


@pytest.fixture
def readonly_url(test_db):
    """A Chinook-ish table plus the readonly_app role inside the fresh test DB."""
    test_db.execute("CREATE TABLE artist (artist_id int PRIMARY KEY, name text)")
    test_db.execute("INSERT INTO artist VALUES (1, 'AC/DC'), (2, 'Accept')")
    test_db.execute(
        """DO $$
           BEGIN
               IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'readonly_app') THEN
                   CREATE ROLE readonly_app LOGIN PASSWORD 'readonly';
               ELSE
                   ALTER ROLE readonly_app LOGIN PASSWORD 'readonly';
               END IF;
           END
           $$"""
    )
    test_db.execute("GRANT USAGE ON SCHEMA public TO readonly_app")
    test_db.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_app")
    info = test_db.info
    return f"postgresql://readonly_app:readonly@{info.host}:{info.port}/{info.dbname}"


def test_insert_as_readonly_role_is_denied(readonly_url):
    with psycopg.connect(readonly_url) as conn:
        assert conn.execute("SELECT name FROM artist ORDER BY artist_id").fetchone()[0] == "AC/DC"
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("INSERT INTO artist VALUES (999, 'x')")


def test_run_readonly_selects_but_never_writes(readonly_url):
    columns, rows = run_readonly("SELECT name FROM artist ORDER BY artist_id", url=readonly_url)
    assert columns == ["name"]
    assert rows == [("AC/DC",), ("Accept",)]
    # even the transaction itself is READ ONLY on top of the role's privileges
    with pytest.raises(psycopg.Error):
        run_readonly("INSERT INTO artist VALUES (999, 'x')", url=readonly_url)
