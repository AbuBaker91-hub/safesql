from pathlib import Path

import pytest
from aiforge_core.testing import *  # noqa: F401,F403

ROOT = Path(__file__).resolve().parents[1]

# The tables the committed db/chinook.sql (v1.4.5, lowercase identifiers) creates.
CHINOOK_TABLES = frozenset(
    {
        "album",
        "artist",
        "customer",
        "employee",
        "genre",
        "invoice",
        "invoice_line",
        "media_type",
        "playlist",
        "playlist_track",
        "track",
    }
)


@pytest.fixture
def prompts_dir():
    return str(ROOT / "prompts")


@pytest.fixture
def project_migrations_dir():
    return str(ROOT / "migrations")


@pytest.fixture
def allowed_tables():
    return CHINOOK_TABLES
