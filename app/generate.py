"""SQL proposal generation via aiforge_core's Router (never a raw SDK call)."""

import json
import os
import re
from pathlib import Path

from aiforge_core.llm import LLMResult, Router, router_from_env
from pydantic import BaseModel, Field


class SqlProposal(BaseModel):
    sql: str
    rationale: str = ""
    tables: list[str] = Field(default_factory=list)


def propose_sql(
    router: Router, question: str, schema_summary: str, error: str | None = None
) -> LLMResult:
    """One generate call. For the repair attempt, the DB error is appended."""
    if error:
        question = (
            f"{question}\n\n"
            f"The previous SQL attempt failed with this database error:\n{error}\n"
            f"Propose a corrected query."
        )
    return router.generate_json(
        "sql", {"question": question, "schema_summary": schema_summary}, schema=SqlProposal
    )


# ---------------------------------------------------------------------------
# Keyless offline demo (LLM_PROVIDER_ORDER=mock): canned proposals routed by
# keywords in the question, and summaries computed from the actual result rows.
# Demo-only; tests wire aiforge_core's MockProvider themselves.
# ---------------------------------------------------------------------------

_CANNED_SQL: list[tuple[tuple[str, ...], dict]] = [
    (
        ("drop", "truncate", "alter"),
        {
            "sql": "DROP TABLE customer",
            "rationale": "Destructive statement passed through so the guard can block it.",
            "tables": ["customer"],
        },
    ),
    (
        ("delete", "remove", "wipe", "update", "insert"),
        {
            "sql": "DELETE FROM invoice",
            "rationale": "Destructive statement passed through so the guard can block it.",
            "tables": ["invoice"],
        },
    ),
    (
        ("genre",),
        {
            "sql": (
                "SELECT g.name AS genre, COUNT(*) AS track_count "
                "FROM track AS t JOIN genre AS g ON g.genre_id = t.genre_id "
                "GROUP BY g.name ORDER BY track_count DESC"
            ),
            "rationale": "Count tracks per genre and sort so the biggest genre comes first.",
            "tables": ["track", "genre"],
        },
    ),
    (
        ("album", "artist"),
        {
            "sql": (
                "SELECT ar.name AS artist, COUNT(al.album_id) AS albums "
                "FROM artist AS ar JOIN album AS al ON al.artist_id = ar.artist_id "
                "GROUP BY ar.name ORDER BY albums DESC LIMIT 10"
            ),
            "rationale": "Rank artists by how many albums they have in the catalog.",
            "tables": ["artist", "album"],
        },
    ),
    (
        (),  # default: top customers by spend
        {
            "sql": (
                "SELECT c.first_name || ' ' || c.last_name AS customer, "
                "SUM(i.total) AS total_spent "
                "FROM customer AS c JOIN invoice AS i ON i.customer_id = c.customer_id "
                "GROUP BY c.customer_id, c.first_name, c.last_name "
                "ORDER BY total_spent DESC LIMIT 5"
            ),
            "rationale": "Join customers to invoices, sum the totals, keep the top 5.",
            "tables": ["customer", "invoice"],
        },
    ),
]


def _mock_summary(prompt: str) -> dict:
    """One sentence built from the first result row embedded in the prompt."""
    columns: list = []
    rows: list = []
    m = re.search(r"Columns:\s*(.*?)\nFirst rows:\s*(.*)$", prompt, re.DOTALL)
    if m:
        try:
            columns = json.loads(m.group(1))
            rows = json.loads(m.group(2))
        except ValueError:
            pass
    if not rows or not columns:
        return {"sentence": "No matching rows were found."}
    first = rows[0]
    pairs = ", ".join(f"{col} {val}" for col, val in zip(columns, first, strict=False))
    return {"sentence": f"The first of {len(rows)} row(s) shown ranks highest: {pairs}."}


class DemoMockProvider:
    """Offline provider: same interface as a real one, deterministic answers."""

    name = "mock"

    def complete(self, prompt: str, json_schema: dict) -> str:
        if json_schema.get("x-prompt-name") == "summarize":
            return json.dumps(_mock_summary(prompt))
        question = prompt.lower().rsplit("question:", 1)[-1]
        for keywords, proposal in _CANNED_SQL:
            if not keywords or any(k in question for k in keywords):
                return json.dumps(proposal)
        raise AssertionError("unreachable: the last canned entry matches everything")


def build_router(prompts_dir: str | Path) -> Router:
    """Router from env; LLM_PROVIDER_ORDER=mock wires canned responses (no keys)."""
    order = [p.strip().lower() for p in os.getenv("LLM_PROVIDER_ORDER", "gemini,groq").split(",")]
    if "mock" in order:
        return Router([DemoMockProvider()], prompts_dir=prompts_dir)
    return router_from_env(prompts_dir)
