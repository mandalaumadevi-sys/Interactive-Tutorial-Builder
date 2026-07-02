"""Offline mock LLM — canned, schema-valid outputs routed by ``purpose``.

Lets the whole pipeline run end-to-end with no API key and no cost. The outputs are
plausible and structurally valid (so parsers/assemblers exercise real code paths),
but they are intentionally generic — not meant to be *good*, just to *run*.
"""

from __future__ import annotations

import json
from typing import Any


def generate(purpose: str, meta: dict[str, Any] | None = None) -> str:
    meta = meta or {}
    if purpose == "block_divide":
        return _mock_division(meta)
    if purpose == "agent1_content":
        return _mock_content(meta)
    if purpose == "agent2_animation":
        return _mock_animation(meta)
    if purpose == "image_describe":
        return _mock_image_describe(meta)
    if purpose == "mcq":
        return _mock_mcq_end(meta)
    if purpose == "assessment":
        return _mock_assessment_qa(meta)
    if purpose in ("self_validate", "final_quality"):
        return _mock_eval(meta)
    return "[mock] response"


# --------------------------------------------------------------------------- #
def _mock_division(meta: dict) -> str:
    count = int(meta.get("candidate_count", 4) or 4)
    target = int(meta.get("target_blocks", 5) or 5)
    # The mock can't understand feedback text, but to prove the HITL re-divide loop
    # works end-to-end it visibly changes the grouping when feedback was given
    # (merges one block). A real LLM applies the feedback semantically instead.
    if meta.get("has_feedback"):
        target = max(1, target - 1)
    nblocks = max(1, min(target, count))
    ids = list(range(1, count + 1))
    # contiguous, roughly-even partition of the section ids into `nblocks` groups
    groups: list[list[int]] = [[] for _ in range(nblocks)]
    for idx, cid in enumerate(ids):
        groups[idx * nblocks // max(1, count)].append(cid)
    groups = [g for g in groups if g] or [ids]
    blocks = [
        {
            "title": f"Block {i}",
            "source_section_ids": g,
            "objectives": [f"Understand the key idea of block {i}"],
        }
        for i, g in enumerate(groups, start=1)
    ]
    return json.dumps({
        "session_name": meta.get("session_name", "Mock Session"),
        "total_blocks": len(blocks),
        "division_reasoning": f"[mock] grouped {count} sections into {len(blocks)} contiguous blocks.",
        "blocks": blocks,
    })


def _mock_content(meta: dict) -> str:
    title = meta.get("title", "Concept")
    first_img = meta.get("first_image_id")
    marker = f"<!--HF_ANIM:{first_img}-->" if first_img else ""
    decisions = (
        [{"image_id": first_img, "decision": "send_to_agent2",
          "visual_type": "flowchart", "reason": "[mock] concept-bearing diagram"}]
        if first_img else []
    )
    html = (
        f'<div class="main-content">'
        f'<div class="section-label"><h2>{title}</h2><p>[mock] overview</p></div>'
        f'<p>[mock] This block explains <strong>{title}</strong> in connected prose so the '
        f'pipeline has realistic content to assemble.</p>'
        f'{marker}'
        f'<div class="key-takeaway"><span class="takeaway-label">Key takeaway</span>'
        f'<p>[mock] the core idea of {title}.</p></div>'
        f'</div>'
    )
    return json.dumps({
        "content_html": html,
        "image_decisions": decisions,
        "concepts_defined": [title],
        "visual_patterns_used": ["flowchart"] if first_img else [],
    })


def _mock_animation(meta: dict) -> str:
    iid = (meta.get("image_id") or "img").replace("-", "_")
    return (
        f'<div class="animation-container" id="anim-{iid}">'
        f'<style>#anim-{iid} .reveal_{iid}{{opacity:1}}'
        f'@media (prefers-reduced-motion: reduce){{#anim-{iid} *{{animation:none}}}}</style>'
        f'<svg viewBox="0 0 400 120" class="reveal_{iid}">'
        f'<rect x="20" y="30" width="120" height="50" fill="#3b82f6" rx="6"/>'
        f'<text x="40" y="60" fill="#fff">[mock anim]</text></svg>'
        f'<script>(function(){{/* steps_{iid} */}})();</script></div>'
    )


def _mock_image_describe(meta: dict) -> str:
    label = (meta.get("alt") or meta.get("nearby_heading") or "a diagram").strip()
    worthy = bool(meta.get("worthy_hint"))
    return json.dumps({
        "description": f"[mock] Illustration of {label}.",
        "placement_context": meta.get("nearby_heading") or label,
        "animation_worthy": worthy,
        "visual_type": "flowchart" if worthy else "concept",
    })


def _mock_mcq_end(meta: dict) -> str:
    n = int(meta.get("n", 2) or 2)
    topic = meta.get("title", "the topic")
    out = []
    for i in range(1, n + 1):
        out.append(
            f"TOPIC: {topic}\n"
            f"SUB_TOPIC: {topic} detail {i}\n"
            f"QUESTION_KEY: mock_{meta.get('block_id', 0)}_{i}\n"
            f"QUESTION_TEXT: [mock] Which statement about {topic} is correct (Q{i})?\n"
            f"QUESTION_TYPE: SINGLE_MULTIPLE_CHOICE\n"
            f"CODE: NA\n"
            f"OPTION_1: The correct statement about {topic}\n"
            f"OPTION_2: A plausible but wrong statement\n"
            f"OPTION_3: Another incorrect statement\n"
            f"OPTION_4: A clearly wrong statement\n"
            f"CORRECT_OPTION: OPTION_1\n"
            f"EXPLANATION: [mock] Option 1 correctly describes {topic}.\n"
            f"BLOOM_LEVEL: UNDERSTAND\n"
            f"LEARNING_OUTCOME: understand_{topic}\n"
            f"-END-"
        )
    return "\n".join(out)


def _mock_assessment_qa(meta: dict) -> str:
    n = int(meta.get("n", 5) or 5)
    topic = meta.get("title", "the session")
    out = []
    for i in range(1, n + 1):
        is_long = (i % 3 == 0)  # vary short/long like a real set
        out.append({
            "question_number": i,
            "question_type": "long" if is_long else "short",
            "question": (f"[mock] Explain how key idea {i} of {topic} works?" if is_long
                         else f"[mock] What is key idea {i} of {topic}?"),
            "blooms_level": "K2" if is_long else "K1",
            "answer": (f"[mock] Key idea {i} of {topic} is a concise, session-derived model answer "
                       f"a learner can compare their own response against."),
        })
    return json.dumps(out)


def _mock_eval(meta: dict) -> str:
    dims = meta.get("dimensions") or ["overall"]
    return json.dumps({
        "dimensions": [
            {"dimension": d, "weight": round(1.0 / len(dims), 3), "score": 8.5,
             "reasoning": "[mock] passes", "improvement_instruction": "",
             "improvement": "", "reason": "[mock] passes"}
            for d in dims
        ],
        "overall_passed": True,
        "summary": "[mock] meets the bar.",
    })
