"""Supabase Postgres persistence — the single backend for all state (no SQLite/local).

Everything durable lives in Supabase Postgres, reached through one shared psycopg connection
pool built from ``SUPABASE_DB_URL``:
  • LangGraph checkpoints (graph state / HITL resume)  — ``checkpointer.build_checkpointer``
  • course memory, cost ledger, run metadata           — plain SQL via ``connection()``

Only true file artifacts (input decks, extracted images, draft/published HTML) stay on disk.
"""

from .db import connection, get_pool
from .checkpointer import build_checkpointer

__all__ = ["connection", "get_pool", "build_checkpointer"]
