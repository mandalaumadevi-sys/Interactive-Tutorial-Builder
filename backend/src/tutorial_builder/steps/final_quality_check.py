"""Final Quality Check (LLM judge) — session-level evaluation across all blocks + assessment.

Scores cross-block dimensions that individual agents cannot judge about themselves (learning flow,
objective coverage, depth consistency, MCQ variety, assessment synthesis). Drives the bounded
self-refine loop: below threshold → refine the responsible stage once → escalate to HITL #2.
"""

from __future__ import annotations

import json

from ..config import Settings, get_settings
from ..llm.base import as_object
from ..llm.client import LLMClient
from ..schemas import MCQ, AssessmentQuestion, BlockResult, DimensionScore, FinalQualityReport
from ..tools.html_tools import html_to_text
from ..utils.io import dimension_id, load_agent_evalset, read_agent_prompt


def run(
    blocks: list[BlockResult],
    mcqs: dict[int, list[MCQ]],
    final_assessment: list[AssessmentQuestion],
    *,
    session_name: str = "Session",
    learning_objectives: list[str] | None = None,
    client: LLMClient | None = None,
    settings: Settings | None = None,
) -> FinalQualityReport:
    settings = settings or get_settings()
    client = client or LLMClient(settings)
    es = load_agent_evalset("final_quality", settings)
    rubric = es.get("rubric") or {"pass_threshold": settings.pass_threshold, "dimensions": []}
    threshold = float(rubric.get("pass_threshold", settings.pass_threshold))
    dim_ids = [dimension_id(d) for d in rubric.get("dimensions", [])]

    session_blob = _session_blob(blocks, mcqs, final_assessment)
    system = read_agent_prompt("final_quality_check", settings)
    user = (
        f"SESSION: {session_name}\n"
        f"LEARNING OBJECTIVES: {json.dumps(learning_objectives or [])}\n\n"
        f"RUBRIC:\n{json.dumps(rubric, indent=2)}\n\n"
        f"GOOD EXAMPLES:\n{json.dumps(es.get('good', []))}\n\n"
        f"BAD EXAMPLES:\n{json.dumps(es.get('bad', []))}\n\n"
        f"SESSION OUTPUT TO REVIEW:\n{session_blob[:12000]}"
    )
    data = as_object(client.complete_json(
        purpose="final_quality", system=system, user=user,
        model=settings.eval_model, meta={"agent": "final_quality", "dimensions": dim_ids},
    ))

    dims = [
        DimensionScore(
            dimension=d.get("dimension", "?"),
            weight=float(d.get("weight", 0.0)),
            score=float(d.get("score", 0.0)),
            passed=float(d.get("score", 0.0)) >= threshold,
            reason=d.get("reasoning", "") or d.get("reason", ""),
            improvement=d.get("improvement_instruction", "") or d.get("improvement", ""),
        )
        for d in data.get("dimensions", [])
    ]
    overall = bool(dims) and all(d.passed for d in dims)
    if "overall_passed" in data:
        overall = bool(data["overall_passed"]) and overall
    return FinalQualityReport(dimensions=dims, overall_passed=overall,
                              summary=data.get("summary", ""))


def _session_blob(blocks: list[BlockResult], mcqs: dict[int, list[MCQ]],
                  final_assessment: list[AssessmentQuestion]) -> str:
    parts: list[str] = []
    for b in blocks:
        parts.append(f"### BLOCK {b.block_id}: {b.title}\n{html_to_text(b.content_html)[:1500]}")
        qs = mcqs.get(b.block_id, [])
        for m in qs:
            parts.append(f"  MCQ: {m.question} | type={'multi' if m.multi else 'single'} "
                         f"| outcome={m.meta.get('learning_outcome', '')}")
    if final_assessment:
        parts.append("### FINAL ASSESSMENT (descriptive Q&A)")
        for q in final_assessment:
            parts.append(f"  Q: {q.question}\n  A: {q.answer}")
    return "\n".join(parts)
