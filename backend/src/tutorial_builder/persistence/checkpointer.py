"""LangGraph checkpointer backed by Supabase Postgres.

Replaces the old SQLite ``SqliteSaver``. The PostgresSaver borrows connections from the shared
pool, so graph state (and both HITL interrupts) persist in Supabase and survive a server restart.
``setup()`` is idempotent (CREATE TABLE IF NOT EXISTS for the checkpoint tables) and runs once.
"""

from __future__ import annotations

import threading

from ..config import Settings
from .db import get_pool

_SETUP_DONE = False
_SETUP_LOCK = threading.Lock()


def build_checkpointer(settings: Settings | None = None):
    """Return a PostgresSaver on the shared pool, creating its tables on first call.

    Falls back to an in-memory saver when Postgres is not configured/reachable (offline dev,
    tests, or a missing Supabase tenant) so the graph still runs end-to-end — without
    cross-restart persistence. The fallback is logged once, never silent in production logs.
    """
    global _SETUP_DONE
    from langgraph.checkpoint.postgres import PostgresSaver

    from .health import mark_supabase

    try:
        saver = PostgresSaver(get_pool(settings))
        if not _SETUP_DONE:
            with _SETUP_LOCK:
                if not _SETUP_DONE:
                    saver.setup()
                    _SETUP_DONE = True
        mark_supabase(True)
        return saver
    except Exception as err:  # noqa: BLE001 — unreachable/unconfigured DB → local SQLite fallback
        import logging

        mark_supabase(False)
        logging.getLogger(__name__).warning(
            "Postgres checkpointer unavailable (%s); falling back to the local SQLite checkpointer "
            "at <runs_dir>/local_store.sqlite (runs DO persist locally). Restore the Supabase "
            "project to switch back — no code change needed.",
            err.__class__.__name__,
        )
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver

            from .local import checkpointer_connection
            saver = SqliteSaver(checkpointer_connection(settings))
            saver.setup()
            return saver
        except Exception:  # noqa: BLE001 — last resort: in-memory (no persistence)
            from langgraph.checkpoint.memory import MemorySaver
            logging.getLogger(__name__).warning(
                "SQLite checkpointer also unavailable; using in-memory (no persistence).")
            return MemorySaver()
