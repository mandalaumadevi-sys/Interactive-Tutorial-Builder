"""LangGraph shared state.

A single ``TutorialState`` dict is threaded through every node. Per-block work
writes into dicts keyed by block_id so parallel branches don't collide; the
reducers below merge concurrent updates.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from .schemas import (
    CandidateBlock,
    MCQ,
    NormalizedDocument,
)


def merge_dict(left: dict | None, right: dict | None) -> dict:
    """Reducer for parallel per-block writes (block_id -> value)."""
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class TutorialState(TypedDict, total=False):
    # ---- identity / config ----
    run_id: str
    course_id: str | None
    input_type: Literal["html", "pptx"]
    raw_input_path: str
    config: dict
    created_at: str
    metadata: dict            # course_name, session_name, learning_objectives
    memory: dict              # cross-session memory loaded at start
    status: str               # running | needs_review | completed | failed
    current_node: str
    # which human gate is open: "block" | "content" | "animation" | "mcq" | "quality"
    review_stage: str

    # ---- Stage 0 (ingestion) ----
    document: NormalizedDocument
    candidate_blocks: list[CandidateBlock]
    # supplementary reading material (HTML) — enriches Agent 1 content; NOT divided, NOT used for MCQs
    supplementary_material: str

    # ---- Stage 1/2 (division + HITL #1) ----
    division: BlockDivision  # type: ignore[name-defined]
    divider_validation: dict
    division_feedback: Annotated[list[str], operator.add]
    blocks_accepted: bool
    block_feedback: str
    review_iteration: int

    # ---- Stage 3 (per-agent gates: content → animation → MCQ) ----
    built_blocks_list: list[dict]                       # BlockResult dicts in block order
    mcqs: Annotated[dict[str, list[dict]], merge_dict]  # block_id (str) -> QUIZ_DATA entries

    # HITL #2 (content): per-block review — {block_id(str): feedback}. Only flagged blocks re-run.
    content_accepted: bool
    content_feedback: str            # (legacy, unused by content gate now)
    content_feedback_map: dict
    # HITL #3 (animation): per-block review — {block_id(str): feedback}. Only flagged blocks re-run.
    animation_accepted: bool
    animation_feedback: str          # (legacy)
    animation_feedback_map: dict
    animation_reject: list           # block_ids whose animation the human rejected (dropped)
    # HITL #4 (mcq): per-QUESTION review — maps/rejects keyed "block:index".
    mcq_accepted: bool
    mcq_feedback: str                # (legacy)
    mcq_feedback_map: dict           # {"block:index": feedback} → regenerate just that question
    mcq_block_feedback_map: dict     # {block_id: feedback} → regenerate that whole block's MCQs
    mcq_reject: list                 # ["block:index", …] → drop those questions
    # HITL #5 (assessment): human reviewed/edited the assessment → combined final review
    assessment_accepted: bool
    # HITL #6 (final combined review): the whole assembled tutorial is previewed; per-element
    # improvements are applied in place, then the human proceeds to publish.
    final_review_notes: str          # overall note left at the final gate (→ course memory)
    # every per-agent gate's feedback, accumulated for persistence to course memory
    stage_feedback: Annotated[list[str], operator.add]

    # ---- Stage 4 ----
    final_assessment: list[MCQ]

    # ---- Stage 5 (assembly) ----
    session_html_draft: str
    final_html: str
    output_path: str

    # ---- Stage 6 (eval + refine) ----
    eval_scores: Annotated[dict[str, Any], merge_dict]
    quality_report: dict
    escalations: Annotated[list, operator.add]
    retries: dict
    refine_target: str

    # ---- Stage 7 (HITL #2) ----
    review_decision: str      # approve | edit | reject
    review_edits: dict
    review_notes: str
    final_feedback: Annotated[list[str], operator.add]
    final_approved: bool


# Need BlockDivision in annotations above; import here to avoid an unused top-level import warning.
from .schemas import BlockDivision  # noqa: E402,F401
