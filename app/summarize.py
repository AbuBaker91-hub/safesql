"""One-sentence result summaries, built from the rows — never the question alone."""

from aiforge_core.llm import LLMResult, Router
from pydantic import BaseModel


class Summary(BaseModel):
    sentence: str


def summarize_rows(
    router: Router, question: str, columns: list[str], first_rows: list[list]
) -> LLMResult:
    return router.generate_json(
        "summarize",
        {"question": question, "columns": columns, "first_rows": first_rows},
        schema=Summary,
    )
