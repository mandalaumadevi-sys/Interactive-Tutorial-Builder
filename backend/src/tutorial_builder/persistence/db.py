"""The shared Supabase Postgres connection pool.

A single psycopg ``ConnectionPool`` (lazily opened) is the one way every module reaches the
database. Connections are configured for LangGraph's PostgresSaver and for Supabase's poolers:
``autocommit=True`` + ``prepare_threshold=0`` (so the transaction pooler also works) and
``row_factory=dict_row`` (rows come back as dicts; jsonb columns load as Python objects).
"""

from __future__ import annotations

import threading

from ..config import Settings, get_settings

_POOL = None
_LOCK = threading.Lock()


def _require_url(settings: Settings) -> str:
    url = settings.db_url
    if not url:
        raise RuntimeError(
            "SUPABASE_DB_URL is not set. This build uses Supabase Postgres for ALL persistence "
            "(no SQLite / local fallback). Add it to backend/.env:\n"
            "  SUPABASE_DB_URL=postgresql://postgres.<ref>:<password>@<host>:5432/postgres\n"
            "Get it from Supabase → Project Settings → Database → Connection string → URI "
            "(Session pooler or Direct connection)."
        )
    return url


def get_pool(settings: Settings | None = None):
    """Return the process-wide connection pool, opening it on first use."""
    global _POOL
    settings = settings or get_settings()
    if _POOL is None:
        with _LOCK:
            if _POOL is None:
                from psycopg.rows import dict_row
                from psycopg_pool import ConnectionPool

                pool = ConnectionPool(
                    conninfo=_require_url(settings),
                    min_size=1,
                    max_size=settings.db_pool_max,
                    open=False,
                    # connect_timeout bounds each connection attempt so a dead/paused Supabase
                    # surfaces in seconds instead of hanging ~30s.
                    kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row,
                            "connect_timeout": 8},
                    # Supabase's pooler closes idle connections; check (and recycle) each one
                    # before handing it out so we never block on a half-dead socket. Recycle
                    # idle/old connections proactively too.
                    check=ConnectionPool.check_connection,
                    max_idle=45.0,
                    max_lifetime=600.0,
                )
                pool.open(wait=True, timeout=10)
                _POOL = pool
    return _POOL


def connection(settings: Settings | None = None):
    """Borrow a pooled connection as a context manager: ``with connection() as conn: ...``.

    A 10s acquisition timeout guarantees a caller can never block indefinitely on the pool
    (e.g. if every connection is briefly being health-checked/recycled)."""
    return get_pool(settings).connection(timeout=10.0)
