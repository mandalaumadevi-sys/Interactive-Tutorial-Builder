"""Local SQLite persistence — the automatic fallback when Supabase Postgres is unreachable.

Mirrors the two app tables (``runs`` and ``course_memory``) and provides a connection for
LangGraph's ``SqliteSaver`` checkpointer. This keeps the app fully functional offline / when the
cloud project is paused: runs, checkpoints, and course memory (human feedback) all persist on disk
under ``<runs_dir>/local_store.sqlite``. When Supabase comes back, the Postgres path is used again.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from ..config import Settings, get_settings

_LOCK = threading.Lock()
_INIT: set[str] = set()


def db_path(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    p = settings.runs_path / "local_store.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _conn(settings: Settings | None = None) -> sqlite3.Connection:
    path = str(db_path(settings))
    conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    if path not in _INIT:
        with _LOCK:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, course_name TEXT, session_name TEXT,
                    status TEXT, created_at TEXT, updated_at TEXT, data TEXT
                );
                CREATE TABLE IF NOT EXISTS course_memory (
                    course TEXT PRIMARY KEY, prior_concepts TEXT, mcq_topics TEXT,
                    feedback TEXT, eval_history TEXT, updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS tutorials (
                    run_id TEXT PRIMARY KEY, course TEXT, session TEXT,
                    output_path TEXT, html TEXT, created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS cost_ledger (
                    id TEXT PRIMARY KEY, data TEXT, updated_at TEXT
                );
                """
            )
            conn.commit()
            _INIT.add(path)
    return conn


# ── runs ──────────────────────────────────────────────────────────────────── #
def save_run(info: dict, *, settings: Settings | None = None) -> None:
    with _conn(settings) as conn:
        conn.execute(
            """INSERT INTO runs (run_id, course_name, session_name, status, created_at, updated_at, data)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(run_id) DO UPDATE SET course_name=excluded.course_name,
                 session_name=excluded.session_name, status=excluded.status,
                 updated_at=excluded.updated_at, data=excluded.data""",
            (info.get("run_id"), info.get("course_name", ""), info.get("session_name", ""),
             info.get("status", ""), info.get("created_at", ""), info.get("updated_at", ""),
             json.dumps(info)),
        )
        conn.commit()


def load_runs(*, settings: Settings | None = None) -> list[dict]:
    with _conn(settings) as conn:
        rows = conn.execute("SELECT data FROM runs ORDER BY created_at DESC").fetchall()
    return [json.loads(r["data"]) for r in rows if r["data"]]


# ── course memory ────────────────────────────────────────────────────────── #
_MEM = ("prior_concepts", "mcq_topics", "feedback", "eval_history")


def load_course_memory(course: str, *, settings: Settings | None = None) -> dict | None:
    with _conn(settings) as conn:
        row = conn.execute(
            "SELECT prior_concepts, mcq_topics, feedback, eval_history FROM course_memory WHERE course=?",
            (course,),
        ).fetchone()
    if not row:
        return None
    return {k: json.loads(row[k]) if row[k] else [] for k in _MEM}


def save_course_memory(course: str, entry: dict, *, settings: Settings | None = None) -> None:
    with _conn(settings) as conn:
        conn.execute(
            """INSERT INTO course_memory (course, prior_concepts, mcq_topics, feedback, eval_history, updated_at)
               VALUES (?,?,?,?,?, datetime('now'))
               ON CONFLICT(course) DO UPDATE SET prior_concepts=excluded.prior_concepts,
                 mcq_topics=excluded.mcq_topics, feedback=excluded.feedback,
                 eval_history=excluded.eval_history, updated_at=excluded.updated_at""",
            (course, json.dumps(entry.get("prior_concepts", [])), json.dumps(entry.get("mcq_topics", [])),
             json.dumps(entry.get("feedback", [])), json.dumps(entry.get("eval_history", []))),
        )
        conn.commit()


def load_cost(*, settings: Settings | None = None) -> dict:
    with _conn(settings) as conn:
        row = conn.execute("SELECT data FROM cost_ledger WHERE id='global'").fetchone()
    return (json.loads(row["data"]) if row and row["data"] else {})


def save_cost(data: dict, *, settings: Settings | None = None) -> None:
    with _conn(settings) as conn:
        conn.execute(
            """INSERT INTO cost_ledger (id, data, updated_at) VALUES ('global', ?, datetime('now'))
               ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at""",
            (json.dumps(data),),
        )
        conn.commit()


def save_tutorial(run_id: str, course: str, session: str, output_path: str, html: str,
                  *, settings: Settings | None = None) -> None:
    with _conn(settings) as conn:
        conn.execute(
            """INSERT INTO tutorials (run_id, course, session, output_path, html, created_at)
               VALUES (?,?,?,?,?, datetime('now'))
               ON CONFLICT(run_id) DO UPDATE SET course=excluded.course, session=excluded.session,
                 output_path=excluded.output_path, html=excluded.html""",
            (run_id, course, session, output_path, html),
        )
        conn.commit()


def checkpointer_connection(settings: Settings | None = None) -> sqlite3.Connection:
    """A dedicated multithread-safe connection for langgraph's SqliteSaver."""
    conn = sqlite3.connect(str(db_path(settings)), check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
