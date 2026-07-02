"""API request/response + run-record models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    pending = "pending"
    running = "running"
    needs_review = "needs_review"   # a human gate is open
    completed = "completed"
    failed = "failed"


class RunInfo(BaseModel):
    run_id: str
    status: RunStatus = RunStatus.pending
    course_name: str = ""
    session_name: str = ""
    created_at: str = ""
    updated_at: str = ""
    current_node: str = ""
    # "block" | "content" | "animation" | "mcq" | "quality"
    review_stage: str = ""
    message: str = ""
    output_path: str | None = None
    llm_calls: int = 0                # LLM calls made by THIS run (delta over the run's lifetime)
    llm_tokens: int = 0               # total tokens used by THIS run (exact real / estimated mock)


class BlockReviewRequest(BaseModel):
    accepted: bool = True
    feedback: str = ""               # non-empty + not accepted → divider re-runs


class StageReviewRequest(BaseModel):
    """Per-agent gate decision (content | animation | mcq).

    content/animation: ``feedback_map`` = {block_id: feedback}; only flagged blocks re-run
    (empty map = accept all). mcq: a single ``feedback`` string."""

    accepted: bool = True
    feedback: str = ""
    feedback_map: dict = Field(default_factory=dict)
    reject: list = Field(default_factory=list)   # animation: block_ids · mcq: "block:index" keys
    block_feedback_map: dict = Field(default_factory=dict)  # mcq: {block_id: feedback} (whole block)


class FinalReviewRequest(BaseModel):
    decision: str = Field(default="approve", pattern="^(approve|reject|edit)$")
    notes: str = ""
    edits: dict = Field(default_factory=dict)


class McqEditRequest(BaseModel):
    """In-place edit of one block's MCQs at the MCQ gate."""
    block_id: str
    action: str = "question"           # "question" | "block" | "reject"
    index: int | None = None
    feedback: str = ""


class AssessmentEditRequest(BaseModel):
    """In-place edit of the session assessment at the assessment gate."""
    action: str = "question"           # "question" | "all" | "reject"
    index: int | None = None
    feedback: str = ""


class ContentEditRequest(BaseModel):
    """In-place re-author of one block at the final combined-review gate."""
    block_id: str
    feedback: str = ""


class AnimationEditRequest(BaseModel):
    """In-place animation edit. With image_id set, only that one animation changes."""
    block_id: str
    action: str = "refine"             # "refine" | "reject"
    feedback: str = ""
    image_id: str = ""                 # target one animation (empty = whole block)


class FinalProceedRequest(BaseModel):
    """Proceed from the final combined review to publish; optional overall note → course memory."""
    notes: str = ""


class StartResponse(BaseModel):
    run_id: str
    status: str
