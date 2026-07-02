"""Self-validation shared by agents.

Two layers:
  • Rule-based structural checks — cheap, deterministic (no LLM).
  • Eval-set self-validation     — the agent's output scored by an LLM against its eval-set
                                   (rubric dimensions + good/bad examples) → drives a self-retry.
"""

from __future__ import annotations

import json

from bs4 import BeautifulSoup

from ..config import Settings, get_settings
from ..llm.base import as_object
from ..llm.client import LLMClient
from ..schemas import DimensionScore, SelfValidation
from ..utils.io import dimension_id, load_agent_evalset


# ── rule-based structural checks ───────────────────────────────────────────── #
def validate_html_structure(html: str) -> list[str]:
    """Agent 1 — content block structural checks."""
    issues: list[str] = []
    soup = BeautifulSoup(html or "", "lxml")
    if not soup.find(class_="main-content") and not soup.find(class_="content-block"):
        issues.append("missing top-level .main-content / .content-block wrapper")
    if not soup.find(["h2", "h3"]):
        issues.append("no heading (h2/h3) in the block")
    if "<script" in (html or "") or "<style" in (html or ""):
        issues.append("content_html must not contain <script>/<style>")
    # body-content gate: catch empty / heading-only blocks (text beyond the headings)
    all_text = soup.get_text(" ", strip=True)
    heading_text = " ".join(h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"]))
    if len(all_text) - len(heading_text) < 60:
        issues.append("block has little or no explanation content (heading only?)")
    return issues


def check_js_namespace(html: str, image_id: str) -> bool:
    if not image_id:
        return True
    token = image_id.replace("-", "_")
    return token in (html or "") or image_id in (html or "")


def validate_animation_html(html: str, image_id: str) -> list[str]:
    """Agent 2 — animation structural checks (self-contained, namespaced, reduced-motion safe)."""
    issues: list[str] = []
    h = html or ""
    if "src=" in h and ("http://" in h or "https://" in h):
        issues.append("animation must not reference external resources")
    if "@media (prefers-reduced-motion" not in h:
        issues.append("missing prefers-reduced-motion media query")
    if not check_js_namespace(h, image_id):
        issues.append(f"CSS/JS identifiers are not namespaced with the image_id ({image_id})")
    if "<svg" not in h and "<canvas" not in h:
        issues.append("no <svg>/<canvas> drawing in the animation")
    # Auto-play/loop only — no Play/Reset/Next control buttons of any kind.
    if "<button" in h.lower():
        issues.append("animation must auto-play and loop with NO control buttons "
                      "(remove any Play/Pause/Reset/Replay/Next/Step buttons)")
    return issues


# ── eval-set self-validation ──────────────────────────────────────────────── #
_SELF_VALIDATE_SYSTEM = (
    "You are a strict self-validation reviewer. Score the OUTPUT against EACH rubric dimension "
    "0-10, calibrated by the good/bad examples. Be honest — this gates a self-retry.\n\n"
    "Return ONLY JSON:\n"
    '{ "dimensions": [ {"dimension": "<id>", "weight": <float>, "score": <0-10>, '
    '"reason": "<one sentence>", "improvement": "<actionable fix if low, else \'\'>"} ], '
    '"summary": "<one sentence verdict>" }'
)


def self_validate(
    agent: str,
    output_text: str,
    *,
    context: str = "",
    client: LLMClient | None = None,
    settings: Settings | None = None,
    evalset: dict | None = None,
    max_output_chars: int = 8000,
) -> SelfValidation:
    """Score ``output_text`` against ``eval-sets/<agent>/`` (rubric + good/bad examples).

    Pass ``evalset`` to override the loaded eval-set — used by the golden-set harness to do
    leave-one-out scoring (the example under test is removed from the few-shot context).
    """
    settings = settings or get_settings()
    client = client or LLMClient(settings)
    es = evalset if evalset is not None else load_agent_evalset(agent, settings)
    rubric = es.get("rubric") or {"pass_threshold": settings.pass_threshold, "dimensions": []}

    if not rubric.get("dimensions"):
        return SelfValidation(agent=agent, weighted_score=10.0, passed=True,
                              summary="no rubric dimensions defined; skipped")

    threshold = float(rubric.get("pass_threshold", settings.pass_threshold))
    dim_ids = [dimension_id(d) for d in rubric.get("dimensions", [])]
    user = (
        f"AGENT UNDER REVIEW: {agent}\n\n"
        f"RUBRIC:\n{json.dumps(rubric, indent=2)}\n\n"
        f"GOOD EXAMPLES:\n{json.dumps(es.get('good', []))}\n\n"
        f"BAD EXAMPLES:\n{json.dumps(es.get('bad', []))}\n\n"
        f"{('CONTEXT:' + chr(10) + context + chr(10) + chr(10)) if context else ''}"
        f"OUTPUT TO SCORE:\n{output_text[:max_output_chars]}"
    )
    data = as_object(client.complete_json(
        purpose="self_validate", system=_SELF_VALIDATE_SYSTEM, user=user,
        model=settings.eval_model, meta={"agent": agent, "dimensions": dim_ids},
    ))
    dims = [
        DimensionScore(
            dimension=dimension_id(d),
            weight=float(d.get("weight", 0.0)),
            score=float(d.get("score", 0.0)),
            passed=float(d.get("score", 0.0)) >= threshold,
            reason=d.get("reason", "") or d.get("reasoning", ""),
            improvement=d.get("improvement", "") or d.get("improvement_instruction", ""),
        )
        for d in data.get("dimensions", [])
    ]
    total_w = sum(d.weight for d in dims) or 1.0
    weighted = round(sum(d.score * d.weight for d in dims) / total_w, 2)
    passed = bool(dims) and all(d.passed for d in dims)
    return SelfValidation(agent=agent, weighted_score=weighted, passed=passed,
                          dimensions=dims, summary=data.get("summary", ""))
