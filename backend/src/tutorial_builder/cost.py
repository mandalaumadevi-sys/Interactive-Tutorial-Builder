"""OpenRouter cost tracking — how much money THIS application spends on a shared key.

We can measure this app's spend exactly: OpenRouter returns the real USD cost of every
generation when we request it (``usage: {include: true}``), and we accumulate it into a small
JSON ledger. The key is shared with other apps, so *their* usage is only DERIVABLE — never
directly observable — via:

    others = (key_usage_now - baseline_key_usage) - (app_spend_now - app_spend_at_baseline)

The baseline (the key's total usage plus our own spend at that instant) is captured lazily the
first time ``cost_summary`` runs with a reachable key — i.e. at feature setup. Call ``GET
/api/cost`` once right after enabling the feature so the baseline is set before heavy use.
"""

from __future__ import annotations

import threading
import time

import httpx
from psycopg.types.json import Json

from .config import Settings, get_settings
from .persistence.db import connection
from .utils.logging import now_iso

_LOCK = threading.Lock()

# Live USD→INR rate, cached in-process so we don't refetch on every panel open.
_RATE_CACHE: dict = {"rate": None, "fetched_at": 0.0}
_RATE_TTL_SECONDS = 3600  # refresh at most hourly


def usd_to_inr_rate(settings: Settings | None = None) -> tuple[float, str]:
    """Return (rate, source). Source is 'live', 'live-cached', or 'fixed' (fallback).

    Fetches a live USD→INR rate from a free, keyless FX endpoint and caches it for an hour.
    Falls back to the last cached rate, then to the configured TB_USD_TO_INR if the network
    or the FX service is unavailable — so the panel always has a number to show.
    """
    settings = settings or get_settings()
    now = time.time()
    if _RATE_CACHE["rate"] is not None and (now - _RATE_CACHE["fetched_at"]) < _RATE_TTL_SECONDS:
        return _RATE_CACHE["rate"], "live-cached"
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get("https://open.er-api.com/v6/latest/USD")
            resp.raise_for_status()
            rate = float(((resp.json() or {}).get("rates") or {}).get("INR"))
            if rate > 0:
                _RATE_CACHE.update(rate=rate, fetched_at=now)
                return rate, "live"
    except Exception:  # noqa: BLE001 — FX down / offline → fall back
        pass
    if _RATE_CACHE["rate"] is not None:
        return _RATE_CACHE["rate"], "live-cached"
    return float(settings.usd_to_inr), "fixed"


def _load(settings: Settings) -> dict:
    """The single cost-ledger document — Supabase ``cost_ledger`` (id='global'), else local SQLite."""
    from .persistence.health import mark_supabase, supabase_ok
    if supabase_ok() is False:
        from .persistence import local
        return local.load_cost(settings=settings)
    try:
        with connection(settings) as conn:
            row = conn.execute("select data from cost_ledger where id = 'global'").fetchone()
        mark_supabase(True)
        return (row.get("data") if row else None) or {}
    except Exception:  # noqa: BLE001 — Supabase down → local SQLite
        mark_supabase(False)
        from .persistence import local
        return local.load_cost(settings=settings)


def _save(settings: Settings, data: dict) -> None:
    from .persistence.health import mark_supabase, supabase_ok
    if supabase_ok() is False:
        from .persistence import local
        local.save_cost(data, settings=settings)
        return
    try:
        with connection(settings) as conn:
            conn.execute(
                """
                insert into cost_ledger (id, data, updated_at) values ('global', %s, now())
                on conflict (id) do update set data = excluded.data, updated_at = now()
                """,
                (Json(data),),
            )
        mark_supabase(True)
    except Exception:  # noqa: BLE001 — Supabase down → local SQLite
        mark_supabase(False)
        from .persistence import local
        local.save_cost(data, settings=settings)


def current_calls(settings: Settings | None = None) -> int:
    """Total LLM calls recorded so far (used to compute a per-run delta). Never raises."""
    settings = settings or get_settings()
    try:
        with _LOCK:
            return int(_load(settings).get("calls", 0))
    except Exception:  # noqa: BLE001
        return 0


def current_tokens(settings: Settings | None = None) -> int:
    """Total tokens recorded so far (used to compute a per-run delta). Never raises."""
    settings = settings or get_settings()
    try:
        with _LOCK:
            return int(_load(settings).get("tokens_total", 0))
    except Exception:  # noqa: BLE001
        return 0


