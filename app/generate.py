"""SQL proposal generation via aiforge_core's Router (never a raw SDK call)."""

import os
from pathlib import Path

from aiforge_core.llm import LLMResult, Router, router_from_env
from aiforge_core.llm.providers import MockProvider
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


def demo_mock_responses() -> dict:
    """Canned answers for the keyless offline demo (LLM_PROVIDER_ORDER=mock).

    The "sql" list is consumed one response per question (the last repeats):
    1. top customers, 2. tracks per genre, 3. a destructive DELETE the guard
    blocks live, 4+. top customers again.
    """
    top_customers = {
        "sql": (
            "SELECT c.first_name || ' ' || c.last_name AS customer, "
            "SUM(i.total) AS total_spent "
            "FROM customer AS c JOIN invoice AS i ON i.customer_id = c.customer_id "
            "GROUP BY c.customer_id, c.first_name, c.last_name "
            "ORDER BY total_spent DESC LIMIT 5"
        ),
        "rationale": "Join customers to invoices, sum totals, keep the top 5.",
        "tables": ["customer", "invoice"],
    }
    tracks_per_genre = {
        "sql": (
            "SELECT g.name AS genre, COUNT(*) AS track_count "
            "FROM track AS t JOIN genre AS g ON g.genre_id = t.genre_id "
            "GROUP BY g.name ORDER BY track_count DESC"
        ),
        "rationale": "Count tracks grouped by genre name.",
        "tables": ["track", "genre"],
    }
    delete_everything = {
        "sql": "DELETE FROM invoice",
        "rationale": "Destructive statement passed through so the guard can block it.",
        "tables": ["invoice"],
    }
    return {
        "sql": [top_customers, tracks_per_genre, delete_everything, top_customers],
        "summarize": {
            "sentence": (
                "Mock summary — the numbers above come straight from the rows; "
                "set GEMINI_API_KEY for a real model-written sentence."
            )
        },
    }


def build_router(prompts_dir: str | Path) -> Router:
    """Router from env; LLM_PROVIDER_ORDER=mock wires canned responses (no keys)."""
    order = [p.strip().lower() for p in os.getenv("LLM_PROVIDER_ORDER", "gemini,groq").split(",")]
    if "mock" in order:
        return Router([MockProvider(responses=demo_mock_responses())], prompts_dir=prompts_dir)
    return router_from_env(prompts_dir)
