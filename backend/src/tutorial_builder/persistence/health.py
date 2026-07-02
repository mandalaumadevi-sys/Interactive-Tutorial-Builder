"""Persistence health — which backend is live (Supabase Postgres vs local SQLite fallback).

A module-level flag records the last observed Supabase reachability so other modules can route to
the fallback without each paying a slow connection timeout. ``probe_supabase`` does a fast, bounded
direct connection (not via the pool) for the /api/db-status endpoint.
"""

from __future__ import annotations

import threading

from ..config import Settings, get_settings

_LOCK = threading.Lock()
_SUPABASE_OK: bool | None = None  # None = not yet probed


def mark_supabase(ok: bool) -> None:
    global _SUPABASE_OK
    with _LOCK:
        _SUPABASE_OK = ok


def supabase_ok() -> bool | None:
    return _SUPABASE_OK


def probe_supabase(settings: Settings | None = None, *, timeout: float = 4.0) -> tuple[bool, str]:
    """Fast bounded probe of the configured Supabase URL. Returns (ok, human-readable detail)."""
    settings = settings or get_settings()
    url = settings.db_url
    if not url:
        mark_supabase(False)
        return False, "SUPABASE_DB_URL is not set"
    try:
        import psycopg

        with psycopg.connect(url, connect_timeout=int(timeout)) as conn:
            conn.execute("select 1")
        mark_supabase(True)
        return True, "connected"
    except Exception as err:  # noqa: BLE001
        mark_supabase(False)
        msg = str(err).splitlines()[0][:200] if str(err) else err.__class__.__name__
        return False, msg


def status(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    ok, detail = probe_supabase(settings)
    from .local import db_path

    return {
        "connected": ok,
        "backend": "supabase" if ok else "sqlite-fallback",
        "supabase_configured": bool(settings.db_url),
        "detail": detail,
        "local_db_path": str(db_path(settings)),
        "note": ("Supabase is live — runs, checkpoints, and feedback persist to Postgres."
                 if ok else
                 "Supabase unreachable — using the local SQLite fallback so runs and feedback "
                 "still persist on disk. Restore/resume the Supabase project to switch back "
                 "(no code change needed)."),
    }
