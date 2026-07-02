"""High-level LLM client used by every agent.

Routes to the offline mock when ``settings.use_mock`` (no key / TB_LLM_MODE=mock),
otherwise to the configured OpenRouter provider. Handles vision image attachment,
JSON extraction, and a small retry loop.
"""

from __future__ import annotations

from typing import Any

from ..config import Settings, get_settings
from . import mock
from .base import extract_json
from .providers import Provider, build_messages, build_provider


def _est_tokens(*texts: str) -> int:
    """Rough token estimate (~4 chars/token) for the offline mock, so the UI can still show a
    realistic token figure without a real provider's usage block."""
    chars = sum(len(t or "") for t in texts)
    return max(1, chars // 4)


class LLMClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._provider: Provider | None = None  # built lazily (real calls only)

    @property
    def provider(self) -> Provider:
        if self._provider is None:
            self._provider = build_provider(self.settings)
        return self._provider

    # ── public API ──────────────────────────────────────────────────────── #
    def complete_text(self, *, purpose: str, system: str, user: str, model: str,
                      image_urls: list[str] | None = None, meta: dict | None = None,
                      max_tokens: int = 8192) -> str:
        if self.settings.use_mock:
            out = mock.generate(purpose, meta)
            self._count_mock_call(_est_tokens(system, user, out))
            return out
        messages = build_messages(system, user, image_urls)
        return self.provider.chat(model=model, messages=messages,
                                  temperature=self.settings.temperature, max_tokens=max_tokens)

    def _count_mock_call(self, tokens: int = 0) -> None:
        """Count a mock 'call' (with an estimated token count) so the UI can show usage offline."""
        try:
            from .. import cost
            cost.record_call_cost(None, self.settings, tokens=tokens)
        except Exception:  # noqa: BLE001 — counting must never break a run
            pass

    def complete_json(self, *, purpose: str, system: str, user: str, model: str,
                      image_urls: list[str] | None = None, meta: dict | None = None,
                      retries: int = 2, max_tokens: int = 8192) -> Any:
        """Return parsed JSON (a dict, or a list when the prompt returns one)."""
        if self.settings.use_mock:
            out = mock.generate(purpose, meta)
            self._count_mock_call(_est_tokens(system, user, out))
            return extract_json(out)

        messages = build_messages(system, user, image_urls)
        last_err: Exception | None = None
        for _ in range(retries + 1):
            text = self.provider.chat(model=model, messages=messages,
                                      temperature=self.settings.temperature,
                                      json_mode=not image_urls, max_tokens=max_tokens)
            try:
                return extract_json(text)
            except Exception as err:  # noqa: BLE001 — retry malformed JSON
                last_err = err
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user",
                                 "content": "That was not valid JSON. Reply with ONLY one valid JSON object."})
        raise ValueError(f"LLM did not return valid JSON for purpose={purpose!r}: {last_err}")
