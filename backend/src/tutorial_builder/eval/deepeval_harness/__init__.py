"""DeepEval-based evaluation harness for the tutorial-builder agentic workflow.

This is an *additive* layer on top of the existing rubric judge (``tools.validation_tools``)
and the golden-set regression (``eval.golden``). It expresses the SAME human-authored eval-set
rubrics as DeepEval metrics so the workflow can be measured with a standard, well-known eval
framework:

  • per-agent quality — each eval-set rubric dimension → a ``GEval`` metric (anchored by the
    1/5/10 rubric anchors), plus selected RAG metrics (Faithfulness) where the output must stay
    grounded in the source. Replayed over the labelled good/bad golden examples to report judge
    accuracy, mirroring ``eval.golden`` but through DeepEval.

  • end-to-end — the final assembled tutorial scored against its source session via the
    session-level ``final_quality`` rubric + Faithfulness.

The judge runs on the project's own OpenRouter client (no OpenAI key, no cloud upload):
``OpenRouterDeepEvalModel`` wraps ``LLMClient`` so DeepEval scores with the configured
``judge_model`` (default ``anthropic/claude-sonnet-4.6``). A real ``OPENROUTER_API_KEY`` is
required — DeepEval metrics are meaningless against the offline mock.
"""

from __future__ import annotations

from .model import OpenRouterDeepEvalModel
from .runner import GOLDEN_AGENTS, run_deepeval_e2e, run_deepeval_golden

__all__ = [
    "OpenRouterDeepEvalModel",
    "GOLDEN_AGENTS",
    "run_deepeval_golden",
    "run_deepeval_e2e",
]
