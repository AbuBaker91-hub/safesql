"""Vercel Python serverless entrypoint: exposes the FastAPI ASGI app as `app`.

Cold start is cheap: migrations are an idempotent no-op and the schema summary
is a handful of catalog queries. Chinook data is NEVER loaded here — seed the
remote database once with `python -m app.seed` (see README Deploy).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402,F401
