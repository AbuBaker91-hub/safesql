"""FastAPI app: POST /ask, GET /queries, GET /schema, UI at /."""

from pathlib import Path

from aiforge_core.app import create_app
from aiforge_core.db import connect, run_migrations
from fastapi import HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from .execute import process_question
from .generate import build_router
from .schema import build_schema_info

ROOT = Path(__file__).resolve().parents[1]

app = create_app("safesql", static_dir=ROOT / "static")

_state: dict = {}


def state() -> dict:
    """Lazy init: DB connection, migrations, router, schema summary (built once)."""
    if not _state:
        conn = connect()
        run_migrations(conn, ROOT / "migrations")
        _state["conn"] = conn
        _state["router"] = build_router(ROOT / "prompts")
        _state["schema"] = build_schema_info(conn)
    return _state


class AskRequest(BaseModel):
    question: str


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")
    s = state()
    return process_question(
        question, conn=s["conn"], router=s["router"], schema_info=s["schema"]
    )


@app.get("/queries")
def queries() -> list[dict]:
    rows = state()["conn"].execute(
        """SELECT id, question, status, block_reason, rows_returned, latency_ms,
                  prompt_version, final_sql, created_at
           FROM queries ORDER BY id DESC LIMIT 50"""
    ).fetchall()
    return [
        {
            "id": r[0],
            "question": r[1],
            "status": r[2],
            "block_reason": r[3],
            "rows_returned": r[4],
            "latency_ms": r[5],
            "prompt_version": r[6],
            "final_sql": r[7],
            "created_at": r[8].isoformat(),
        }
        for r in rows
    ]


@app.get("/schema", response_class=PlainTextResponse)
def schema_summary() -> str:
    """The exact text the model sees. Transparency route."""
    return state()["schema"].summary


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")
