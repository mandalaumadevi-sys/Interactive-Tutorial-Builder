"""Deterministic MCQ format/quality checks against the MCQ prompt's rules.

Returns a list of human-readable issues; an empty list means the set passes. The MCQ
agent uses this to decide whether to make one corrective attempt.
"""

from __future__ import annotations

from ..schemas import MCQ


def validate(mcqs: list[MCQ]) -> list[str]:
    issues: list[str] = []
    seen_keys: set[str] = set()

    if not mcqs:
        return ["no questions were parsed from the model output"]

    for i, m in enumerate(mcqs, start=1):
        tag = f"Q{i}"
        if not (m.question or "").strip():
            issues.append(f"{tag}: empty question text")
        if len(m.options) != 4:
            issues.append(f"{tag}: expected exactly 4 options, found {len(m.options)}")
        if any(o.strip().endswith(".") for o in m.options):
            issues.append(f"{tag}: options must not end with a period")
        # options must be distinct (a repeated option is always a defect)
        norm = [o.strip().lower() for o in m.options if o.strip()]
        if len(set(norm)) != len(norm):
            issues.append(f"{tag}: options are not all distinct")
        lengths = [len(o) for o in m.options if o]
        if lengths and max(lengths) > 2.5 * max(1, min(lengths)):
            issues.append(f"{tag}: option lengths are unbalanced (longest ≫ shortest)")
        if m.multi and len(m.correct_indexes) < 2:
            issues.append(f"{tag}: multi-answer type but fewer than 2 correct options")
        if not m.multi and len(m.correct_indexes) != 1:
            issues.append(f"{tag}: single-answer type must have exactly 1 correct option")
        if not (m.explanation or "").strip():
            issues.append(f"{tag}: missing explanation")
        # checkpoint (deterministic subset): the answer must not be revealed verbatim in the stem
        q_low = (m.question or "").lower()
        for ci in m.correct_indexes:
            if 0 <= ci < len(m.options):
                opt = m.options[ci].strip().lower()
                if len(opt) >= 8 and opt in q_low:
                    issues.append(f"{tag}: correct option appears verbatim in the question (answer revealed)")
                    break
        key = m.meta.get("question_key", "")
        if key and key in seen_keys:
            issues.append(f"{tag}: duplicate QUESTION_KEY '{key}'")
        seen_keys.add(key)
    return issues