def record_call_cost(cost_usd: float | None, settings: Settings | None = None,
                     *, tokens: int = 0) -> None:
    """Add one generation's USD cost + token usage to this app's running totals. Thread-safe.

    Never raises — cost tracking must not be able to break a generation. ``tokens`` is the
    total tokens for the call (exact from the provider's usage, or estimated under the mock).
    """
    settings = settings or get_settings()
    try:
        with _LOCK:
            data = _load(settings)
            if cost_usd and cost_usd > 0:
                data["app_spend_usd"] = round(
                    float(data.get("app_spend_usd", 0.0)) + float(cost_usd), 8)
            else:
                data["calls_missing_cost"] = int(data.get("calls_missing_cost", 0)) + 1
            data["calls"] = int(data.get("calls", 0)) + 1
            if tokens and tokens > 0:
                data["tokens_total"] = int(data.get("tokens_total", 0)) + int(tokens)
            data.setdefault("first_recorded_at", now_iso())
            data["updated_at"] = now_iso()
            _save(settings, data)
    except Exception:  # noqa: BLE001 — best-effort accounting only
        pass


def fetch_key_usage(settings: Settings | None = None) -> dict | None:
    """Read the shared key's totals from OpenRouter. Returns None if no key / unreachable.

    ``usage`` is the key's total spend (all apps); ``remaining`` is the spendable credit left
    (key limit_remaining, falling back to account credits when the key has no own limit).
    """
    settings = settings or get_settings()
    # Mock mode or a non-OpenRouter provider (e.g. Gemini) → don't touch the OpenRouter key.
    if settings.use_mock or settings.is_gemini or not settings.has_api_key:
        return None
    base = settings.openrouter_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}"}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{base}/auth/key", headers=headers)
            resp.raise_for_status()
            data = (resp.json() or {}).get("data", {}) or {}
            usage = data.get("usage")
            limit = data.get("limit")
            remaining = data.get("limit_remaining")
            if remaining is None:  # pay-as-you-go key → derive from account credit balance
                try:
                    cr = client.get(f"{base}/credits", headers=headers)
                    if cr.status_code == 200:
                        cd = (cr.json() or {}).get("data", {}) or {}
                        total, used = cd.get("total_credits"), cd.get("total_usage")
                        if total is not None and used is not None:
                            remaining = round(float(total) - float(used), 8)
                except Exception:  # noqa: BLE001
                    pass
            return {"usage": usage, "limit": limit, "remaining": remaining}
    except Exception:  # noqa: BLE001 — endpoint down / network / auth → treat as unreachable
        return None


def cost_summary(settings: Settings | None = None) -> dict:
    """This app's spend, the shared key's usage/remaining, and the derived 'others' figure."""
    settings = settings or get_settings()
    key = fetch_key_usage(settings)  # network done outside the lock
    key_usage = key.get("usage") if key else None
    remaining = key.get("remaining") if key else None
    limit = key.get("limit") if key else None

    with _LOCK:
        data = _load(settings)
        app_spend = round(float(data.get("app_spend_usd", 0.0)), 6)
        baseline = data.get("baseline_key_usage_usd")
        app_at_baseline = float(data.get("app_spend_at_baseline_usd", 0.0))
        # Capture the baseline the first time the key is reachable (feature setup).
        if baseline is None and key_usage is not None:
            baseline = float(key_usage)
            app_at_baseline = app_spend
            data["baseline_key_usage_usd"] = baseline
            data["app_spend_at_baseline_usd"] = app_at_baseline
            data["baseline_set_at"] = now_iso()
            _save(settings, data)
        calls = int(data.get("calls", 0))

    others = None
    if key_usage is not None and baseline is not None:
        others = round(max(0.0, (float(key_usage) - float(baseline))
                           - (app_spend - app_at_baseline)), 6)

    rate, rate_source = usd_to_inr_rate(settings)

    def _inr(usd):  # USD → INR, null-safe
        return round(float(usd) * rate, 2) if usd is not None else None

    with _LOCK:
        tokens_total = int(_load(settings).get("tokens_total", 0))
    provider = "mock" if settings.use_mock else ("gemini" if settings.is_gemini else "openrouter")
    return {
        "currency": "USD",
        "provider": provider,                  # mock | gemini | openrouter
        "model": settings.agent1_model,        # the model in use this run
        "tokens_total": tokens_total,          # total tokens recorded (exact real / est. mock)
        "usd_to_inr": round(rate, 4),          # live rate used for the INR figures below
        "usd_to_inr_source": rate_source,      # 'live' | 'live-cached' | 'fixed' (fallback)
        "app_spend_usd": app_spend,            # all-time spend this app has recorded
        "app_spend_inr": _inr(app_spend),
        "key_usage_usd": key_usage,            # total spend on the shared key (everyone)
        "key_usage_inr": _inr(key_usage),
        "remaining_credit_usd": remaining,     # credit left on the key/account
        "remaining_credit_inr": _inr(remaining),
        "key_limit_usd": limit,                # key credit limit (null = pay-as-you-go)
        "others_usd": others,                  # derived: other apps' spend since baseline
        "others_inr": _inr(others),
        "baseline_key_usage_usd": baseline,    # key usage when tracking began
        "calls": calls,                        # number of LLM calls this app made
        "key_reachable": key is not None,      # False → couldn't read OpenRouter (no key/offline)
    }
