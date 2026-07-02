"""LLM access layer (OpenRouter, OpenAI-compatible) with an offline mock fallback."""

from __future__ import annotations

from ..config import get_settings
from .client import LLMClient


def get_client() -> LLMClient:
    """Factory: a single high-level client; it self-routes to mock when configured / no key."""
    return LLMClient(get_settings())


__all__ = ["get_client", "LLMClient"]
