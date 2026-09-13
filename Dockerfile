FROM python:3.12-slim

WORKDIR /srv

# git is needed for the pinned aiforge-core git dependency
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY . .
RUN pip install --no-cache-dir .

# First boot: migrations + Chinook + readonly role (all idempotent), then serve.
CMD ["sh", "-c", "python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
