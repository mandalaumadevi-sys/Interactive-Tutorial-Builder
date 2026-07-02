"""Deterministic checks for the descriptive (open-ended) session assessment.

No LLM — these are the format/structure checkpoints that can be verified by rule, so the
LLM is reserved for the qualitative checkpoints (syllabus alignment, Bloom's level, clarity,
technical accuracy). Returns a list of human-readable issues; empty means the set passes.
"""

from __future__ import annotations

import re

from ..schemas import AssessmentQuestion

_MIN_Q_CHARS = 15
_MIN_A_CHARS = 25
_SHORT_MAX_SENTENCES = 6     # short answers stay concise (a definition, optionally a small list)
_LONG_PARA_LIMIT = 320       # a long answer past this with no structure reads as a wall of text
_BULLET_RE = re.compile(r"(^|\n)\s*([-*•]|\d+[.)])\s+")                      # bullet / numbered list
# a "Capabilities:" / "**Examples:**" / "When to use:" style labelled line
_LABEL_RE = re.compile(r"(^|\n)\s*\*{0,2}[A-Z][A-Za-z0-9 /&'-]{1,40}:\*{0,2}")


def _sentence_count(text: str) -> int:
    return len([s for s in re.split(r"[.!?]+", text) if s.strip()])


def _is_structured(text: str) -> bool:
    """Structured = has a bullet/numbered list, a labelled line, or a paragraph break."""
    return bool(_BULLET_RE.search(text) or _LABEL_RE.search(text) or "\n\n" in text)


def validate_assessment(questions: list[AssessmentQuestion]) -> list[str]:
    issues: list[str] = []
    if not questions:
        return ["no descriptive assessment questions were produced"]

    seen: set[str] = set()
    for i, q in enumerate(questions, start=1):
        tag = f"AQ{i}"
        question = (q.question or "").strip()
        answer = (q.answer or "").strip()

        if not question:
            issues.append(f"{tag}: empty question")
        else:
            # Questions may be imperative ("Define…", "Compare…") or interrogative — both valid
            # per the spec, so we only require a clear, long-enough prompt (not a trailing '?').
            if len(question) < _MIN_Q_CHARS:
                issues.append(f"{tag}: question is too short to be a clear prompt")
            key = question.lower()
            if key in seen:
                issues.append(f"{tag}: duplicate question")
            seen.add(key)

        if not answer:
            issues.append(f"{tag}: missing model answer")
        elif len(answer) < _MIN_A_CHARS:
            issues.append(f"{tag}: model answer is too short to be useful")

        if question and answer and question.lower() == answer.lower():
            issues.append(f"{tag}: answer merely repeats the question")

        # Rule 7: structure mirrors content. Long answers must be structured (labelled lists /
        # bullets); short answers stay concise (don't cram a long answer into the short format).
        if answer:
            if (q.question_type or "short").lower() == "long":
                if len(answer) > _LONG_PARA_LIMIT and not _is_structured(answer):
                    issues.append(f"{tag}: long answer is one unstructured paragraph — break it into "
                                  f"a lead line + labelled bullet lists (e.g. **Capabilities:**, **Examples:**)")
            elif _sentence_count(answer) > _SHORT_MAX_SENTENCES:
                issues.append(f"{tag}: short answer is too long — keep it to a few sentences "
                              f"(a definition, optionally a small bullet list)")
    return issues
