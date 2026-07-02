"""Run the DeepEval metrics over the golden set and over a finished tutorial.

Per-agent (``run_deepeval_golden``): replay every labelled good/bad exemplar through the
agent's rubric GEvals (+ Faithfulness where applicable) and check the label holds — good
should pass, bad should fail. Headline metric is judge accuracy vs. the golden labels, the
DeepEval analogue of ``eval.golden``.

End-to-end (``run_deepeval_e2e``): score one assembled tutorial against its source session
with the session-level ``final_quality`` rubric + a Faithfulness check.

A real OPENROUTER_API_KEY is required; in mock mode the judge returns canned output and the
numbers are meaningless, so both entry points refuse to run on the mock.
"""

from __future__ import annotations

from pathlib import Path

from deepeval.metrics import FaithfulnessMetric
from deepeval.test_case import LLMTestCase

from ...config import Settings, get_settings
from ...utils.io import load_agent_evalset
from . import dataset
from .metrics import AgentMetrics, build_agent_metrics
from .model import OpenRouterDeepEvalModel

# Agents with real labelled exemplars + a scoreable rubric. (final_quality is session-level —
# its exemplars are placeholders — so it is evaluated through the end-to-end path instead.)
GOLDEN_AGENTS = ["block_divider", "content", "visual", "mcq", "assessment"]


def _require_real(settings: Settings) -> None:
    if settings.use_mock:
        raise RuntimeError(
            "DeepEval evaluation needs a real judge — set TB_LLM_MODE=real with a valid "
            "OPENROUTER_API_KEY. (In mock mode the judge returns canned output.)"
        )


def _score_case(test_case: LLMTestCase, bundle: AgentMetrics,
                rag_extra: list[FaithfulnessMetric] | None = None) -> dict:
    """Measure every metric on one test case and aggregate to a weighted score + pass/fail."""
    dim_rows = []
    for dm in bundle.dims:
        try:
            dm.metric.measure(test_case)
            score10 = round((dm.metric.score or 0.0) * 10, 2)
            dim_rows.append({"dimension": dm.dimension, "weight": dm.weight,
                             "score": score10, "passed": bool(dm.metric.is_successful()),
                             "reason": (dm.metric.reason or "")[:300]})
        except Exception as err:  # noqa: BLE001 — a judge failure shouldn't crash the sweep
            dim_rows.append({"dimension": dm.dimension, "weight": dm.weight, "score": None,
                             "passed": False, "reason": f"metric error: {err}", "error": True})

    rag_rows = []
    for r in list(bundle.rag) + list(rag_extra or []):
        try:
            r.measure(test_case)
            rag_rows.append({"metric": r.__class__.__name__,
                             "score": round((r.score or 0.0) * 10, 2),
                             "passed": bool(r.is_successful()),
                             "reason": (r.reason or "")[:300]})
        except Exception as err:  # noqa: BLE001
            rag_rows.append({"metric": r.__class__.__name__, "score": None,
                             "passed": False, "reason": f"metric error: {err}", "error": True})

    scored = [d for d in dim_rows if d["score"] is not None]
    total_w = sum(d["weight"] for d in scored) or 1.0
    weighted = round(sum(d["score"] * d["weight"] for d in scored) / total_w, 2) if scored else None
    dims_pass = bool(dim_rows) and all(d["passed"] for d in dim_rows)
    rag_pass = all(r["passed"] for r in rag_rows)
    return {"weighted_score": weighted, "dims_pass": dims_pass, "rag_pass": rag_pass,
            "passed": dims_pass and rag_pass, "dimensions": dim_rows, "rag": rag_rows}


def _rate(rows: list[dict], pred) -> float | None:
    return round(sum(1 for r in rows if pred(r)) / len(rows), 3) if rows else None


def run_deepeval_golden(agents: list[str] | None = None, *, limit: int | None = None,
                        settings: Settings | None = None,
                        model: OpenRouterDeepEvalModel | None = None,
                        progress=None) -> dict:
    """Replay golden exemplars through the DeepEval metrics; report judge accuracy per agent.

    ``progress`` is an optional ``callable(agent, label, example_id, correct, weighted_score)``.
    """
    settings = settings or get_settings()
    _require_real(settings)
    model = model or OpenRouterDeepEvalModel(settings)
    agents = agents or GOLDEN_AGENTS

    report: dict = {"agents": {}, "overall": {}}
    g_total = g_correct = 0
    for agent in agents:
        bundle = build_agent_metrics(agent, settings=settings, model=model)
        if not bundle.dims:
            report["agents"][agent] = {"skipped": "no rubric dimensions"}
            continue

        rows: list[dict] = []
        for case in dataset.golden_cases(agent, settings=settings, limit=limit):
            result = _score_case(case.test_case, bundle)
            correct = result["passed"] == case.expected_pass
            rows.append({"example_id": case.example_id, "label": case.label,
                         "expected_pass": case.expected_pass, "judged_pass": result["passed"],
                         "score": result["weighted_score"], "correct": correct,
                         "dimensions": result["dimensions"], "rag": result["rag"]})
            if progress:
                progress(agent, case.label, case.example_id, correct, result["weighted_score"])

        total = len(rows)
        correct = sum(1 for r in rows if r["correct"])
        good = [r for r in rows if r["label"] == "good"]
        bad = [r for r in rows if r["label"] == "bad"]
        report["agents"][agent] = {
            "total": total, "correct": correct,
            "accuracy": round(correct / total, 3) if total else None,
            "good_pass_rate": _rate(good, lambda r: r["judged_pass"]),
            "bad_fail_rate": _rate(bad, lambda r: not r["judged_pass"]),
            "rows": rows,
        }
        g_total += total
        g_correct += correct

    report["overall"] = {"total": g_total, "correct": g_correct,
                         "accuracy": round(g_correct / g_total, 3) if g_total else None}
    return report


def run_deepeval_e2e(*, run_dir: str | Path | None = None,
                     source_html: str | None = None, tutorial_html: str | None = None,
                     settings: Settings | None = None,
                     model: OpenRouterDeepEvalModel | None = None) -> dict:
    """Score one finished tutorial against its source via the final_quality rubric + Faithfulness.

    Provide either ``run_dir`` (a ``runs/<id>/`` with input.html + *tutorial.html) or an
    explicit ``source_html`` + ``tutorial_html`` pair.
    """
    settings = settings or get_settings()
    _require_real(settings)
    model = model or OpenRouterDeepEvalModel(settings)

    if run_dir is not None:
        test_case, tutorial_name = dataset.e2e_case_from_run(run_dir)
        source_label = str(Path(run_dir))
    elif source_html is not None and tutorial_html is not None:
        test_case = dataset.e2e_case(source_html, tutorial_html)
        tutorial_name, source_label = "<inline>", "<inline>"
    else:
        raise ValueError("run_deepeval_e2e needs run_dir, or both source_html and tutorial_html")

    rubric = load_agent_evalset("final_quality", settings).get("rubric") or {}
    bundle = build_agent_metrics("final_quality", settings=settings, model=model, rubric=rubric)
    faithfulness = FaithfulnessMetric(threshold=bundle.threshold, model=model,
                                      include_reason=True, async_mode=False)
    result = _score_case(test_case, bundle, rag_extra=[faithfulness])
    return {"source": source_label, "tutorial": tutorial_name,
            "threshold": round(bundle.threshold * 10, 1), **result}
