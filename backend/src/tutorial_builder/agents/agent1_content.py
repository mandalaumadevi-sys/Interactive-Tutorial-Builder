"""Agent 1 — Content + HTML Builder (per block), orchestrator of the block.

Receives ONE final block. Rewrites the raw curriculum HTML into a learner-facing tutorial block
matching the house style, and decides — per image — whether it is concept-bearing enough to
animate (using the ingest-time vision hints: description / placement / animation_worthy).

The work is split into two phases so each can be reviewed at its own human gate:
  • ``author``          — write the block HTML + animate/skip decisions, leaving a marker where
                          each to-be-animated image goes. Does NOT call Agent 2.
  • ``apply_animations`` — for each ANIMATE decision, call Agent 2 and place the returned
                          animation at its marker.
``run`` chains both (kept for callers/tests that want the whole block in one go).
Self-validates (structure + eval-set) with one retry. Agent 1 is the ONLY caller of Agent 2.
"""

from __future__ import annotations

import json
import re

from ..config import Settings, get_settings
from ..llm.base import as_object
from ..llm.client import LLMClient
from ..schemas import (
    Animation,
    Block,
    BlockResult,
    ImageRef,
    VisualDecision,
    VisualVerdict,
)
from ..skills import house_style
from ..tools import validation_tools as vt
from ..tools.html_tools import html_to_text
from ..utils.io import load_visual_decision_examples, read_agent_prompt
from . import agent2_animation as agent2

_MARKER = "<!--HF_ANIM:{image_id}-->"
_MARKER_RE = re.compile(r"<!--HF_ANIM:([A-Za-z0-9_]+)-->")


def run(
    block: Block,
    *,
    memory: dict | None = None,
    client: LLMClient | None = None,
    settings: Settings | None = None,
    extra_notes: str = "",
) -> BlockResult:
    """Author the block AND apply its animations in one pass (whole-block convenience)."""
    settings = settings or get_settings()
    client = client or LLMClient(settings)
    drafted = author(block, memory=memory, client=client, settings=settings, extra_notes=extra_notes)
    return apply_animations(drafted, block.images, client=client, settings=settings)


