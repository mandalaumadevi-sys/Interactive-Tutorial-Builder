"""LLM provider adapters. Default = OpenRouter (OpenAI-compatible Chat Completions API)."""

from __future__ import annotations

import re
import time
from typing import Protocol

from ..config import Settings
from .base import encode_image_data_url

_MAX_429_RETRIES = 4          # transient rate-limit retries before giving up
_MAX_BACKOFF_SECONDS = 35.0   # cap a single wait (provider may suggest e.g. "retry in 25s")


def _retry_delay_seconds(msg: str, attempt: int) -> float:
    """How long to wait before retrying a 429. Honour the provider's suggested delay if present
    (e.g. "retryDelay': '25s'" / "retry in 25.7s"), else exponential backoff. Capped."""
    m = re.search(r"retry(?:Delay)?['\"]?\s*[:in]+\s*['\"]?(\d+(?:\.\d+)?)s", msg, re.IGNORECASE)
    suggested = float(m.group(1)) + 1.0 if m else (2.0 ** attempt)
    return min(_MAX_BACKOFF_SECONDS, max(2.0, suggested))


def build_messages(system: str, user: str, image_paths: list[str] | None) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": system}]
    if image_paths:
        content: list[dict] = [{"type": "text", "text": user}]
        for path in image_paths:
            url = path if path.startswith(("http", "data:")) else encode_image_data_url(path)
            content.append({"type": "image_url", "image_url": {"url": url}})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": user})
    return messages


class Provider(Protocol):
    def chat(self, *, model: str, messages: list[dict], temperature: float,
             json_mode: bool = False, max_tokens: int = 8192) -> str:
        ...


def _with_prompt_cache(messages: list[dict], model: str) -> list[dict]:
    """Mark the stable system prompt with an Anthropic ``cache_control`` breakpoint so the
    large shared prefix is cached across calls. Only applies to Claude/Anthropic models —
    OpenAI-family models on OpenRouter cache automatically and ignore the field.

    The system content is converted to OpenRouter's content-parts form; openai-python sends
    message dicts verbatim, so the extra ``cache_control`` key passes through to Anthropic.
    """
    low = (model or "").lower()
    if "claude" not in low and "anthropic" not in low:
        return messages
    out, marked = [], False
    for m in messages:
        if not marked and m.get("role") == "system" and isinstance(m.get("content"), str):
            out.append({"role": "system", "content": [
                {"type": "text", "text": m["content"], "cache_control": {"type": "ephemeral"}}]})
            marked = True
        else:
            out.append(m)
    return out


def _extract_tokens(resp) -> int:
    """Total tokens for a generation from the provider's usage block (0 if absent)."""
    try:
        usage = getattr(resp, "usage", None)
        if usage is None:
            return 0
        total = getattr(usage, "total_tokens", None)
        if total is None:
            pt = getattr(usage, "prompt_tokens", 0) or 0
            ct = getattr(usage, "completion_tokens", 0) or 0
            total = pt + ct
        return int(total or 0)
    except Exception:  # noqa: BLE001
        return 0


def _extract_cost(resp) -> float | None:
    """Pull the per-generation USD cost OpenRouter returns in usage (usage.include=true)."""
    try:
        usage = getattr(resp, "usage", None)
        if usage is None:
            return None
        cost = getattr(usage, "cost", None)
        if cost is None:
            extra = getattr(usage, "model_extra", None) or {}
            cost = extra.get("cost")
        return float(cost) if cost is not None else None
    except Exception:  # noqa: BLE001
        return None


class OpenAICompatibleProvider:
    """Works for OpenRouter and OpenAI — only base_url / key / headers differ."""

    def __init__(self, *, api_key: str, base_url: str, default_headers: dict | None = None,
                 settings: Settings | None = None):
        from openai import OpenAI  # imported lazily so the package imports without the dep

        if not api_key:
            raise RuntimeError(
                "No LLM API key configured. Set OPENROUTER_API_KEY in NEW PROJECT/.env, "
                "or set TB_LLM_MODE=mock for an offline run."
            )
        self._settings = settings
        # Bound every request and disable the SDK's own retries (we do 429 backoff ourselves),
        # so a slow/hanging provider call can never stall a run indefinitely.
        timeout = getattr(settings, "llm_timeout", 90.0) if settings else 90.0
        self._client = OpenAI(api_key=api_key, base_url=base_url,
                              default_headers=default_headers or {},
                              timeout=timeout, max_retries=0)

    def chat(self, *, model: str, messages: list[dict], temperature: float,
             json_mode: bool = False, max_tokens: int = 8192) -> str:
        base = getattr(self._settings, "active_base_url", "") if self._settings else ""
        is_openrouter = "openrouter" in (base or "")
        if is_openrouter and (self._settings is None or getattr(self._settings, "prompt_cache", True)):
            messages = _with_prompt_cache(messages, model)
        kwargs: dict = {"model": model, "messages": messages,
                        "temperature": temperature, "max_tokens": max_tokens}
        # The usage-cost echo is an OpenRouter extension; other providers reject unknown fields.
        if is_openrouter:
            kwargs["extra_body"] = {"usage": {"include": True}}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        # Retry transient rate limits (429) with backoff — free-tier Gemini has tight per-minute
        # limits, so a multi-call build would otherwise fail partway. Bounded so we never loop forever.
        attempt = 0
        while True:
            try:
                resp = self._client.chat.completions.create(**kwargs)
                break
            except Exception as err:  # noqa: BLE001 — translate provider errors to clear guidance
                msg = str(err)
                low = msg.lower()
                is_429 = "429" in msg or "resource_exhausted" in low or "rate limit" in low
                # Only retry rate limits that aren't a hard "limit: 0" (no quota at all for this model).
                if is_429 and "limit: 0" not in msg and attempt < _MAX_429_RETRIES:
                    attempt += 1
                    time.sleep(_retry_delay_seconds(msg, attempt))
                    continue
                if "401" in msg or "user not found" in low or "no auth" in low or "invalid api key" in low:
                    raise RuntimeError(
                        "API key rejected (401). Set a VALID key in .env and restart the server."
                    ) from err
                if "402" in msg or "insufficient" in low or "credit" in low:
                    raise RuntimeError("Account is out of credit (402). Add credit / enable billing.") from err
                if is_429 and "limit: 0" in msg:
                    raise RuntimeError(
                        f"Model '{model}' has no quota on this key (free-tier limit 0). Pick a model "
                        f"with quota (e.g. set TB_GEMINI_MODEL=gemini-2.5-flash) or enable billing. "
                        f"[{msg[:160]}]") from err
                raise RuntimeError(f"LLM call failed: {msg}") from err
        # Record this app's spend + token usage (best-effort; never breaks the generation).
        from .. import cost as cost_tracker
        cost_tracker.record_call_cost(_extract_cost(resp), self._settings,
                                      tokens=_extract_tokens(resp))
        return resp.choices[0].message.content or ""


def build_provider(settings: Settings) -> Provider:
    # OpenRouter wants attribution headers; Gemini ignores them harmlessly.
    headers = {
        "HTTP-Referer": settings.openrouter_http_referer,
        "X-Title": settings.openrouter_app_title,
    }
    return OpenAICompatibleProvider(
        api_key=settings.active_api_key,
        base_url=settings.active_base_url,
        default_headers=headers,
        settings=settings,
    )
