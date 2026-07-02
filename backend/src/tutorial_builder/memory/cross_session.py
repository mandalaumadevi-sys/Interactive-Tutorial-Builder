"""Cross-session memory — a Supabase Postgres table keyed by course (PRD §10).

Persists three categories across runs of the same course (shared by all its sessions):
  • human feedback / corrections (division edits, final-review notes)
  • accepted few-shot signals (defined concepts, good MCQ topics)
  • a lightweight course/style profile (eval history → difficulty/quality trend)

Backed by the ``course_memory`` table (one row per course, jsonb columns). No local files.
"""

from __future__ import annotations

from psycopg.types.json import Json

from ..config import Settings, get_settings
from ..persistence.db import connection

_EMPTY = ("prior_concepts", "mcq_topics", "feedback", "eval_history")


def _use_local() -> bool:
    """True when Supabase is known to be down — skip the pool entirely (avoids slow retries)."""
    from ..persistence.health import supabase_ok
    return supabase_ok() is False


def load(course: str, *, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    if _use_local():
        from ..persistence import local
        m = local.load_course_memory(course, settings=settings)
        return m if m is not None else {k: [] for k in _EMPTY}
    try:
        with connection(settings) as conn:
            row = conn.execute(
                "select prior_concepts, mcq_topics, feedback, eval_history "
                "from course_memory where course = %s",
                (course,),
            ).fetchone()
        from ..persistence.health import mark_supabase
        mark_supabase(True)
    except Exception:  # noqa: BLE001 — Supabase down → local SQLite fallback
        from ..persistence.health import mark_supabase
        from ..persistence import local
        mark_supabase(False)
        local_mem = local.load_course_memory(course, settings=settings)
        return local_mem if local_mem is not None else {k: [] for k in _EMPTY}
    if not row:
        return {k: [] for k in _EMPTY}
    return {k: (row.get(k) or []) for k in _EMPTY}


def update(
    course: str,
    *,
    new_concepts: list[str] | None = None,
    new_mcq_topics: list[str] | None = None,
    feedback: list[str] | None = None,
    eval_score: float | None = None,
    session: str = "",
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    entry = load(course, settings=settings)

    def _extend_unique(target: list, items: list | None):
        for it in items or []:
            if it and it not in target:
                target.append(it)

    _extend_unique(entry["prior_concepts"], new_concepts)
    _extend_unique(entry["mcq_topics"], new_mcq_topics)
    _extend_unique(entry["feedback"], feedback)
    if eval_score is not None:
        entry["eval_history"].append({"session": session, "score": eval_score})

    if _use_local():
        from ..persistence import local
        local.save_course_memory(course, entry, settings=settings)
        return

    try:
        with connection(settings) as conn:
            conn.execute(
                """
                insert into course_memory
                    (course, prior_concepts, mcq_topics, feedback, eval_history, updated_at)
                values (%s, %s, %s, %s, %s, now())
                on conflict (course) do update set
                    prior_concepts = excluded.prior_concepts,
                    mcq_topics     = excluded.mcq_topics,
                    feedback       = excluded.feedback,
                    eval_history   = excluded.eval_history,
                    updated_at     = now()
                """,
                (course, Json(entry["prior_concepts"]), Json(entry["mcq_topics"]),
                 Json(entry["feedback"]), Json(entry["eval_history"])),
            )
        from ..persistence.health import mark_supabase
        mark_supabase(True)
    except Exception:  # noqa: BLE001 — Supabase down → persist to local SQLite instead
        from ..persistence.health import mark_supabase
        from ..persistence import local
        mark_supabase(False)
        local.save_course_memory(course, entry, settings=settings)
