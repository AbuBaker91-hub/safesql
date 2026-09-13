"""Compact schema summary built once at startup.

The model never sees the database — it sees this text: table names, columns
with types, foreign keys, and 3 sample rows per table. The table names double
as the guard's allow-list.
"""

from dataclasses import dataclass

import psycopg

# Infrastructure tables are never shown to the model and never queryable.
EXCLUDED_TABLES = frozenset(
    {"queries", "audit_log", "chunks", "processed_keys", "schema_migrations"}
)


@dataclass(frozen=True)
class SchemaInfo:
    summary: str
    allowed_tables: frozenset[str]


def _truncate(value, width: int = 40) -> str:
    text = repr(value)
    return text if len(text) <= width else text[: width - 1] + "…"


def build_schema_info(conn: psycopg.Connection) -> SchemaInfo:
    columns_by_table: dict[str, list[tuple[str, str]]] = {}
    for table, column, dtype in conn.execute(
        """SELECT table_name, column_name, data_type
           FROM information_schema.columns
           WHERE table_schema = 'public'
           ORDER BY table_name, ordinal_position"""
    ).fetchall():
        if table in EXCLUDED_TABLES:
            continue
        columns_by_table.setdefault(table, []).append((column, dtype))

    fks: dict[str, list[str]] = {}
    for table, column, f_table, f_column in conn.execute(
        """SELECT tc.table_name, kcu.column_name, ccu.table_name, ccu.column_name
           FROM information_schema.table_constraints tc
           JOIN information_schema.key_column_usage kcu
             ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
           JOIN information_schema.constraint_column_usage ccu
             ON tc.constraint_name = ccu.constraint_name
            AND tc.table_schema = ccu.table_schema
           WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
           ORDER BY tc.table_name, kcu.column_name"""
    ).fetchall():
        if table in EXCLUDED_TABLES:
            continue
        fks.setdefault(table, []).append(f"{column} -> {f_table}.{f_column}")

    lines: list[str] = []
    for table, columns in sorted(columns_by_table.items()):
        lines.append(f"table {table}")
        lines.append("  columns: " + ", ".join(f"{c} {t}" for c, t in columns))
        if table in fks:
            lines.append("  foreign keys: " + "; ".join(fks[table]))
        try:
            samples = conn.execute(f'SELECT * FROM public."{table}" LIMIT 3').fetchall()
        except psycopg.Error:
            samples = []
        if samples:
            lines.append("  sample rows:")
            for row in samples:
                lines.append("    (" + ", ".join(_truncate(v) for v in row) + ")")
        lines.append("")

    return SchemaInfo(
        summary="\n".join(lines).strip() + "\n",
        allowed_tables=frozenset(columns_by_table),
    )
