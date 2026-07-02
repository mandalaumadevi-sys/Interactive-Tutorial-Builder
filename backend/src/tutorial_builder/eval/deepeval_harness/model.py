"""A DeepEval judge model backed by the project's own OpenRouter client.

DeepEval defaults to OpenAI; this project talks to OpenRouter (OpenAI-compatible) through
``LLMClient``. ``OpenRouterDeepEvalModel`` adapts the existing client to DeepEval's
``DeepEvalBaseLLM`` interface so every metric is judged by the configured ``judge_model``
with no extra API key and no data leaving for a third-party eval cloud.

DeepEval 4.x calls ``generate(prompt)`` for free-text and ``generate(prompt, schema=Model)``
when it needs structured output (the GEval score+reason object, claim extraction, etc.). We
honour both: the schema path asks the LLM for JSON, parses it via the existing
``complete_json`` (which already retries malformed JSON), then validates it into the pydantic
schema DeepEval handed us — retrying once if validation fails.
"""

from __future__ import annotations

import json
from typing import Any

from deepeval.models.base_model import DeepEvalBaseLLM

from ...config import Settings, get_settings
from ...llm.base import as_object
from ...llm.client import LLMClient

_JSON_SYSTEM = (
    "You are a precise, strict evaluation engine. Follow the instructions exactly and "
    "respond with ONLY a single valid JSON object — no prose, no markdown fences."
)
_TEXT_SYSTEM = "You are a precise, strict evaluation engine. Follow the instructions exactly."


class OpenRouterDeepEvalModel(DeepEvalBaseLLM):
    """Adapter exposing ``LLMClient`` (OpenRouter) as a DeepEval judge model."""

    def __init__(self, settings: Settings | None = None, model: str | None = None,
                 client: LLMClient | None = None):
        self.settings = settings or get_settings()
        self._model_name = model or self.settings.judge_model
        self.client = client or LLMClient(self.settings)
        super().__init__(self._model_name)

    # ── DeepEvalBaseLLM interface ───────────────────────────────────────── #
    def load_model(self):
        return self.client

    def get_model_name(self) -> str:
        return f"openrouter:{self._model_name}"

    # Tell DeepEval we can take a pydantic schema, so it uses the structured path.
    def supports_json_mode(self) -> bool:  # noqa: D401
        return True

    def generate(self, prompt: str, schema: Any | None = None, **_: Any) -> Any:
        if schema is not None:
            return self._generate_schema(prompt, schema)
        return self.client.complete_text(
            purpose="deepeval", system=_TEXT_SYSTEM, user=prompt, model=self._model_name,
        )

    async def a_generate(self, prompt: str, schema: Any | None = None, **_: Any) -> Any:
        # The underlying client is synchronous; metrics run with async_mode=False so this is
        # only reached if DeepEval forces an async path. Keep it correct, not concurrent.
        return self.generate(prompt, schema=schema)

    # ── internals ───────────────────────────────────────────────────────── #
    def _generate_schema(self, prompt: str, schema: Any) -> Any:
        instruction = (
            f"{prompt}\n\nReturn ONLY a JSON object conforming to this JSON schema:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
        last_err: Exception | None = None
        for _ in range(2):
            data = as_object(self.client.complete_json(
                purpose="deepeval", system=_JSON_SYSTEM, user=instruction,
                model=self._model_name,
            ))
            try:
                return schema.model_validate(data)
            except Exception as err:  # noqa: BLE001 — coerce / retry on schema mismatch
                last_err = err
                instruction = (
                    f"{prompt}\n\nYour previous reply did not match the schema "
                    f"({err}). Return ONLY a JSON object conforming exactly to:\n"
                    f"{json.dumps(schema.model_json_schema())}"
                )
        raise ValueError(f"DeepEval judge could not produce schema {schema.__name__}: {last_err}")