def author(
    block: Block,
    *,
    memory: dict | None = None,
    client: LLMClient | None = None,
    settings: Settings | None = None,
    extra_notes: str = "",
    supplementary: str = "",
    previous_html: str = "",
) -> BlockResult:
    """Phase 1 — write the block HTML + animate/skip verdicts. Leaves a marker for each
    ANIMATE image (filled in later by :func:`apply_animations`). Does NOT call Agent 2.

    ``supplementary`` is optional reading material (hands-on detail the deck lacks); Agent 1 weaves
    the relevant parts into this block. It does NOT drive MCQs — those stay deck-only.

    ``previous_html`` is the block's CURRENT HTML on a refine: when set (with ``extra_notes``), the
    agent REVISES that exact block to satisfy the feedback rather than rewriting from scratch."""
    settings = settings or get_settings()
    client = client or LLMClient(settings)
    examples = load_visual_decision_examples(settings)

    user = (
        f"BLOCK {block.block_id}: {block.title}\n"
        f"LEARNING OBJECTIVES: {json.dumps(block.learning_objectives_hint)}\n\n"
        f"PRIOR-SESSION CONCEPTS (reference, do not re-explain):\n"
        f"{json.dumps((memory or {}).get('prior_concepts', []))}\n\n"
        f"IMAGES IN THIS BLOCK:\n{_images_text(block.images)}\n\n"
        f"LABELLED EXAMPLES — ANIMATE:\n{json.dumps(examples['animate'])}\n"
        f"LABELLED EXAMPLES — SKIP:\n{json.dumps(examples['skip'])}\n\n"
        f"RAW CURRICULUM HTML FOR THIS BLOCK:\n{block.content_html}"
    )
    if supplementary:
        user += (
            "\n\nSUPPLEMENTARY READING MATERIAL (the deck omits hands-on detail; this is the fuller "
            "explanation for the WHOLE session). Weave in ONLY the parts relevant to THIS block to "
            "enrich the hands-on/step-by-step detail. Do not invent unrelated content, and do not "
            "turn this into new top-level topics:\n" + html_to_text(supplementary)[:6000]
        )
    if previous_html and extra_notes:
        user += (
            "\n\nCURRENT VERSION OF THIS BLOCK — REVISE THIS EXACT HTML to satisfy the revision notes "
            "below. Change ONLY what the notes ask; keep everything else (wording, structure, and any "
            "<!--HF_ANIM:IMAGE_ID--> markers) as-is. Do not rewrite the whole block from scratch:\n"
            + previous_html[:6000]
        )
    if extra_notes:
        user += f"\n\nREVISION NOTES (apply these to the current version above):\n{extra_notes}"

    system = read_agent_prompt("agent1_system", settings) + "\n\n" + house_style()

    def generate(extra: str = "") -> dict:
        data = client.complete_json(
            purpose="agent1_content", system=system, user=user + extra,
            model=settings.agent1_model,
            image_urls=_vision_srcs(block.images),
            meta={"block_id": block.block_id, "title": block.title,
                  "first_image_id": block.images[0].image_id if block.images else None},
        )
        return as_object(data)

    data = generate()
    content_html = data.get("content_html", "")
    # Capture image decisions from the FIRST generation and keep them STABLE. The content-fidelity
    # regenerations below only fix prose — they must never churn or multiply which images animate.
    image_decisions = data.get("image_decisions", [])

    issues = vt.validate_html_structure(content_html)
    if issues and not settings.use_mock:
        data = generate("\n\nThe previous attempt had these structural problems:\n- "
                        + "\n- ".join(issues) + "\nRegenerate fixing them.")
        content_html = data.get("content_html", content_html)
        issues = vt.validate_html_structure(content_html)

    # LLM content rubric self-check (gated; catches invented content + thin prose the structural
    # rules miss). The judge gets the SOURCE so it can actually verify grounding — without it the
    # judge scores on plausibility and lets additions slip through (the cause of content drift).
    # Loop up to self_validate_retries times, re-checking after each fix, so a still-ungrounded
    # block gets another corrective pass rather than shipping.
    if not settings.use_mock and settings.self_validate_retries > 0:
        source_ctx = (
            f"BLOCK: {block.title}\nOBJECTIVES: {block.learning_objectives_hint}\n\n"
            "SOURCE MATERIAL — this is the ONLY information the block may contain. Score 'accuracy' by "
            "checking EVERY fact, example, number, tool name, step, and claim in the OUTPUT against THIS "
            "source; if the output asserts anything not grounded here, 'accuracy' MUST be low.\n"
            f"--- SOURCE (curriculum / PPT) ---\n{html_to_text(block.content_html)[:6000]}"
        )
        if supplementary:
            source_ctx += ("\n--- SUPPLEMENTARY READING (also allowed) ---\n"
                           f"{html_to_text(supplementary)[:3000]}")
        for _ in range(settings.self_validate_retries):
            verdict = vt.self_validate("content", content_html, context=source_ctx,
                                       client=client, settings=settings)
            acc = next((d for d in verdict.dimensions if d.dimension == "accuracy"), None)
            if verdict.passed and (acc is None or acc.passed):
                break  # grounded + good enough
            fixes = "; ".join(d.improvement for d in verdict.dimensions if d.improvement) \
                or verdict.summary or "Improve accuracy, clarity, and completeness."
            data = generate("\n\nA reviewer scored the previous block below the bar:\n"
                            f"{fixes}\nRegenerate the block addressing this — DELETE every fact, step, "
                            "tool, number, mechanism, or analogy that is not in the SOURCE above; keep "
                            "only source-grounded content as connected prose. Keep the same "
                            "<!--HF_ANIM:...--> animation markers, in the same places — do not add or "
                            "remove any.")
            candidate = data.get("content_html", content_html)
            if not vt.validate_html_structure(candidate):  # only accept a structurally-clean redo
                content_html = candidate
            issues = vt.validate_html_structure(content_html)

    decisions = image_decisions  # stable decisions captured from the first generation
    by_id = {im.image_id: im for im in block.images}
    verdicts: list[VisualVerdict] = []
    patterns: list[str] = list(data.get("visual_patterns_used", []))
    animate_ids: set[str] = set()

    for dec in decisions:
        iid = dec.get("image_id")
        if by_id.get(iid) is None:
            continue
        if dec.get("decision") != "send_to_agent2":
            verdicts.append(VisualVerdict(image_id=iid, decision=VisualDecision.SKIP,
                                          reason=dec.get("reason", "")))
            continue
        vtype = dec.get("visual_type") or "concept"
        verdicts.append(VisualVerdict(image_id=iid, decision=VisualDecision.ANIMATE,
                                      visual_type=vtype, reason=dec.get("reason", "")))
        patterns.append(vtype)
        animate_ids.add(iid)

    # User-provided (add-on) images MUST always animate — override any skip/missing decision.
    decided = {v.image_id for v in verdicts}
    for im in block.images:
        if (im.source_ref or "") == "user-added" and im.image_id not in animate_ids:
            vtype = "flowchart" if "flow" in (im.alt + im.description).lower() else "concept"
            # replace a SKIP verdict for this image if one exists, else add a new ANIMATE verdict
            verdicts = [v for v in verdicts if v.image_id != im.image_id]
            verdicts.append(VisualVerdict(image_id=im.image_id, decision=VisualDecision.ANIMATE,
                                          visual_type=vtype, reason="user-provided image (always animated)"))
            patterns.append(vtype)
            animate_ids.add(im.image_id)
            decided.add(im.image_id)

    # HARD CAP — at most 2 animations per block. Keep USER-PROVIDED images first (they must always
    # animate), then the best content images in order, up to 2; demote the rest to SKIP (their
    # markers are stripped below so they never become animations).
    if len(animate_ids) > 2:
        ordered = [im.image_id for im in block.images if im.image_id in animate_ids]
        user_first = ([i for i in ordered if (by_id[i].source_ref or "") == "user-added"]
                      + [i for i in ordered if (by_id[i].source_ref or "") != "user-added"])
        keep = set(user_first[:2])
        for v in verdicts:
            if v.decision == VisualDecision.ANIMATE and v.image_id not in keep:
                v.decision = VisualDecision.SKIP
        animate_ids = keep

    # Keep markers only for images we'll animate; drop markers for skipped/unknown images.
    content_html = _strip_markers_except(content_html, animate_ids)

    return BlockResult(
        block_id=block.block_id,
        title=block.title,
        content_html=content_html,
        authored_html=content_html,  # marker version — base for (re)applying/rejecting animations
        animation_used=False,        # filled by apply_animations
        visual_verdicts=verdicts,
        animations=[],
        concepts_defined=list(data.get("concepts_defined", [])),
        visual_patterns_used=patterns,
        objectives=block.learning_objectives_hint,
        quality_issues=list(issues),  # non-empty → block flagged for the final human review
    )


