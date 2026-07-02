"""Golden-set evaluation — does the rubric + LLM judge actually discriminate good from bad?

The eval-sets carry human-authored, labelled exemplars (``good_examples.json`` /
``bad_examples.json``). This harness replays them through the SAME judge the pipeline uses
(``validation_tools.self_validate``) and checks the labels hold:

  • every GOOD example should PASS (all rubric dimensions ≥ threshold), and
  • every BAD example should FAIL.

To avoid leakage, scoring is **leave-one-out**: the example under test is removed from the
few-shot context the judge sees, so it can't grade itself by recognising itself.

The headline metric is judge accuracy = (correctly-classified examples) / (total examples),
per agent and overall — a real, offline, ground-truth-labelled regression number.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from ..config import Settings, get_settings
from ..llm.client import LLMClient
from ..tools import validation_tools as vt
from ..utils.io import load_agent_evalset

# Agents whose eval-sets are scored by the rubric judge. (visual-decision is a few-shot
# decision aid for Agent 1, not a judged rubric, so it is intentionally excluded.)
DEFAULT_AGENTS = ["block_divider", "content", "visual", "mcq", "assessment", "final_quality"]


def _examples(blob: Any) -> list[dict]:
    """Normalise an eval-set file to a list of example dicts (handles both shapes)."""
    if isinstance(blob, dict):
        return [e for e in blob.get("examples", []) if isinstance(e, dict)]
    if isinstance(blob, list):
        return [e for e in blob if isinstance(e, dict)]
    return []


def _example_id(ex: dict, idx: int, label: str) -> str:
    return str(ex.get("example_id") or ex.get("id") or f"{label}_{idx:03d}")


def _output_text(ex: dict) -> str:
    """The text a judge should score — the example's ``output`` (serialised), else the example."""
    out = ex.get("output", ex)
    if isinstance(out, str):
        return out
    return json.dumps(out, indent=2, ensure_ascii=False)


def _leave_one_out(es: dict, drop_id: str) -> dict:
    """Return a copy of the eval-set with the example ``drop_id`` removed from good+bad few-shot."""
    loo = copy.deepcopy(es)
    for key in ("good", "bad"):
        blob = loo.get(key)
        if isinstance(blob, dict) and isinstance(blob.get("examples"), list):
            blob["examples"] = [e for e in blob["examples"]
                                if str(e.get("example_id") or e.get("id")) != drop_id]
        elif isinstance(blob, list):
            loo[key] = [e for e in blob
                        if str(e.get("example_id") or e.get("id")) != drop_id]
    return loo


def run_golden_eval(
    agents: list[str] | None = None,
    *,
    limit: int | None = None,
    client: LLMClient | None = None,
    settings: Settings | None = None,
    progress=None,
) -> dict:
    """Score every labelled example with the leave-one-out judge and report accuracy.

    ``limit`` caps examples-per-label-per-agent (handy for a cheap smoke run). ``progress`` is an
    optional ``callable(agent, label, example_id, correct, score)`` for live CLI output.
    Returns ``{"agents": {agent: {...}}, "overall": {...}}``.
    """
    settings = settings or get_settings()
    client = client or LLMClient(settings)
    if settings.use_mock:
        raise RuntimeError(
            "Golden eval needs a real judge — set TB_LLM_MODE=real with a valid OPENROUTER_API_KEY. "
            "(In mock mode the judge returns canned output, so the metric is meaningless.)"
        )

    agents = agents or DEFAULT_AGENTS
    report: dict = {"agents": {}, "overall": {}}
    g_total = g_correct = 0

    for agent in agents:
        es = load_agent_evalset(agent, settings)
        if not (es.get("rubric") or {}).get("dimensions"):
            report["agents"][agent] = {"skipped": "no rubric dimensions"}
            continue

        rows: list[dict] = []
        for label, expect_pass in (("good", True), ("bad", False)):
            items = _examples(es.get(label))
            if limit:
                items = items[:limit]
            for idx, ex in enumerate(items, start=1):
                ex_id = _example_id(ex, idx, label)
                verdict = vt.self_validate(
                    agent, _output_text(ex),
                    evalset=_leave_one_out(es, ex_id),
                    client=client, settings=settings,
                )
                correct = (verdict.passed == expect_pass)
                rows.append({"example_id": ex_id, "label": label,
                             "expected_pass": expect_pass, "judged_pass": verdict.passed,
                             "score": verdict.weighted_score, "correct": correct})
                if progress:
                    progress(agent, label, ex_id, correct, verdict.weighted_score)

        total = len(rows)
        correct = sum(1 for r in rows if r["correct"])
        good_rows = [r for r in rows if r["label"] == "good"]
        bad_rows = [r for r in rows if r["label"] == "bad"]
        report["agents"][agent] = {
            "total": total,
            "correct": correct,
            "accuracy": round(correct / total, 3) if total else None,
            "good_pass_rate": _rate(good_rows, lambda r: r["judged_pass"]),
            "bad_fail_rate": _rate(bad_rows, lambda r: not r["judged_pass"]),
            "rows": rows,
        }
        g_total += total
        g_correct += correct

    report["overall"] = {
        "total": g_total,
        "correct": g_correct,
        "accuracy": round(g_correct / g_total, 3) if g_total else None,
    }
    return report


def _rate(rows: list[dict], pred) -> float | None:
    return round(sum(1 for r in rows if pred(r)) / len(rows), 3) if rows else None
