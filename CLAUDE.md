# safesql: ask questions in plain language over a real database; the model proposes SQL, deterministic code validates it and runs it read-only with limits and logging.
Portfolio quality: small scope, complete execution. Stack is fixed (see aiforge-core README).
Rules:
- All model calls go through aiforge_core.llm.Router.generate_json with a Pydantic schema. Never call an SDK directly.
- ValidationFailed means review queue or an honest failure message. Never a partial write.
- Every write path is wrapped in idempotency.once. Every stage calls audit.record.
- Tests use MockProvider and StubEmbedder only. No network in tests.
- Do not add frameworks, providers or dependencies without updating the README Limits section.
Commands: make setup | make test | make demo | make lint
