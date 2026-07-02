"""Turn the human-authored eval-set rubrics into DeepEval metrics.

Each rubric dimension becomes a ``GEval`` metric whose ``evaluation_steps`` carry the
dimension's description and whose ``Rubric`` bands are built from the 1/5/10 anchors the
curriculum team wrote. The dimension's ``weight`` is carried alongside the metric so the
runner can reproduce the weighted aggregate the in-pipeline judge uses.

Selected agents also get RAG metrics where the output must stay grounded in the source:
``FaithfulnessMetric`` (no invented claims vs. the source) for the content and MCQ agents,
and likewise for the end-to-end tutorial. These run on the same OpenRouter judge.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from deepeval.metrics import FaithfulnessMetric, GEval
from deepeval.metrics.g_eval.g_eval import Rubric
from deepeval.test_case import LLMTestCaseParams as P

from ...config import Settings, get_settings
from ...utils.io import dimension_id, load_agent_evalset
from .model import OpenRouterDeepEvalModel

# Agents whose source-grounding warrants a Faithfulness check on top of the rubric GEvals.
RAG_AGENTS = {"content", "mcq"}

# GEval looks at these test-case fields. We always populate all three (see dataset.py).
_GEVAL_PARAMS = [P.INPUT, P.ACTUAL_OUTPUT, P.CONTEXT]


@dataclass
class DimMetric:
    """A GEval metric for one rubric dimension, plus the weight it carries in the aggregate."""

    dimension: str
    weight: float
    metric: GEval


@dataclass
class AgentMetrics:
    agent: str
    threshold: float  # 0-1 (rubric pass_threshold / 10)
    dims: list[DimMetric]
    rag: list[FaithfulnessMetric] = field(default_factory=list)


def _rubric_from_anchors(anchors: dict | None) -> list[Rubric]:
    """Map the rubric's 1/5/10 score anchors onto DeepEval score bands (0-10)."""
    anchors = anchors or {}

    def _txt(*keys: str) -> str:
        for k in keys:
            v = anchors.get(k)
            if v:
                return str(v)
        return ""

    low = _txt("1", "0") or "Fails this dimension badly."
    mid = _txt("5", "4", "6") or "Partially satisfies this dimension."
    high = _txt("10", "9") or "Fully satisfies this dimension."
    return [
        Rubric(score_range=(0, 3), expected_outcome=low),
        Rubric(score_range=(4, 6), expected_outcome=mid),
        Rubric(score_range=(7, 10), expected_outcome=high),
    ]


def _geval_for_dimension(agent: str, dim: dict, threshold: float,
                         model: OpenRouterDeepEvalModel) -> DimMetric:
    dim_id = dimension_id(dim)
    name = dim.get("name", dim_id)
    description = dim.get("description", name)
    steps = [
        f"You are grading the '{name}' dimension of the {agent} agent's output.",
        f"Criterion: {description}",
        "Read INPUT for the task/context and ACTUAL_OUTPUT for what the agent produced; "
        "use CONTEXT as the source material the output must respect.",
        "Score strictly against the rubric bands, calibrated by their descriptions. "
        "Judge ONLY this dimension, not overall quality.",
    ]
    metric = GEval(
        name=f"{agent}:{dim_id}",
        evaluation_steps=steps,
        rubric=_rubric_from_anchors(dim.get("anchors")),
        evaluation_params=_GEVAL_PARAMS,
        model=model,
        threshold=threshold,
        async_mode=False,
    )
    return DimMetric(dimension=dim_id, weight=float(dim.get("weight", 0.0)), metric=metric)


def build_agent_metrics(agent: str, *, settings: Settings | None = None,
                        model: OpenRouterDeepEvalModel | None = None,
                        rubric: dict | None = None) -> AgentMetrics:
    """Build the DeepEval metric bundle for ``agent`` from its eval-set rubric.

    ``rubric`` overrides the loaded rubric (used by the end-to-end path for ``final_quality``).
    """
    settings = settings or get_settings()
    model = model or OpenRouterDeepEvalModel(settings)
    if rubric is None:
        rubric = load_agent_evalset(agent, settings).get("rubric") or {}
    dimensions = rubric.get("dimensions", [])
    threshold = float(rubric.get("pass_threshold", settings.pass_threshold)) / 10.0

    dims = [_geval_for_dimension(agent, d, threshold, model) for d in dimensions]
    rag: list[FaithfulnessMetric] = []
    if agent in RAG_AGENTS:
        rag.append(FaithfulnessMetric(threshold=threshold, model=model,
                                      include_reason=True, async_mode=False))
    return AgentMetrics(agent=agent, threshold=threshold, dims=dims, rag=rag)
