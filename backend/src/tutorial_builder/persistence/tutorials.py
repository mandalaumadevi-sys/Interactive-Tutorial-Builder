"""Persist finished tutorials to the database (Supabase Postgres when reachable, else local
SQLite). The HTML file is also written to ``generated_tutorials/`` by the assembler — this stores
a copy in the DB so the tutorial is retrievable from Supabase too, not just from disk.
"""

from __future__ import annotations

from ..config import Settings, get_settings

_CREATE_PG = (
    "create table if not exists tutorials ("
    "run_id text primary key, course text, session text, output_path text, "
    "html text, created_at timestamptz default now())"
)
_UPSERT_PG = (
    "insert into tutorials (run_id, course, session, output_path, html) "
    "values (%s, %s, %s, %s, %s) "
    "on conflict (run_id) do update set course=excluded.course, session=excluded.session, "
    "output_path=excluded.output_path, html=excluded.html"
)


def save(run_id: str, course: str, session: str, html: str, output_path: str,
         *, settings: Settings | None = None) -> str:
    """Store the tutorial; returns which backend was used ("supabase" | "sqlite")."""
    settings = settings or get_settings()
    from .health import mark_supabase, supabase_ok

    if supabase_ok() is not False:  # True or unknown → try Postgres
        try:
            from .db import connection
            with connection(settings) as conn:
                conn.execute(_CREATE_PG)
                conn.execute(_UPSERT_PG, (run_id, course, session, output_path, html))
            mark_supabase(True)
            return "supabase"
        except Exception:  # noqa: BLE001 — fall back to local SQLite
            mark_supabase(False)

    from . import local
    local.save_tutorial(run_id, course, session, output_path, html, settings=settings)
    return "sqlite"
