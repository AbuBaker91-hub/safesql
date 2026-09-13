-- Project table: one row per asked question, whatever the outcome.
CREATE TABLE IF NOT EXISTS queries (
    id           BIGSERIAL PRIMARY KEY,
    question     TEXT NOT NULL,
    proposed_sql TEXT NOT NULL DEFAULT '',
    final_sql    TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'failed'
                 CHECK (status IN ('ok', 'blocked', 'failed')),
    block_reason TEXT NOT NULL DEFAULT '',
    rows_returned INTEGER NOT NULL DEFAULT 0,
    latency_ms   INTEGER NOT NULL DEFAULT 0,
    prompt_version TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS queries_created_at_idx ON queries (created_at DESC);
