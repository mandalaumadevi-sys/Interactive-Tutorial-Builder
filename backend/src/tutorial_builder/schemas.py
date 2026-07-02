"""Pydantic data contracts shared across the pipeline.

These mirror the artifacts in PRD.md and docs/normalized_html_contract.md and are
the stable interfaces between LangGraph nodes.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


# --------------------------------------------------------------------------- #
# Session metadata
# --------------------------------------------------------------------------- #
class SessionMeta(BaseModel):
    session_name: str = "Session"
    course_name: str = "Course"
    source_type: Literal["html", "pptx"] = "html"
    source_filename: str = ""
    learning_objectives: list[str] = Field(default_factory=list)
    language: str = "ENGLISH"


# --------------------------------------------------------------------------- #
# Stage 0 — Ingestion / normalization
# --------------------------------------------------------------------------- #
class ImageRef(BaseModel):
    """One image found during ingestion, with the context needed to judge concept-relevance."""

    image_id: str
    src: str  # local path under assets/ (or remote/data: for the HTML sample)
    alt: str = ""
    caption: str = ""
    nearby_heading: str = ""
    slide_index: int | None = None
    width: int | None = None
    height: int | None = None
    occurrences: int = 1  # how many times this exact src appears (logos/bullets repeat)
    source_ref: str | None = None
    bytes: int | None = None
    format: str = "png"

    # ---- Stage 0.5 — vision description (guides placement + animation decision) ----
    # Produced by ingest/image_describer for BOTH flows. Degrades to alt/heading heuristics
    # when the pixels aren't reachable or the offline mock is active.
    description: str = ""            # what the image depicts (concept-level, 1-2 sentences)
    placement_context: str = ""     # which idea it illustrates / where it belongs in the block
    animation_worthy: bool | None = None  # concept-bearing → worth animating (hint for Agent 1)
    description_source: str = ""     # "vision" | "heuristic" | "mock" | ""


class NormalizedDocument(BaseModel):
    session_meta: SessionMeta
    normalized_html: str
    assets: list[ImageRef] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Stage 1 — Block division
# --------------------------------------------------------------------------- #
class HeadingNode(BaseModel):
    level: int  # 1..4
    text: str


class CandidateBlock(BaseModel):
    """Deterministic HTML-parser output — a rule-based split at hard heading boundaries."""

    block_id: int
    title: str
    content_html: str = ""
    images: list[ImageRef] = Field(default_factory=list)
    word_count: int = 0


class Block(BaseModel):
    """Block-Divider output (after merge/split + human review) — one cohesive concept per block."""

    block_id: int
    title: str  # learner-facing
    h2_sections_included: list[str] = Field(default_factory=list)
    content_html: str = ""  # verbatim source HTML for this block
    images: list[ImageRef] = Field(default_factory=list)
    word_count_estimate: int = 0
    learning_objectives_hint: list[str] = Field(default_factory=list)


class BlockDivision(BaseModel):
    session_name: str = "Session"
    total_blocks: int = 0
    heading_tree: list[HeadingNode] = Field(default_factory=list)
    division_reasoning: str = ""
    blocks: list[Block] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Stage 3 — Per-block outputs
# --------------------------------------------------------------------------- #
class VisualDecision(str, Enum):
    ANIMATE = "animate"
    SKIP = "skip"


class VisualVerdict(BaseModel):
    image_id: str
    decision: VisualDecision
    visual_type: str | None = None  # flowchart | lifecycle | architecture | comparison | concept
    reason: str = ""


class Animation(BaseModel):
    """A self-contained inline animation produced by Agent 2."""

    image_id: str
    visual_type: str = "flowchart"
    reference_template: str | None = None  # which ref-library pattern matched
    html: str  # inline <style> + <svg> (+ minimal JS), namespaced by image_id


class BlockResult(BaseModel):
    """Agent 1's output for a single block (animations already placed inline in content_html)."""

    block_id: int
    title: str = ""
    content_html: str  # authored interactive HTML for this block (animations placed inline)
    authored_html: str = ""  # pre-animation HTML (with markers) — base for idempotent re-animation
    animation_used: bool = False
    visual_verdicts: list[VisualVerdict] = Field(default_factory=list)
    animations: list[Animation] = Field(default_factory=list)
    concepts_defined: list[str] = Field(default_factory=list)
    visual_patterns_used: list[str] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)
    # non-empty → this block failed its self-checks (e.g. empty/thin content); surfaced at HITL #2
    quality_issues: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Stage 3/4 — MCQs  (final shape == output HTML's QUIZ_DATA entry)
# --------------------------------------------------------------------------- #
class MCQ(BaseModel):
    """Matches the QUIZ_DATA object consumed by the output HTML's JS."""

    question: str
    options: list[str]
    multi: bool = False
    correct_indexes: list[int] = Field(alias="correctIndexes")
    explanation: str = ""
    code: str | None = None  # rendered as <pre><code> for code-analysis questions

    # provenance kept for evaluation/memory, stripped at assembly time
    learning_outcome: str | None = None
    bloom_level: str | None = None
    raw_end_format: str | None = None
    meta: dict = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _check(self) -> "MCQ":
        if len(self.options) < 2:
            raise ValueError("an MCQ needs at least 2 options")
        if not self.correct_indexes:
            raise ValueError("an MCQ needs at least one correct index")
        if any(i < 0 or i >= len(self.options) for i in self.correct_indexes):
            raise ValueError("correct_indexes out of range")
        if not self.multi and len(self.correct_indexes) != 1:
            raise ValueError("single-answer MCQ must have exactly one correct index")
        return self

    def to_quiz_entry(self) -> dict:
        """The exact JS object shape the output HTML consumes."""
        return {
            "question": self.question,
            "options": self.options,
            "multi": self.multi,
            "correctIndexes": self.correct_indexes,
            "explanation": self.explanation,
            "code": self.code,
        }


class AssessmentQuestion(BaseModel):
    """A descriptive (open-ended) end-of-session assessment item: a direct question + its model
    answer. Rendered as a read-through carousel (no options, no grading). Fields mirror the
    assessment eval-set: short vs long type and a Bloom's K-level (K1/K2/K4/K6)."""

    question: str
    answer: str
    question_type: str = "short"   # "short" | "long"
    blooms_level: str = ""         # K1 | K2 | K4 | K6

    def to_entry(self) -> dict:
        return {"question": self.question, "answer": self.answer,
                "question_type": self.question_type, "blooms_level": self.blooms_level}


# --------------------------------------------------------------------------- #
# Stage 6 — Evaluation
# --------------------------------------------------------------------------- #
class DimensionScore(BaseModel):
    dimension: str
    score: float = 0.0  # 0..10
    weight: float = 0.0
    passed: bool = True
    reason: str = ""
    improvement: str = ""


class EvalResult(BaseModel):
    stage: str
    score: float = 0.0  # weighted 0..10
    pass_threshold: float = 7.0
    passed: bool = False
    dimensions: list[DimensionScore] = Field(default_factory=list)
    critique: str = ""
    attempt: int = 1


class SelfValidation(BaseModel):
    """An agent scoring its OWN output against its eval-set (rubric + examples)."""

    agent: str
    weighted_score: float = 0.0
    passed: bool = True
    dimensions: list[DimensionScore] = Field(default_factory=list)
    summary: str = ""

    @property
    def failing_dimensions(self) -> list[DimensionScore]:
        return [d for d in self.dimensions if not d.passed]

    def improvement_notes(self) -> str:
        return "\n".join(
            f"- {d.dimension}: {d.improvement or d.reason}" for d in self.failing_dimensions
        )


class FinalQualityReport(BaseModel):
    """Session-level Final Quality Check across all blocks + assessment."""

    dimensions: list[DimensionScore] = Field(default_factory=list)
    overall_passed: bool = True
    summary: str = ""

    # dimension → owning agent map drives which stage to refine on failure
    OWNER: dict[str, str] = Field(default_factory=lambda: {
        "learning_flow": "content",
        "objective_coverage": "content",
        "content_depth_consistency": "content",
        "mcq_variety_across_session": "mcq",
        "assessment_synthesis": "assessment",
    }, exclude=True)

    @property
    def failed_dimensions(self) -> list[DimensionScore]:
        return [d for d in self.dimensions if not d.passed]

    def refine_target(self) -> str | None:
        if not self.failed_dimensions:
            return None
        worst = min(self.failed_dimensions, key=lambda d: d.score)
        return self.OWNER.get(worst.dimension, "content")

    def improvement_notes(self, agent: str) -> str:
        return "\n".join(
            f"- {d.dimension}: {d.improvement or d.reason}"
            for d in self.failed_dimensions
            if self.OWNER.get(d.dimension, "content") == agent
        )
