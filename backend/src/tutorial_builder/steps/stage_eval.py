"""Per-stage advisory evaluation surfaced at each human gate.

Each producing stage (content → animation → MCQ) is scored against its eval-set so the human
reviewer sees concrete metrics + an overall score when deciding to accept or refine. This is
advisory: the human is the control. The session-level self-refine loop (``final_quality_check``)
is unchanged — it still auto-refines once, then escalates to the final human gate with its metrics.

Returns a plain dict (JSON-round-trippable, stored in ``state['eval_scores'][stage]``):
    {"score": float, "passed": bool, "summary": str, "dimensions": [DimensionScore, ...]}
Under the offline mock the underlying judge returns canned passing scores, so gates still render.
"""

from __future__ import annotations

from ..config import Settings, get_settings
from ..llm.client import LLMClient
from ..schemas import MCQ, BlockResult, SelfValidation
from ..tools import validation_tools as vt
from ..tools.html_tools import html_to_text


def _pack(v: SelfValidation) -> dict:
    return {
        "score": v.weighted_score,
        "passed": v.passed,
        "summary": v.summary,
        "dimensions": [d.model_dump() for d in v.dimensions],
    }


def evaluate_content(blocks: list[BlockResult], *, source_blocks=None,
                     client: LLMClient | None = None, settings: Settings | None = None) -> dict:
    if not blocks:
        return {"score": 0.0, "passed": False, "summary": "No content generated.", "dimensions": []}
    # Judge the RAW house-style HTML (NOT stripped text) so 'html_structure' can actually be scored,
    # and give every block enough room so the blob isn't truncated (the cause of unfairly low scores).
    n = len(blocks)
    budget = max(1200, 13000 // n)
    blob = "\n\n".join(f"### {b.title}\n{(b.content_html or '')[:budget]}" for b in blocks)
    ctx = ("Whole-session content review. The OUTPUT is the rendered house-style HTML for each block "
           "(judge 'html_structure' on this real HTML — .main-content wrapper + house-style classes).")
    if source_blocks:
        src = "\n\n".join(f"### {getattr(b, 'title', '')}\n{html_to_text(getattr(b, 'content_html', '') or '')[:1500]}"
                          for b in source_blocks)
        ctx += (" Score 'accuracy' by checking the OUTPUT against the SOURCE below — anything in the "
                "output not grounded in this source means a LOW accuracy score. For "
                "'analogy_example_quality': if the SOURCE contains no analogy, the correct output adds "
                f"none and scores 10 — never penalise the absence of an analogy.\n\nSOURCE MATERIAL:\n{src[:7000]}")
    return _pack(vt.self_validate("content", blob, context=ctx, client=client, settings=settings,
                                  max_output_chars=16000))


def evaluate_animation(blocks: list[BlockResult], *, client: LLMClient | None = None,
                       settings: Settings | None = None) -> dict:
    anims = [a for b in blocks for a in b.animations]
    if not anims:
        return {"score": 10.0, "passed": True,
                "summary": "No concept diagrams required animation in this session.",
                "dimensions": []}
    blob = "\n\n".join(a.html[:1500] for a in anims)
    return _pack(vt.self_validate("visual", blob, context="Session animations",
                                  client=client, settings=settings))


def evaluate_mcq(mcqs: dict[int, list[MCQ]], *, client: LLMClient | None = None,
                 settings: Settings | None = None) -> dict:
    parts = [f"Q: {m.question} | correct={m.correct_indexes} | {m.explanation}"
             for qs in mcqs.values() for m in qs]
    if not parts:
        return {"score": 0.0, "passed": False, "summary": "No MCQs generated.", "dimensions": []}
    return _pack(vt.self_validate("mcq", "\n".join(parts), context="All per-block MCQs",
                                  client=client, settings=settings))
