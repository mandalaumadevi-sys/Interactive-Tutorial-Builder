"""LangGraph assembly — the full agentic pipeline with FIVE human-in-the-loop gates.

Flow (each 👤 gate pauses via interrupt_before; accept → next stage, refine → regenerate & re-pause):

  ingest(+image descriptions) → divide → 👤 block review ─(accept)─┐
                                          └(feedback)→ divide        │
        ┌───────────────────────────────────────────────────────────┘
        ▼
  content (Agent 1: author + animate/skip) → 👤 content review ─(accept)─┐  └(refine)→ content
        ┌────────────────────────────────────────────────────────────────┘
        ▼
  animation (Agent 2) → 👤 animation review ─(accept)─┐  └(refine)→ animation
        ┌──────────────────────────────────────────────┘
        ▼
  mcq (Agent 3) → 👤 mcq review ─(accept)─┐  └(refine)→ mcq
        ┌──────────────────────────────────┘
        ▼
  assessment (Agent 4) → draft → quality ─ pass ───────────────────────→ assemble → memory → END
                                         ├ fail (retries<max) → refine → quality
                                         └ exhausted → 👤 final review ─ approve → assemble
                                                                        └ reject  → divide

Each producing stage attaches an advisory eval score to ``eval_scores`` so the human sees metrics
at its gate. State is stored as plain dicts so it round-trips through any checkpointer.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from langgraph.graph import END, START, StateGraph

from .agents import agent1_content as a1
from .agents import agent3_mcq as a3
from .agents import agent4_assessment as a4
from .assembler import html_assembler
from .config import get_settings
from .ingest import ingest
from .llm.client import LLMClient
from .memory import cross_session
from .memory.guidance import standing_guidance
from .memory.run_state import defined_concepts, mcq_topics
from .schemas import (
    MCQ, AssessmentQuestion, Block, BlockDivision, BlockResult, FinalQualityReport, VisualDecision,
)
from .state import TutorialState
from .steps import block_divider as s_divider
from .steps import final_quality_check as s_quality
from .steps import stage_eval
from .tools.html_tools import parse_blocks
from .utils.events import RUN_BUS
from .utils.io import run_dir
from .utils.logging import RunLogger, now_iso

_MAX_WORKERS = 6
# gate node → review_stage label exposed to the API/UI
_STAGE_BY_NODE = {
    "human_block_review": "block",
    "human_content_review": "content",
    "human_animation_review": "animation",
    "human_mcq_review": "mcq",
    "human_assessment_review": "assessment",
    "human_final_review": "final",
}


# ── helpers ─────────────────────────────────────────────────────────────────
def _emit(state: TutorialState, node: str, status: str, **extra) -> None:
    rid = state.get("run_id", "")
    RUN_BUS.publish(rid, {"type": "node", "node": node, "status": status, **extra})
    if rid:
        try:
            RunLogger(rid, get_settings().runs_path).log("node", node=node, status=status, **extra)
        except Exception:  # noqa: BLE001 — logging must never break a run
            pass


def _meta(state: TutorialState) -> dict:
    return state.get("metadata", {}) or {}


def _division(state: TutorialState) -> BlockDivision:
    return BlockDivision(**state["division"]) if state.get("division") else BlockDivision()


def _blocks(state: TutorialState) -> list[Block]:
    return _division(state).blocks


def _built(state: TutorialState) -> list[BlockResult]:
    return [BlockResult(**b) for b in state.get("built_blocks_list", [])]


def _mcqs(state: TutorialState) -> dict[int, list[MCQ]]:
    return {int(k): [MCQ(**m) for m in v] for k, v in state.get("mcqs", {}).items()}


def _final(state: TutorialState) -> list[AssessmentQuestion]:
    return [AssessmentQuestion(**m) for m in state.get("final_assessment", [])]


# ── per-block fan-out helpers (each returns the COMPLETE list in block order) ──
def _author_blocks(blocks, memory, client, settings, *, notes: str = "",
                   supplementary: str = "", notes_by_id: dict | None = None,
                   prev_by_id: dict | None = None) -> list[dict]:
    """Agent 1 phase 1 — author block HTML + animate/skip verdicts (no animations yet).

    On a refine, ``prev_by_id`` (block_id str -> current block HTML) lets the agent REVISE the exact
    existing block for the feedback instead of rewriting it from scratch."""
    notes_by_id = notes_by_id or {}
    prev_by_id = prev_by_id or {}
    out: dict[int, BlockResult] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        fut = {pool.submit(a1.author, b, memory=memory, client=client, settings=settings,
                           extra_notes=notes_by_id.get(str(b.block_id), notes),
                           supplementary=supplementary,
                           previous_html=prev_by_id.get(str(b.block_id), "")): b.block_id
               for b in blocks}
        for f in fut:
            out[fut[f]] = f.result()
    order = [b.block_id for b in blocks]
    return [out[i].model_dump(mode="json") for i in order if i in out]


def _animate_blocks(blocks, built: list[BlockResult], client, settings, *, notes: str = "",
                    notes_by_id: dict | None = None) -> list[dict]:
    """Agent 2 phase — place an animation for each ANIMATE verdict (per-block notes supported)."""
    notes_by_id = notes_by_id or {}
    images_by_block = {b.block_id: b.images for b in blocks}
    out: dict[int, BlockResult] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        fut = {pool.submit(a1.apply_animations, r, images_by_block.get(r.block_id, []),
                           client=client, settings=settings,
                           extra_notes=notes_by_id.get(str(r.block_id), notes)): r.block_id
               for r in built}
        for f in fut:
            out[fut[f]] = f.result()
    order = [b.block_id for b in blocks]
    return [out[i].model_dump(mode="json") for i in order if i in out]


def _mcq_blocks(blocks, client, settings, *, notes: str = "") -> dict[str, list[dict]]:
    """Agent 3 — per-block MCQs, keyed by block_id (str) for the merge reducer."""
    quizzes: dict[int, list[MCQ]] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        fut = {pool.submit(a3.run, b, client=client, settings=settings, extra_notes=notes): b.block_id
               for b in blocks}
        for f in fut:
            quizzes[fut[f]] = f.result()
    order = [b.block_id for b in blocks]
    return {str(i): [m.model_dump(mode="json", by_alias=True) for m in quizzes[i]]
            for i in order if i in quizzes}


# ── nodes ───────────────────────────────────────────────────────────────────
def ingest_node(state: TutorialState) -> dict:
    settings = get_settings()
    _emit(state, "ingest", "start")
    doc = ingest(state["raw_input_path"], state["input_type"],
                 run_id=state["run_id"], metadata=_meta(state), settings=settings)
    candidates = parse_blocks(doc.normalized_html)
    _attach_descriptions(candidates, doc.assets)  # carry vision hints onto the parsed images
    meta = dict(_meta(state))
    meta.setdefault("session_name", doc.session_meta.session_name)
    meta.setdefault("course_name", doc.session_meta.course_name)
    meta.setdefault("learning_objectives", doc.session_meta.learning_objectives)
    memory = cross_session.load(meta["course_name"], settings=settings)
    described = sum(1 for a in doc.assets if a.description)
    # Supplementary reading material (NOT divided / NOT used for MCQs) — enriches Agent 1 content.
    from .ingest import material_html
    supplementary = material_html(meta)
    _emit(state, "ingest", "done", candidates=len(candidates),
          images=len(doc.assets), described=described, has_material=bool(supplementary))
    return {"document": doc.model_dump(), "candidate_blocks": [c.model_dump() for c in candidates],
            "metadata": meta, "memory": memory, "supplementary_material": supplementary,
            "status": "running", "current_node": "ingest",
            "retries": {}, "review_iteration": 0}


def _attach_descriptions(candidates, assets) -> None:
    """Copy ingest-time vision hints (matched by src) onto each candidate block's images.

    ``parse_blocks`` re-inventories images straight from the HTML and so loses the descriptions
    that ``image_describer`` put on ``doc.assets``; this re-unites them by source URL/path."""
    by_src = {a.src: a for a in assets}
    for c in candidates:
        for im in c.images:
            a = by_src.get(im.src)
            if a is None:
                continue
            im.description = a.description
            im.placement_context = a.placement_context
            im.animation_worthy = a.animation_worthy
            im.description_source = a.description_source
            im.alt = im.alt or a.alt
            im.caption = im.caption or a.caption
            im.nearby_heading = im.nearby_heading or a.nearby_heading
            im.source_ref = im.source_ref or a.source_ref  # keep "user-added" so it always animates


def divide_node(state: TutorialState) -> dict:
    settings = get_settings()
    client = LLMClient(settings)
    _emit(state, "divide", "start")
    from .schemas import CandidateBlock
    candidates = [CandidateBlock(**c) for c in state.get("candidate_blocks", [])]
    feedback = (state.get("block_feedback") or "").strip()
    previous = _blocks(state) if feedback else None
    doc = state.get("document", {})
    division, validation = s_divider.run(
        candidates, _meta(state).get("learning_objectives", []),
        feedback=feedback, previous=previous,
        normalized_html=doc.get("normalized_html", ""),
        session_name=_meta(state).get("session_name", "Session"),
        guidance=standing_guidance(state.get("memory", {}), "division"),
        client=client, settings=settings,
    )
    _emit(state, "divide", "done", blocks=len(division.blocks), valid=validation.passed)
    return {"division": division.model_dump(), "divider_validation": validation.model_dump(),
            "blocks_accepted": False, "block_feedback": "",
            "review_iteration": state.get("review_iteration", 0) + 1,
            "status": "needs_review", "current_node": "human_block_review", "review_stage": "block"}


def human_block_review_node(state: TutorialState) -> dict:
    accepted = bool(state.get("blocks_accepted"))
    _emit(state, "human_block_review", "decision",
          accepted=accepted, has_feedback=bool(state.get("block_feedback")))
    out: dict = {"status": "running", "review_stage": ""}
    fb = (state.get("block_feedback") or "").strip()
    if fb:
        out["division_feedback"] = [fb]
    return out


def content_node(state: TutorialState) -> dict:
    """Agent 1 phase 1 → 👤 content gate (HITL #2). Per-block refine: only flagged blocks re-run."""
    settings = get_settings()
    client = LLMClient(settings)
    blocks = _blocks(state)
    fb_map = {k: v for k, v in (state.get("content_feedback_map") or {}).items() if (v or "").strip()}
    supp = state.get("supplementary_material", "")
    memory = state.get("memory", {})
    existing = state.get("built_blocks_list", [])
    if fb_map and existing:
        # Re-author ONLY the flagged blocks; keep the rest as-is.
        redo = [b for b in blocks if str(b.block_id) in fb_map]
        _emit(state, "content", "start", refine=True, blocks=len(redo))
        # current HTML per flagged block → the agent revises THAT block for the feedback
        prev_by_id = {str(b["block_id"]): (b.get("authored_html") or b.get("content_html") or "")
                      for b in existing}
        redone = {d["block_id"]: d for d in _author_blocks(
            redo, memory, client, settings, supplementary=supp, notes_by_id=fb_map,
            prev_by_id=prev_by_id)}
        by_id = {b["block_id"]: b for b in existing}
        by_id.update(redone)
        built_list = [by_id[b.block_id] for b in blocks if b.block_id in by_id]
    else:
        _emit(state, "content", "start", blocks=len(blocks), refine=False)
        built_list = _author_blocks(blocks, memory, client, settings, supplementary=supp,
                                    notes=standing_guidance(memory, "content"))
    # No advisory eval score shown at the content gate (the human reviews the rendered blocks
    # directly). Faithfulness is still enforced inside Agent 1's own source-grounded self-check.
    flagged = [b.get("title", f"block {b.get('block_id')}") for b in built_list if b.get("quality_issues")]
    _emit(state, "content", "done", flagged_blocks=flagged)
    return {"built_blocks_list": built_list, "content_feedback_map": {}, "content_accepted": False,
            "status": "needs_review", "current_node": "human_content_review",
            "review_stage": "content"}


def human_content_review_node(state: TutorialState) -> dict:
    fb_map = {k: v for k, v in (state.get("content_feedback_map") or {}).items() if (v or "").strip()}
    _emit(state, "human_content_review", "decision",
          accepted=not fb_map, refine_blocks=list(fb_map.keys()))
    out: dict = {"status": "running", "review_stage": ""}
    if fb_map:
        out["stage_feedback"] = [f"[content b{k}] {v}" for k, v in fb_map.items()]
    return out


def animation_node(state: TutorialState) -> dict:
    """Agent 2 → 👤 animation gate (HITL #3). Per-block: refine regenerates, reject drops it."""
    settings = get_settings()
    client = LLMClient(settings)
    blocks = _blocks(state)
    built = _built(state)  # list[BlockResult]
    fb_map = {k: v for k, v in (state.get("animation_feedback_map") or {}).items() if (v or "").strip()}
    rejects = {str(x) for x in (state.get("animation_reject") or [])}
    affected = set(fb_map) | rejects
    if affected and any(b.animations or b.visual_verdicts for b in built):
        # Reject → flip that block's ANIMATE verdicts to SKIP so re-applying yields no animation.
        redo = [r for r in built if str(r.block_id) in affected]
        for r in redo:
            if str(r.block_id) in rejects:
                for v in r.visual_verdicts:
                    if v.decision == VisualDecision.ANIMATE:
                        v.decision = VisualDecision.SKIP
        _emit(state, "animation", "start", refine=len(fb_map), rejected=len(rejects))
        redone = {d["block_id"]: d for d in _animate_blocks(blocks, redo, client, settings,
                                                            notes_by_id=fb_map)}
        new_built = [redone.get(r.block_id) or r.model_dump(mode="json") for r in built]
    else:
        n_anim = sum(1 for b in built for v in b.visual_verdicts if v.decision.value == "animate")
        _emit(state, "animation", "start", to_animate=n_anim, refine=False)
        # NOTE: no cross-session "standing guidance" here on purpose — animation feedback is
        # image/block-specific and doesn't transfer between sessions; injecting it derailed fresh
        # generation. Animations are built from the image + the block's process narrative; refine
        # per-block at the animation gate instead.
        new_built = _animate_blocks(blocks, built, client, settings)
    metrics = stage_eval.evaluate_animation([BlockResult(**b) for b in new_built],
                                            client=client, settings=settings)
    made = sum(len(b.get("animations", [])) for b in new_built)
    _emit(state, "animation", "done", animations=made, score=metrics.get("score"))
    return {"built_blocks_list": new_built, "animation_feedback_map": {}, "animation_reject": [],
            "animation_accepted": False, "eval_scores": {"visual": metrics},
            "status": "needs_review", "current_node": "human_animation_review",
            "review_stage": "animation"}


def human_animation_review_node(state: TutorialState) -> dict:
    fb_map = {k: v for k, v in (state.get("animation_feedback_map") or {}).items() if (v or "").strip()}
    rejects = [str(x) for x in (state.get("animation_reject") or [])]
    _emit(state, "human_animation_review", "decision",
          accepted=not (fb_map or rejects), refine_blocks=list(fb_map.keys()), rejected=rejects)
    out: dict = {"status": "running", "review_stage": ""}
    notes = [f"[animation b{k}] {v}" for k, v in fb_map.items()]
    notes += [f"[animation b{k}] rejected" for k in rejects]
    if notes:
        out["stage_feedback"] = notes
    return out


def mcq_node(state: TutorialState) -> dict:
    """Agent 3 → 👤 mcq gate (HITL #4). Per-QUESTION: feedback regenerates that one question,
    reject drops it. Keys are "block_id:index"."""
    settings = get_settings()
    client = LLMClient(settings)
    blocks = _blocks(state)
    blocks_by_id = {str(b.block_id): b for b in blocks}
    fb_map = {k: v for k, v in (state.get("mcq_feedback_map") or {}).items() if (v or "").strip()}
    block_fb = {str(k): v for k, v in (state.get("mcq_block_feedback_map") or {}).items() if (v or "").strip()}
    rejects = {str(x) for x in (state.get("mcq_reject") or [])}

    if (fb_map or block_fb or rejects) and state.get("mcqs"):
        mcq_map = {k: list(v) for k, v in state["mcqs"].items()}  # copy existing
        # 1) Block-level feedback → regenerate that whole block's MCQ set (overrides its per-question).
        for bid, fb in block_fb.items():
            blk = blocks_by_id.get(bid)
            if blk is None:
                continue
            new_qs = a3.run(blk, client=client, settings=settings, extra_notes=fb)
            mcq_map[bid] = [m.model_dump(mode="json", by_alias=True) for m in new_qs]
        # 2) Per-question feedback (skip blocks already wholesale-regenerated).
        for key, fb in fb_map.items():
            bid, _, idx = key.partition(":")
            if bid in block_fb or bid not in blocks_by_id or bid not in mcq_map or not idx.isdigit():
                continue
            i = int(idx)
            new_qs = a3.run(blocks_by_id[bid], count=1, client=client, settings=settings, extra_notes=fb)
            if new_qs and 0 <= i < len(mcq_map[bid]):
                mcq_map[bid][i] = new_qs[0].model_dump(mode="json", by_alias=True)
        # 3) Drop rejected questions (descending index per block; skip wholesale-regenerated blocks).
        by_block: dict[str, list[int]] = {}
        for key in rejects:
            bid, _, idx = key.partition(":")
            if bid not in block_fb and idx.isdigit():
                by_block.setdefault(bid, []).append(int(idx))
        for bid, idxs in by_block.items():
            if bid in mcq_map:
                for i in sorted(idxs, reverse=True):
                    if 0 <= i < len(mcq_map[bid]):
                        del mcq_map[bid][i]
        _emit(state, "mcq", "start", refine=len(fb_map), block_refine=len(block_fb), rejected=len(rejects))
    else:
        _emit(state, "mcq", "start", blocks=len(blocks), refine=False)
        mcq_map = _mcq_blocks(blocks, client, settings,
                              notes=standing_guidance(state.get("memory", {}), "mcq"))

    metrics = stage_eval.evaluate_mcq({int(k): [MCQ(**m) for m in v] for k, v in mcq_map.items()},
                                      client=client, settings=settings)
    _emit(state, "mcq", "done", mcqs=sum(len(v) for v in mcq_map.values()),
          score=metrics.get("score"))
    return {"mcqs": mcq_map, "mcq_feedback_map": {}, "mcq_block_feedback_map": {}, "mcq_reject": [],
            "mcq_accepted": False, "eval_scores": {"mcq": metrics},
            "status": "needs_review", "current_node": "human_mcq_review", "review_stage": "mcq"}


def human_mcq_review_node(state: TutorialState) -> dict:
    fb_map = {k: v for k, v in (state.get("mcq_feedback_map") or {}).items() if (v or "").strip()}
    block_fb = {k: v for k, v in (state.get("mcq_block_feedback_map") or {}).items() if (v or "").strip()}
    rejects = [str(x) for x in (state.get("mcq_reject") or [])]
    _emit(state, "human_mcq_review", "decision", accepted=not (fb_map or block_fb or rejects),
          refine=list(fb_map.keys()), block_refine=list(block_fb.keys()), rejected=rejects)
    out: dict = {"status": "running", "review_stage": ""}
    notes = ([f"[mcq {k}] {v}" for k, v in fb_map.items()]
             + [f"[mcq block {k}] {v}" for k, v in block_fb.items()]
             + [f"[mcq {k}] rejected" for k in rejects])
    if notes:
        out["stage_feedback"] = notes
    return out


def assessment_node(state: TutorialState) -> dict:
    """Agent 4 generates the session assessment → 👤 assessment gate (HITL #5)."""
    settings = get_settings()
    client = LLMClient(settings)
    _emit(state, "assessment", "start")
    topics = mcq_topics(_mcqs(state))
    out = a4.run(_built(state), session_name=_meta(state).get("session_name", "Session"),
                 learning_objectives=_meta(state).get("learning_objectives", []),
                 mcq_topics_used=topics, client=client, settings=settings,
                 extra_notes=standing_guidance(state.get("memory", {}), "assessment"))
    fa = [m.model_dump(mode="json", by_alias=True) for m in out]
    draft = _render_draft(state, fa, settings)  # full preview incl. the assessment
    _emit(state, "assessment", "done", questions=len(out))
    return {"final_assessment": fa, "session_html_draft": draft, "assessment_accepted": False,
            "status": "needs_review", "current_node": "human_assessment_review",
            "review_stage": "assessment"}


def _render_draft(state: TutorialState, final_assessment: list[dict], settings) -> str:
    """Render the complete tutorial (blocks + MCQs + assessment) for preview at the gate."""
    try:
        return html_assembler.render(
            session_title=_meta(state).get("session_name", "Session"),
            blocks=_built(state), mcqs=_mcqs(state),
            final_assessment=[AssessmentQuestion(**m) for m in final_assessment], settings=settings)
    except Exception:  # noqa: BLE001 — preview is best-effort
        return ""


def human_assessment_review_node(state: TutorialState) -> dict:
    """HITL #5 — human accepted/edited the assessment; proceed to the combined final review."""
    _emit(state, "human_assessment_review", "decision", accepted=bool(state.get("assessment_accepted")))
    return {"status": "running", "review_stage": ""}


def prepare_final_review_node(state: TutorialState) -> dict:
    """Render the FULLY assembled tutorial (blocks + animations + MCQs + assessment) and open the
    combined final-review gate (HITL #6). Per-element improvements are applied in place at the gate
    (see RunManager.edit_*); proceeding publishes."""
    settings = get_settings()
    _emit(state, "prepare_final_review", "start")
    draft = _render_draft(state, state.get("final_assessment", []), settings)
    _emit(state, "prepare_final_review", "done")
    return {"session_html_draft": draft, "status": "needs_review",
            "current_node": "human_final_review", "review_stage": "final"}


def human_final_review_node(state: TutorialState) -> dict:
    """HITL #6 — human reviewed the whole tutorial and chose to publish. Any overall note is kept
    for course memory so it auto-applies on future runs."""
    notes = (state.get("final_review_notes") or "").strip()
    _emit(state, "human_final_review", "decision", has_notes=bool(notes))
    out: dict = {"status": "running", "review_stage": ""}
    if notes:
        out["final_feedback"] = [notes]
    return out


def draft_node(state: TutorialState) -> dict:
    _emit(state, "draft", "start")
    settings = get_settings()
    html = html_assembler.render(session_title=_meta(state).get("session_name", "Session"),
                                 blocks=_built(state), mcqs=_mcqs(state),
                                 final_assessment=[], settings=settings)
    _emit(state, "draft", "done")
    return {"session_html_draft": html}


def quality_node(state: TutorialState) -> dict:
    settings = get_settings()
    client = LLMClient(settings)
    _emit(state, "quality", "start")
    report = s_quality.run(_built(state), _mcqs(state), _final(state),
                           session_name=_meta(state).get("session_name", "Session"),
                           learning_objectives=_meta(state).get("learning_objectives", []),
                           client=client, settings=settings)
    _emit(state, "quality", "done", passed=report.overall_passed,
          failing=[d.dimension for d in report.failed_dimensions])
    scores = {report.dimensions[i].dimension: report.dimensions[i].score
              for i in range(len(report.dimensions))}
    return {"quality_report": report.model_dump(), "eval_scores": {"final_quality": scores}}


def refine_node(state: TutorialState) -> dict:
    settings = get_settings()
    client = LLMClient(settings)
    report = FinalQualityReport(**state["quality_report"])
    target = report.refine_target() or "content"
    retries = dict(state.get("retries", {}))
    retries[target] = retries.get(target, 0) + 1
    notes = report.improvement_notes(target)
    _emit(state, "refine", "start", target=target, attempt=retries[target])

    out: dict = {"retries": retries, "refine_target": target}
    blocks = _blocks(state)
    if target == "content":
        authored = _author_blocks(blocks, state.get("memory", {}), client, settings, notes=notes,
                                  supplementary=state.get("supplementary_material", ""))
        built_list = _animate_blocks(blocks, [BlockResult(**b) for b in authored],
                                     client, settings, notes=notes)
        out["built_blocks_list"] = built_list
        new_built = [BlockResult(**b) for b in built_list]
        out["final_assessment"] = [
            m.model_dump(mode="json", by_alias=True) for m in a4.run(
                new_built, session_name=_meta(state).get("session_name", "Session"),
                learning_objectives=_meta(state).get("learning_objectives", []),
                client=client, settings=settings, extra_notes=notes)
        ]
    elif target == "mcq":
        out["mcqs"] = _mcq_blocks(blocks, client, settings, notes=notes)
    elif target == "assessment":
        out["final_assessment"] = [
            m.model_dump(mode="json", by_alias=True) for m in a4.run(
                _built(state), session_name=_meta(state).get("session_name", "Session"),
                learning_objectives=_meta(state).get("learning_objectives", []),
                client=client, settings=settings, extra_notes=notes)
        ]
    _emit(state, "refine", "done", target=target)
    return out


def prepare_quality_review_node(state: TutorialState) -> dict:
    settings = get_settings()
    import json
    review = run_dir(state["run_id"], settings) / "review"
    review.mkdir(parents=True, exist_ok=True)
    try:
        html = html_assembler.render(session_title=_meta(state).get("session_name", "Session"),
                                     blocks=_built(state), mcqs=_mcqs(state),
                                     final_assessment=_final(state), settings=settings)
        (review / "draft.html").write_text(html, encoding="utf-8")
    except Exception as err:  # noqa: BLE001
        (review / "draft_error.txt").write_text(str(err), encoding="utf-8")
    (review / "quality_report.json").write_text(
        json.dumps(state.get("quality_report", {}), indent=2), encoding="utf-8")
    _emit(state, "prepare_quality_review", "done", review_dir=str(review))
    return {"status": "needs_review", "current_node": "human_quality_gate", "review_stage": "quality"}


def human_quality_gate_node(state: TutorialState) -> dict:
    decision = state.get("review_decision", "approve")
    _emit(state, "human_quality_gate", "decision", decision=decision)
    out: dict = {"status": "running", "review_stage": ""}
    notes = (state.get("review_notes") or "").strip()
    if notes:
        out["final_feedback"] = [notes]
    if decision == "edit":
        edits = state.get("review_edits") or {}
        for key in ("built_blocks_list", "mcqs", "final_assessment"):
            if key in edits:
                out[key] = edits[key]
    return out


def assemble_node(state: TutorialState) -> dict:
    settings = get_settings()
    _emit(state, "assemble", "start")
    meta = _meta(state)
    html = html_assembler.render(session_title=meta.get("session_name", "Session"),
                                 blocks=_built(state), mcqs=_mcqs(state),
                                 final_assessment=_final(state), settings=settings)
    course = meta.get("course_name", "Course")
    session = meta.get("session_name", "Session")
    fname = html_assembler.output_filename(course, session)
    html_assembler.write_tutorial(html, run_dir(state["run_id"], settings) / fname)
    published = html_assembler.publish_tutorial(html, course, session, settings)
    # Persist to the DB too (Supabase when reachable, else local SQLite), so finished tutorials
    # are retrievable from the database — not just from the generated_tutorials/ folder.
    try:
        from .persistence import tutorials as tut_store
        backend = tut_store.save(state["run_id"], course, session, html, str(published), settings=settings)
    except Exception:  # noqa: BLE001 — DB copy is best-effort; the file on disk is the source of truth
        backend = "none"
    _emit(state, "assemble", "done", output=str(published), db=backend)
    return {"final_html": html, "output_path": str(published), "status": "completed"}


def memory_node(state: TutorialState) -> dict:
    settings = get_settings()
    meta = _meta(state)
    report = FinalQualityReport(**state["quality_report"]) if state.get("quality_report") else None
    score = None
    if report and report.dimensions:
        score = round(sum(d.score for d in report.dimensions) / len(report.dimensions), 2)
    # Persist EVERY human gate's feedback (block division, per-agent gates, final review).
    # cross_session.update de-duplicates, so the same review note is never stored twice.
    feedback = (list(state.get("division_feedback", []))
                + list(state.get("stage_feedback", []))
                + list(state.get("final_feedback", [])))
    cross_session.update(meta.get("course_name", "Course"),
                         new_concepts=defined_concepts(_built(state)),
                         new_mcq_topics=mcq_topics(_mcqs(state)),
                         feedback=feedback, eval_score=score,
                         session=meta.get("session_name", "Session"), settings=settings)
    _emit(state, "memory", "done")
    return {"final_approved": True}


# ── routers ───────────────────────────────────────────────────────────────────
def route_block_review(state: TutorialState) -> str:
    if (state.get("block_feedback") or "").strip() and not state.get("blocks_accepted"):
        return "divide"
    return "content"  # default: accept


def route_content_review(state: TutorialState) -> str:
    fb_map = {k: v for k, v in (state.get("content_feedback_map") or {}).items() if (v or "").strip()}
    return "content" if fb_map else "animation"


def route_animation_review(state: TutorialState) -> str:
    fb_map = {k: v for k, v in (state.get("animation_feedback_map") or {}).items() if (v or "").strip()}
    rejects = [x for x in (state.get("animation_reject") or [])]
    return "animation" if (fb_map or rejects) else "mcq"


def route_mcq_review(state: TutorialState) -> str:
    fb_map = {k: v for k, v in (state.get("mcq_feedback_map") or {}).items() if (v or "").strip()}
    block_fb = {k: v for k, v in (state.get("mcq_block_feedback_map") or {}).items() if (v or "").strip()}
    rejects = [x for x in (state.get("mcq_reject") or [])]
    return "mcq" if (fb_map or block_fb or rejects) else "assessment"


def route_quality(state: TutorialState) -> str:
    """Self-refine ONCE on failure, then always escalate to the final human gate.

    The reviewer always sees the assembled draft + quality metrics and explicitly accepts the
    assessment (GATE 5) — the pipeline never auto-ships without that final human approval."""
    settings = get_settings()
    report = FinalQualityReport(**state["quality_report"])
    if not report.overall_passed:
        target = report.refine_target() or "content"
        if state.get("retries", {}).get(target, 0) < settings.max_refine_attempts:
            return "refine"
    return "review"  # always land on the final human review (GATE 5)


def route_quality_review(state: TutorialState) -> str:
    return "divide" if state.get("review_decision") == "reject" else "assemble"


# ── build ───────────────────────────────────────────────────────────────────
def build_graph(checkpointer=None):
    if checkpointer is None:
        from .persistence.checkpointer import build_checkpointer
        checkpointer = build_checkpointer()

    g = StateGraph(TutorialState)
    g.add_node("ingest", ingest_node)
    g.add_node("divide", divide_node)
    g.add_node("human_block_review", human_block_review_node)
    g.add_node("content", content_node)
    g.add_node("human_content_review", human_content_review_node)
    g.add_node("animation", animation_node)
    g.add_node("human_animation_review", human_animation_review_node)
    g.add_node("mcq", mcq_node)
    g.add_node("human_mcq_review", human_mcq_review_node)
    g.add_node("assessment", assessment_node)
    g.add_node("human_assessment_review", human_assessment_review_node)
    g.add_node("prepare_final_review", prepare_final_review_node)
    g.add_node("human_final_review", human_final_review_node)
    g.add_node("assemble", assemble_node)
    g.add_node("memory", memory_node)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "divide")
    g.add_edge("divide", "human_block_review")
    g.add_conditional_edges("human_block_review", route_block_review,
                            {"content": "content", "divide": "divide"})
    g.add_edge("content", "human_content_review")
    g.add_conditional_edges("human_content_review", route_content_review,
                            {"animation": "animation", "content": "content"})
    g.add_edge("animation", "human_animation_review")
    g.add_conditional_edges("human_animation_review", route_animation_review,
                            {"mcq": "mcq", "animation": "animation"})
    g.add_edge("mcq", "human_mcq_review")
    g.add_conditional_edges("human_mcq_review", route_mcq_review,
                            {"assessment": "assessment", "mcq": "mcq"})
    # Assessment → human review (accept/edit questions) → combined final review of the whole
    # assembled tutorial → publish.
    g.add_edge("assessment", "human_assessment_review")
    g.add_edge("human_assessment_review", "prepare_final_review")
    g.add_edge("prepare_final_review", "human_final_review")
    g.add_edge("human_final_review", "assemble")
    g.add_edge("assemble", "memory")
    g.add_edge("memory", END)

    return g.compile(checkpointer=checkpointer,
                     interrupt_before=["human_block_review", "human_content_review",
                                       "human_animation_review", "human_mcq_review",
                                       "human_assessment_review", "human_final_review"])


def initial_state(run_id: str, input_path: str, input_type: str,
                  metadata: dict | None = None, course_id: str | None = None) -> dict:
    from pathlib import Path
    s = get_settings()
    return {
        "run_id": run_id,
        "course_id": course_id,
        "input_type": input_type,
        "raw_input_path": str(Path(input_path).resolve()),
        "metadata": metadata or {},
        "config": {
            "mcq_per_block": s.mcq_per_block,
            "final_assessment_count": s.final_assessment_count,
            "pass_threshold": s.pass_threshold,
            "max_refine_attempts": s.max_refine_attempts,
        },
        "created_at": now_iso(),
    }
