"""Agent 3 — MCQ Generator.

Runs in parallel with Agent 1 on the SAME raw block content (never Agent 1's HTML). Runs the
fixed MCQ prompt (``prompts/MCQ_generator_prompt.md``) verbatim, parses the ``-END-`` format into
the interactive QUIZ_DATA schema, and self-validates (structure) with one corrective retry.
"""

from __future__ import annotations

from ..config import Settings, get_settings
from ..llm.client import LLMClient
from ..schemas import Block, MCQ
from ..skills import validate
from ..tools import validation_tools as vt
from ..tools.html_tools import html_to_text
from ..tools.mcq_parser import parse_mcq_text
from ..utils.io import read_mcq_prompt


def _to_end_format(m: MCQ) -> str:
    """Render an existing MCQ back into the -END- block format (so the LLM edits it in place)."""
    lines = [
        f"TOPIC: {m.meta.get('topic', '')}",
        f"SUB_TOPIC: {m.meta.get('sub_topic', '')}",
        f"QUESTION_KEY: {m.meta.get('question_key', '')}",
        f"QUESTION_TEXT: {m.question}",
        f"QUESTION_TYPE: {'MORE_THAN_ONE_MULTIPLE_CHOICE' if m.multi else 'SINGLE_MULTIPLE_CHOICE'}",
        f"CODE: {m.code or 'NA'}",
    ]
    lines += [f"OPTION_{i}: {o}" for i, o in enumerate(m.options, 1)]
    lines.append("CORRECT_OPTION: " + ", ".join(f"OPTION_{i + 1}" for i in m.correct_indexes))
    lines += [f"EXPLANATION: {m.explanation}",
              f"BLOOM_LEVEL: {m.bloom_level or 'UNDERSTAND'}",
              f"LEARNING_OUTCOME: {m.learning_outcome or 'understand_topic'}", "-END-"]
    return "\n".join(lines)


def edit(block: Block, mcq: MCQ, feedback: str, *, client: LLMClient | None = None,
         settings: Settings | None = None) -> MCQ | None:
    """Apply ONLY the requested change to an existing MCQ, keeping everything else identical.

    Used by the per-question Apply: e.g. "change options 3 and 4" edits just those options and
    leaves the question text, other options, correct answer, and explanation untouched."""
    settings = settings or get_settings()
    client = client or LLMClient(settings)
    if settings.use_mock:
        return mcq  # offline: nothing to edit
    system = read_mcq_prompt(settings)
    reading = html_to_text(block.content_html)
    user = (
        f"READING MATERIAL (topic: {block.title}):\n\n{reading}\n\n"
        f"EXISTING MCQ (in -END- format):\n{_to_end_format(mcq)}\n\n"
        f"Apply ONLY this requested change and NOTHING else:\n\"{feedback}\"\n\n"
        f"STRICT EDIT RULES:\n"
        f"- Change ONLY what the feedback explicitly asks to change.\n"
        f"- Keep the QUESTION_TEXT, the OTHER (unmentioned) options, the CORRECT_OPTION, and the "
        f"EXPLANATION EXACTLY as they are — do not reword or 'improve' them.\n"
        f"- Preserve the option numbering and order.\n"
        f"- Any changed option must stay similar in length to the others and use only words from the "
        f"material.\n"
        f"Output the COMPLETE edited MCQ in the SAME -END- format (all fields), ending with -END-."
    )
    text = client.complete_text(purpose="mcq", system=system, user=user, model=settings.mcq_model,
                                meta={"block_id": block.block_id, "title": block.title, "n": 1})
    parsed = parse_mcq_text(text)
    return parsed[0] if parsed else None


def _balance_correct_positions(mcqs: list[MCQ], seed: str = "") -> list[MCQ]:
    """LLMs almost always place the correct answer first (OPTION_1), which makes the answer guessable.
    Rotate each single-answer question's options so the correct answer cycles through positions
    1→2→3→4. Only the option ORDER changes — the text, the correct answer, and the explanation are
    untouched; ``correct_indexes`` is remapped to follow the moved option."""
    offset = sum(ord(c) for c in seed) if seed else 0
    out: list[MCQ] = []
    for q, m in enumerate(mcqs):
        n = len(m.options)
        if m.multi or n < 2 or len(m.correct_indexes) != 1:
            out.append(m)  # leave multi-select / match-the-following alone
            continue
        target = (q + offset) % n                       # desired slot for the correct option
        shift = (target - m.correct_indexes[0]) % n      # rotate-right amount to land it there
        if shift:
            opts = m.options[-shift:] + m.options[:-shift]
            new_correct = sorted((i + shift) % n for i in m.correct_indexes)
            m = m.model_copy(update={"options": opts, "correct_indexes": new_correct})
        out.append(m)
    return out


