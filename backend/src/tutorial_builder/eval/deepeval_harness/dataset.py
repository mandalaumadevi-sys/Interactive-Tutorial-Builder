"""Convert eval-set exemplars (and a finished tutorial) into DeepEval test cases.

Golden examples carry a ``context`` (the task framing + source material) and an ``output``
(what a good/bad agent produced). We map those onto ``LLMTestCase`` fields:

  • input             — the agent + task context (so GEval sees what was asked)
  • actual_output     — the example's ``output`` (the thing under judgement)
  • context           — the source material the output must respect (GEval CONTEXT param)
  • retrieval_context — same source, used by the Faithfulness RAG metric

Each test case is paired with the label it was drawn from (good → should pass, bad → should
fail) so the runner can score judge accuracy against ground truth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from deepeval.test_case import LLMTestCase

from ...config import Settings, get_settings
from ...utils.io import html_to_text, load_agent_evalset

# Keep judge prompts (and cost) bounded — outputs/tutorials can be very large.
_MAX_OUTPUT_CHARS = 12_000
_MAX_SOURCE_CHARS = 12_000
_MAX_E2E_OUTPUT_CHARS = 18_000


@dataclass
class GoldenCase:
    agent: str
    example_id: str
    label: str          # "good" | "bad"
    expected_pass: bool
    test_case: LLMTestCase


def _as_text(value, *, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)
    return text[:limit]


def _source_text(context) -> str:
    """Best available source material for a grounding/faithfulness check."""
    if isinstance(context, dict):
        for key in ("source_html", "relevant_paragraph", "source"):
            if context.get(key):
                return _as_text(context[key], limit=_MAX_SOURCE_CHARS)
        if context.get("source_h2_sections"):
            return _as_text({"source_h2_sections": context["source_h2_sections"]},
                            limit=_MAX_SOURCE_CHARS)
        return _as_text(context, limit=_MAX_SOURCE_CHARS) if context else ""
    return _as_text(context, limit=_MAX_SOURCE_CHARS) if context else ""


def _examples(blob) -> list[dict]:
    if isinstance(blob, dict):
        return [e for e in blob.get("examples", []) if isinstance(e, dict)]
    if isinstance(blob, list):
        return [e for e in blob if isinstance(e, dict)]
    return []


def _example_id(ex: dict, idx: int, agent: str, label: str) -> str:
    return str(ex.get("example_id") or ex.get("id") or f"{agent}_{label}_{idx:03d}")


def _build_case(agent: str, ex: dict) -> LLMTestCase:
    context = ex.get("context", {})
    output = ex.get("output", ex)
    source = _source_text(context) or "(no explicit source material in this example)"
    task = f"Agent under evaluation: {agent}\nTask context:\n" + _as_text(context, limit=4_000)
    return LLMTestCase(
        input=task,
        actual_output=_as_text(output, limit=_MAX_OUTPUT_CHARS),
        context=[source],
        retrieval_context=[source],
    )


def golden_cases(agent: str, *, settings: Settings | None = None,
                 limit: int | None = None) -> list[GoldenCase]:
    """All labelled good/bad exemplars for ``agent`` as DeepEval test cases."""
    settings = settings or get_settings()
    es = load_agent_evalset(agent, settings)
    cases: list[GoldenCase] = []
    for label, expect_pass in (("good", True), ("bad", False)):
        items = _examples(es.get(label))
        if limit:
            items = items[:limit]
        for idx, ex in enumerate(items, start=1):
            cases.append(GoldenCase(
                agent=agent,
                example_id=_example_id(ex, idx, agent, label),
                label=label,
                expected_pass=expect_pass,
                test_case=_build_case(agent, ex),
            ))
    return cases


def e2e_case(source_html: str, tutorial_html: str) -> LLMTestCase:
    """A test case scoring a finished tutorial against the source session it was built from."""
    source = html_to_text(source_html)[:_MAX_SOURCE_CHARS] or "(empty source)"
    tutorial = html_to_text(tutorial_html)[:_MAX_E2E_OUTPUT_CHARS] or "(empty tutorial)"
    return LLMTestCase(
        input="Final assembled interactive tutorial generated from the source session content.",
        actual_output=tutorial,
        context=[source],
        retrieval_context=[source],
    )


def e2e_case_from_run(run_dir: str | Path) -> tuple[LLMTestCase, str]:
    """Build an e2e test case from a ``runs/<id>/`` dir holding ``input.html`` + a ``*tutorial.html``.

    Returns ``(test_case, tutorial_filename)``. Raises ``FileNotFoundError`` if the pair is missing.
    """
    d = Path(run_dir)
    src = d / "input.html"
    tutorials = sorted(d.glob("*tutorial.html")) or sorted(d.glob("*.html"))
    tutorials = [t for t in tutorials if t.name != "input.html"]
    if not src.exists() or not tutorials:
        raise FileNotFoundError(
            f"{d} must contain input.html and a *tutorial.html (found src={src.exists()}, "
            f"tutorials={[t.name for t in tutorials]})"
        )
    tutorial = tutorials[0]
    return e2e_case(src.read_text(encoding="utf-8"),
                    tutorial.read_text(encoding="utf-8")), tutorial.name