def apply_animations(
    result: BlockResult,
    images: list[ImageRef],
    *,
    client: LLMClient | None = None,
    settings: Settings | None = None,
    extra_notes: str = "",
    notes_by_image: dict[str, str] | None = None,
    reuse: dict[str, Animation] | None = None,
) -> BlockResult:
    """Phase 2 — for each ANIMATE verdict, place its animation at the marker.

    Idempotent: always starts from the authored (marker) HTML, so re-running cleanly REPLACES
    animations (refine) or produces none when a verdict is SKIP (reject) — never stacking.

    For SINGLE-animation edits (per-image accept/reject/improve), pass ``reuse`` (image_id ->
    existing Animation to keep untouched) and ``notes_by_image`` (image_id -> regenerate note).
    An image in ``reuse`` and NOT in ``notes_by_image`` is kept as-is (no new Agent 2 call); every
    other ANIMATE image is (re)generated. This lets one animation change while the rest stay put."""
    settings = settings or get_settings()
    client = client or LLMClient(settings)
    notes_by_image = notes_by_image or {}
    reuse = reuse or {}
    by_id = {im.image_id: im for im in images}
    old_by_id = {a.image_id: a for a in result.animations}  # current animations (for refine context)
    content_html = result.authored_html or result.content_html  # marker version is the base
    # The block prose is source-faithful, so it is the process narrative Agent 2 uses to sequence
    # the build (e.g. an n8n workflow animated node-by-node in the order the lesson explains).
    process_text = html_to_text(content_html)
    animations: list[Animation] = []

    for v in result.visual_verdicts:
        if v.decision != VisualDecision.ANIMATE:
            continue
        img = by_id.get(v.image_id)
        if img is None:
            continue
        kept = reuse.get(v.image_id)
        if kept is not None and v.image_id not in notes_by_image:
            # keep this animation exactly as-is (a single-item edit is changing a different one)
            vtype = kept.visual_type or v.visual_type or "concept"
            anim_html, ref = kept.html, kept.reference_template
        else:
            vtype = v.visual_type or "concept"
            note = notes_by_image.get(v.image_id, extra_notes)
            # on a per-image refine, hand Agent 2 the CURRENT animation so it revises that exact one
            prev = old_by_id.get(v.image_id)
            prev_html = prev.html if (prev is not None and v.image_id in notes_by_image) else ""
            anim_html = agent2.animate(img, result.title, visual_type=vtype,
                                       client=client, settings=settings, extra_notes=note,
                                       process_context=process_text, previous_html=prev_html)
            ref = agent2.reference_for(result.title, vtype)
        content_html = _place(content_html, img.image_id, anim_html, result.title)
        animations.append(Animation(image_id=v.image_id, visual_type=vtype, html=anim_html,
                                    reference_template=ref))

    content_html = _MARKER_RE.sub("", content_html)  # drop any leftover markers
    return result.model_copy(update={
        "content_html": content_html,
        "animations": animations,
        "animation_used": bool(animations),
    })


