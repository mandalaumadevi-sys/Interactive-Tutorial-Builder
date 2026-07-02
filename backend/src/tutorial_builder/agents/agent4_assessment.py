"""Agent 4 — Final Session Assessment (descriptive Q&A).

Runs ONCE after all blocks are built. Produces a set of descriptive, open-ended questions
(default 5), each paired with a model answer, spanning the whole session. Rendered as the
concluding read-through carousel. Validated by deterministic rules only (no LLM judge — keeps
LLM usage lean) with one corrective retry.
"""

from __future__ import annotations

from ..config import Settings, get_settings
from ..llm.base import extract_json
from ..llm.client import LLMClient
from ..schemas import AssessmentQuestion, BlockResult
from ..skills import validate_assessment
from ..tools import validation_tools as vt
from ..tools.html_tools import html_to_text
from ..utils.io import read_agent_prompt


def _serialize(questions: list[AssessmentQuestion]) -> str:
    """Readable rendering of the descriptive Q&A set for the LLM rubric judge."""
    return "\n\n".join(
        f"Q{i} ({q.question_type}/{q.blooms_level}): {q.question}\nA: {q.answer}"
        for i, q in enumerate(questions, 1)
    )


def _parse(data) -> list[AssessmentQuestion]:
    """Accept either a bare JSON array or an object with a 'questions' list."""
    rows = data.get("questions") if isinstance(data, dict) else data
    rows = rows if isinstance(rows, list) else []
    out: list[AssessmentQuestion] = []
    for r in rows:
        if isinstance(r, dict) and str(r.get("question", "")).strip():
            qtype = str(r.get("question_type") or r.get("type") or "short").strip().lower()
            out.append(AssessmentQuestion(
                question=str(r.get("question", "")).strip(),
                answer=str(r.get("answer", "")).strip(),
                question_type="long" if qtype.startswith("long") else "short",
                blooms_level=str(r.get("blooms_level") or r.get("bloom_level") or "").strip(),
            ))
    return out


def run(
    blocks: list[BlockResult],
    *,
    session_name: str = "Session",
    learning_objectives: list[str] | None = None,
    mcq_topics_used: list[str] | None = None,
    count: int | None = None,
    client: LLMClient | None = None,
    settings: Settings | None = None,
    extra_notes: str = "",
) -> list[AssessmentQuestion]:
    settings = settings or get_settings()
    client = client or LLMClient(settings)
    n = count if count is not None else settings.final_assessment_count

    system = read_agent_prompt("assessment_descriptive_system", settings)
    combined = "\n\n".join(f"### {b.title}\n{html_to_text(b.content_html)}" for b in blocks)
    avoid = (f"\n\nThese sub-topics were already tested in per-block MCQ quizzes — prefer NEW "
             f"angles / cross-block synthesis: {', '.join(mcq_topics_used)}" if mcq_topics_used else "")
    objectives = learning_objectives or []
    user = (
        f"READING MATERIAL (full session: {session_name}):\n\n{combined}\n\n"
        f"SESSION LEARNING OBJECTIVES: {objectives}\n\n"
        f"Write exactly {n} descriptive assessment question(s), each with a model answer, that "
        f"assess understanding across the WHOLE session, following every rule and checkpoint above. "
        f"Return ONLY the JSON array.{avoid}"
    )
    if extra_notes:
        user += f"\n\nREVISION NOTES (address these):\n{extra_notes}"
    meta = {"block_id": "final", "title": session_name, "n": n}

    def generate(extra: str = "") -> list[AssessmentQuestion]:
        text = client.complete_text(purpose="assessment", system=system, user=user + extra,
                                    model=settings.assessment_model, meta=meta)
        try:
            data = extract_json(text)
        except Exception:  # noqa: BLE001 — malformed JSON → empty, caught by the validator
            data = []
        return _parse(data)

    questions = generate()

    # Layer 1 — deterministic rule checks (free) with one corrective retry.
    issues = validate_assessment(questions)
    if issues and not settings.use_mock:
        retry = generate("\n\nThe previous attempt had these problems:\n- " + "\n- ".join(issues)
                         + "\nRegenerate ALL questions fixing them. Return ONLY the JSON array.")
        if retry and len(validate_assessment(retry)) <= len(issues):
            questions = retry

    # Layer 2 — LLM rubric self-check against eval-sets/assessment (material alignment, Bloom's,
    # answer-not-revealed, depth match — the qualitative checkpoints rules can't verify).
    if questions and not settings.use_mock and settings.self_validate_retries > 0:
        verdict = vt.self_validate("assessment", _serialize(questions),
                                   context=f"SESSION: {session_name}", client=client, settings=settings)
        if not verdict.passed:
            fixes = "; ".join(d.improvement for d in verdict.dimensions if d.improvement) \
                or verdict.summary or "Improve material alignment, clarity, and answer quality."
            retry = generate("\n\nA reviewer scored the previous questions below the bar:\n"
                             f"{fixes}\nRegenerate ALL questions fixing this. Return ONLY the JSON array.")
            if retry and len(validate_assessment(retry)) <= len(validate_assessment(questions)):
                questions = retry
    return questions
