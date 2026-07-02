"""Deterministic parser — Agent 3's ``-END-`` block format → list[MCQ] (QUIZ_DATA shape).

Maps the fixed MCQ-prompt output (``prompts/MCQ_generator_prompt.md``) to the shell's schema:
  OPTION_1..6    → options[]
  CORRECT_OPTION → correct_indexes[] (0-based)
  QUESTION_TYPE  → multi (MORE_THAN_ONE_MULTIPLE_CHOICE → True)
  EXPLANATION    → explanation
  CODE (≠ NA)    → code (rendered as <pre><code>)
  QUESTION_KEY / BLOOM_LEVEL / LEARNING_OUTCOME / TOPIC / SUB_TOPIC → meta
"""

from __future__ import annotations

import re

from ..schemas import MCQ

_KEYS = {
    "TOPIC", "SUB_TOPIC", "CONCEPT", "QUESTION_KEY", "BASE_QUESTION_KEYS", "QUESTION_TEXT",
    "CONTENT_TYPE", "QUESTION_TYPE", "LEARNING_OUTCOME", "CODE", "CODE_LANGUAGE",
    "OPTION_1", "OPTION_2", "OPTION_3", "OPTION_4", "OPTION_5", "OPTION_6",
    "CORRECT_OPTION", "EXPLANATION", "BLOOM_LEVEL",
}
_KEY_RE = re.compile(r"^([A-Z_0-9]+):\s?(.*)$")
_OPTION_RE = re.compile(r"OPTION_(\d+)")


def _split_blocks(text: str) -> list[str]:
    blocks, cur = [], []
    for line in (text or "").splitlines():
        if line.strip() == "-END-":
            if cur:
                blocks.append("\n".join(cur))
                cur = []
        else:
            cur.append(line)
    if any(l.strip() for l in cur):
        blocks.append("\n".join(cur))
    return blocks


def _parse_fields(block: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    cur: str | None = None
    for line in block.splitlines():
        m = _KEY_RE.match(line)
        if m and m.group(1) in _KEYS:
            cur = m.group(1)
            fields[cur] = m.group(2)
        elif cur:  # continuation of a multi-line field
            fields[cur] += "\n" + line
    return {k: v.strip() for k, v in fields.items()}


def _correct_indexes(raw: str) -> list[int]:
    return [int(m.group(1)) - 1 for m in _OPTION_RE.finditer(raw or "")]


def parse_mcq_text(text: str) -> list[MCQ]:
    mcqs: list[MCQ] = []
    for raw_block in _split_blocks(text):
        f = _parse_fields(raw_block)
        if "QUESTION_TEXT" not in f:
            continue
        question = f["QUESTION_TEXT"].replace("-END-", "").strip()
        options = [f[f"OPTION_{i}"] for i in range(1, 7) if f.get(f"OPTION_{i}")]
        if not question or len(options) < 2:
            continue
        correct = _correct_indexes(f.get("CORRECT_OPTION", ""))
        if not correct:
            continue
        multi = (f.get("QUESTION_TYPE", "").upper() == "MORE_THAN_ONE_MULTIPLE_CHOICE"
                 or len(correct) > 1)
        code = f.get("CODE", "NA")
        code = None if (not code or code.upper() == "NA") else code
        try:
            mcqs.append(MCQ(
                question=question,
                options=options,
                multi=multi,
                correctIndexes=correct,
                explanation=f.get("EXPLANATION", ""),
                code=code,
                learning_outcome=f.get("LEARNING_OUTCOME", "") or None,
                bloom_level=f.get("BLOOM_LEVEL", "") or None,
                raw_end_format=raw_block,
                meta={
                    "question_key": f.get("QUESTION_KEY", ""),
                    "bloom_level": f.get("BLOOM_LEVEL", ""),
                    "learning_outcome": f.get("LEARNING_OUTCOME", ""),
                    "topic": f.get("TOPIC", ""),
                    "sub_topic": f.get("SUB_TOPIC", ""),
                    "question_type": f.get("QUESTION_TYPE", ""),
                },
            ))
        except ValueError:
            continue  # skip a structurally-invalid question rather than failing the block
    return mcqs