def _serialize(mcqs: list[MCQ]) -> str:
    """Readable rendering of the MCQ set for the LLM rubric judge."""
    parts = []
    for i, m in enumerate(mcqs, 1):
        opts = "\n".join(f"  - {o}" for o in m.options)
        corr = ", ".join(str(c + 1) for c in m.correct_indexes)
        parts.append(f"Q{i}: {m.question}\n{opts}\nCorrect: {corr}\nExplanation: {m.explanation}")
    return "\n\n".join(parts)


def _count_for_block(block: Block, settings: Settings) -> int:
    signal = max(len(block.learning_objectives_hint),
                 block.word_count_estimate // 150,
                 settings.mcq_per_block)
    return max(settings.mcq_min, min(settings.mcq_max, signal))


def run(
    block: Block,
    *,
    count: int | None = None,
    mcq_topics_used: list[str] | None = None,
    client: LLMClient | None = None,
    settings: Settings | None = None,
    extra_notes: str = "",
) -> list[MCQ]:
    settings = settings or get_settings()
    client = client or LLMClient(settings)
    n = count if count is not None else _count_for_block(block, settings)

    system = read_mcq_prompt(settings)
    reading = html_to_text(block.content_html)
    avoid = (f"\n\nDo NOT generate questions on topics already covered: "
             f"{', '.join(mcq_topics_used)}" if mcq_topics_used else "")
    user = (
        f"READING MATERIAL (topic: {block.title}):\n\n{reading}\n\n"
        f"Generate exactly {n} MCQ(s) covering all sub-topics of THIS reading material, "
        f"following every rule above. End each question with -END-.\n"
        f"STRICT RULES:\n"
        f"- Keep each EXPLANATION SHORT — 1 to 2 lines maximum (one or two sentences).\n"
        f"- Make all four OPTIONS roughly EQUAL in length (similar word/character count) so length "
        f"never hints at the answer.\n"
        f"- Use ONLY words and terminology that appear in the reading material above — including the "
        f"WRONG options. Do NOT introduce any term, tool, or concept not present in the material.\n"
        f"- Make questions GENERIC and CLEAN — ask directly about the concept/term. Do NOT build "
        f"questions from use-cases, scenarios, stories, or analogies.\n"
        f"- VARY which option is correct across questions (sometimes OPTION_1, sometimes 2, 3, or 4). "
        f"Never make the correct answer always the first option.{avoid}"
    )
    if extra_notes:
        user += f"\n\nREVISION NOTES from the reviewer (address these):\n{extra_notes}"
    meta = {"block_id": block.block_id, "title": block.title, "n": n}

    def gen(extra: str = "") -> list[MCQ]:
        return parse_mcq_text(client.complete_text(purpose="mcq", system=system, user=user + extra,
                                                   model=settings.mcq_model, meta=meta))

    mcqs = gen()

    # Layer 1 — deterministic rule checks (free) with one corrective retry.
    issues = validate(mcqs)
    if issues and not settings.use_mock:
        retry = gen("\n\nThe previous attempt had these problems:\n- " + "\n- ".join(issues)
                    + "\nRegenerate all MCQs fixing them. End each with -END-.")
        if retry and len(validate(retry)) <= len(issues):
            mcqs = retry

    # Layer 2 — LLM rubric self-check against eval-sets/mcq (clarity, Bloom's, technical
    # accuracy, syllabus alignment — the qualitative checkpoints rules can't verify).
    if mcqs and not settings.use_mock and settings.self_validate_retries > 0:
        verdict = vt.self_validate("mcq", _serialize(mcqs),
                                   context=f"TOPIC: {block.title}", client=client, settings=settings)
        if not verdict.passed:
            fixes = "; ".join(d.improvement for d in verdict.dimensions if d.improvement) \
                or verdict.summary or "Improve clarity, accuracy, and material alignment."
            retry = gen("\n\nA reviewer scored the previous MCQs below the bar:\n"
                        f"{fixes}\nRegenerate all MCQs fixing this. End each with -END-.")
            if retry and len(validate(retry)) <= len(validate(mcqs)):
                mcqs = retry
    return _balance_correct_positions(mcqs, seed=str(block.block_id))
