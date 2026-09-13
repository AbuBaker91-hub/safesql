"""guard.py — the product. Deterministic validation of model-proposed SQL.

A pure function: no database, no LLM, no network. It takes the SQL string the
model proposed plus the allow-listed table names from schema.py, and either
blocks the query with an exact reason or returns a rewritten, safe-to-run
SELECT (LIMIT capped at 200) together with the list of rewrites applied.

Rules (all enforced through sqlglot parsing, dialect postgres):
- unparseable SQL                          -> blocked "unparseable"
- more than one statement                  -> blocked "multi_statement"
- any comment (`--` or `/* */`)            -> blocked "comment"
- final statement not a SELECT             -> blocked "not_select"
  (CTEs are fine; data-modifying CTEs and any DML/DDL node are not)
- SELECT ... INTO                          -> blocked "select_into"
- denied functions (pg_sleep, pg_read_file,
  lo_import, dblink)                       -> blocked "denied_function"
- pg_catalog / information_schema / pg_*   -> blocked "system_table"
- table outside the allow-list             -> blocked "unknown_table"
- missing LIMIT -> inject LIMIT 200; LIMIT > 200 -> lower to 200
"""

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers

MAX_LIMIT = 200
DENIED_FUNCTIONS = frozenset({"pg_sleep", "pg_read_file", "lo_import", "dblink"})
SYSTEM_SCHEMAS = frozenset({"pg_catalog", "information_schema"})

# Any of these node types anywhere in the tree (including inside a CTE) means
# the statement writes, alters, or escapes — never just a read.
_WRITE_NODE_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Drop",
    "Create",
    "Alter",
    "AlterTable",
    "Merge",
    "TruncateTable",
    "Grant",
    "Set",
    "Command",
    "Transaction",
    "Use",
    "Copy",
    "LoadData",
    "Lock",
)
_WRITE_NODES = tuple(t for name in _WRITE_NODE_NAMES if (t := getattr(exp, name, None)))
_SET_OPERATION = getattr(exp, "SetOperation", exp.Union)


@dataclass
class GuardResult:
    ok: bool
    sql: str
    rewrites: list[str] = field(default_factory=list)
    block_reason: str = ""


def _blocked(reason: str, sql: str = "") -> GuardResult:
    return GuardResult(ok=False, sql=sql, rewrites=[], block_reason=reason)


def _has_comments(sql: str) -> bool:
    for token in sqlglot.tokenize(sql, read="postgres"):
        if token.comments:
            return True
    return False


def _function_name(func: exp.Func) -> str:
    if isinstance(func, exp.Anonymous):
        return func.name.lower()
    return func.sql_name().lower()


def guard(sql: str, allowed_tables: frozenset[str] | set[str]) -> GuardResult:
    """Validate and rewrite one model-proposed SQL statement.

    Returns GuardResult(ok, sql, rewrites, block_reason). Never raises.
    """
    allowed = {t.lower() for t in allowed_tables}

    try:
        if _has_comments(sql):
            return _blocked("comment", sql)
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except Exception:
        return _blocked("unparseable", sql)

    if len(statements) == 0:
        return _blocked("unparseable", sql)
    if len(statements) > 1:
        return _blocked("multi_statement", sql)

    expr = statements[0]

    # The one statement must be a query (SELECT, or a set operation of SELECTs).
    if not isinstance(expr, (exp.Select, _SET_OPERATION)):
        return _blocked("not_select", sql)
    # No write/DDL/meta node anywhere in the tree — catches data-modifying CTEs.
    for node in expr.walk():
        if isinstance(node, _WRITE_NODES):
            return _blocked("not_select", sql)

    # SELECT ... INTO creates a table; block it.
    for select in expr.find_all(exp.Select):
        if select.args.get("into"):
            return _blocked("select_into", sql)

    for func in expr.find_all(exp.Func):
        if _function_name(func) in DENIED_FUNCTIONS:
            return _blocked("denied_function", sql)

    # Normalize identifiers the way Postgres would (unquoted -> lowercase),
    # so the allow-list comparison is case-insensitive and quote-aware.
    expr = normalize_identifiers(expr, dialect="postgres")

    cte_names = {cte.alias_or_name.lower() for cte in expr.find_all(exp.CTE)}
    for table in expr.find_all(exp.Table):
        schema_name = table.text("db").lower()
        name = table.name.lower()
        if schema_name in SYSTEM_SCHEMAS or name.startswith("pg_"):
            return _blocked("system_table", sql)
        if schema_name not in ("", "public"):
            return _blocked("unknown_table", sql)
        if name in cte_names:
            continue
        if name not in allowed:
            return _blocked("unknown_table", sql)

    rewrites: list[str] = []
    limit_node = expr.args.get("limit")
    if limit_node is None:
        expr = expr.limit(MAX_LIMIT)
        rewrites.append(f"LIMIT {MAX_LIMIT} added")
    else:
        value = limit_node.expression
        if isinstance(value, exp.Literal) and value.is_int:
            if int(value.name) > MAX_LIMIT:
                value.replace(exp.Literal.number(MAX_LIMIT))
                rewrites.append(f"LIMIT lowered to {MAX_LIMIT}")
        else:
            # LIMIT ALL or a non-literal limit: replace conservatively.
            expr = expr.limit(MAX_LIMIT)
            rewrites.append(f"LIMIT rewritten to {MAX_LIMIT}")

    return GuardResult(ok=True, sql=expr.sql(dialect="postgres"), rewrites=rewrites)