def _images_text(images: list[ImageRef]) -> str:
    if not images:
        return "(no images in this block)"
    lines = []
    for im in images:
        worthy = "unknown" if im.animation_worthy is None else ("yes" if im.animation_worthy else "no")
        lines.append(
            f"- {im.image_id}: alt={im.alt!r} caption={im.caption!r} "
            f"occurrences={im.occurrences} size={im.width}x{im.height}\n"
            f"    description: {im.description or '(none)'}\n"
            f"    illustrates / placement: {im.placement_context or im.nearby_heading or '(none)'}\n"
            f"    animation_worthy (hint): {worthy}"
        )
    return ("\n".join(lines) + "\n\nUse the 'animation_worthy' hint as guidance for your "
            "send_to_agent2 / skip decision, but make the final call yourself. Put the animation "
            "marker where the 'placement' context says the visual belongs.")


def _strip_markers_except(content_html: str, keep_ids: set[str]) -> str:
    """Remove every animation marker whose image_id is not in ``keep_ids``."""
    return _MARKER_RE.sub(lambda m: m.group(0) if m.group(1) in keep_ids else "", content_html)


def _vision_srcs(images: list[ImageRef]) -> list[str] | None:
    srcs = [im.src for im in images if im.src][:4]
    return srcs or None


def _place(content_html: str, image_id: str, animation_html: str, concept: str) -> str:
    """Replace Agent 1's marker for this image with the animation; if absent, append it
    before the key-takeaway (or at the end of the block)."""
    wrapped = (f'<div class="visual-block" aria-label="Interactive visual: {concept}">'
               f'{animation_html}</div>')
    marker = _MARKER.format(image_id=image_id)
    if marker in content_html:
        return content_html.replace(marker, wrapped)
    for anchor in ('<div class="key-takeaway"', '<div class="takeaway"'):
        i = content_html.find(anchor)
        if i != -1:
            return content_html[:i] + wrapped + content_html[i:]
    j = content_html.rfind("</div>")
    return (content_html[:j] + wrapped + content_html[j:]) if j != -1 else content_html + wrapped
