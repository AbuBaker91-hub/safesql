"""Idempotent demo setup: migrations, Chinook sample data, readonly role.

Run with: python -m app.seed
The Chinook dump (db/chinook.sql, (c) Luis Rocha, MIT-style license) ships with
its own DROP/CREATE DATABASE and \\c psql commands; those lines are skipped so
the data loads into whatever database DATABASE_URL points at.
"""

from pathlib import Path

import psycopg
from aiforge_core.db import connect, run_migrations

ROOT = Path(__file__).resolve().parents[1]
_SKIP_PREFIXES = ("\\", "DROP DATABASE", "CREATE DATABASE")


def load_chinook(conn: psycopg.Connection) -> bool:
    """Load db/chinook.sql once; returns True if it loaded, False if present."""
    if conn.execute("SELECT to_regclass('public.artist')").fetchone()[0]:
        return False
    raw = (ROOT / "db" / "chinook.sql").read_text(encoding="utf-8")
    lines = [
        line
        for line in raw.splitlines()
        if not line.strip().upper().startswith(_SKIP_PREFIXES)
    ]
    conn.execute("\n".join(lines))
    return True


def apply_roles(conn: psycopg.Connection) -> None:
    conn.execute((ROOT / "db" / "roles.sql").read_text(encoding="utf-8"))


def main() -> None:
    conn = connect()
    run_migrations(conn, ROOT / "migrations")
    loaded = load_chinook(conn)
    apply_roles(conn)
    count = conn.execute("SELECT count(*) FROM track").fetchone()[0]
    print(f"chinook {'loaded' if loaded else 'already present'}: {count} tracks; "
          f"role readonly_app ready")
    conn.close()


if __name__ == "__main__":
    main()
