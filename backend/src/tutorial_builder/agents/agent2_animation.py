"""Agent 2 — Animation Generator (vision).

Called ONLY by Agent 1. Receives one concept-bearing image and generates a self-contained,
auto-playing, looped step-by-step reveal animation in the style of the reference library
(``reference_animations/waterfall-model-animation.html`` etc.). Namespaced by image_id so
multiple animations coexist on one page. Self-validates (rule-based structural checks +
eval-set LLM judge against eval-sets/visual/) with one bounded retry on each.
"""

from __future__ import annotations

from ..config import Settings, get_settings
from ..llm.client import LLMClient
from ..schemas import ImageRef
from ..skills import visual_patterns
from ..tools import validation_tools as vt
from ..utils.io import read_agent_prompt

# Reference-library patterns keyed by keyword found in the concept/title.
_REFERENCE_FILES = {
    "waterfall": "waterfall-model-animation.html",
    "agile": "agile-model-animation.html",
    "scrum": "agile-model-animation.html",
    "v-model": "v-model-animation.html",
    "v model": "v-model-animation.html",
}

_MAX_REF_CHARS = 4000  # include a trimmed reference as a structural template


def reference_for(concept: str, visual_type: str | None) -> str | None:
    text = (concept or "").lower()
    for kw, fname in _REFERENCE_FILES.items():
        if kw in text:
            return fname
    return None


def _reference_html(concept: str, settings: Settings) -> tuple[str | None, str]:
    fname = reference_for(concept, None)
    if not fname:
        return None, ""
    path = settings.reference_animations_path / fname
    try:
        return fname, path.read_text(encoding="utf-8")[:_MAX_REF_CHARS]
    except OSError:
        return fname, ""


def animate(
    image: ImageRef,
    concept: str,
    visual_type: str | None = None,
    *,
    client: LLMClient | None = None,
    settings: Settings | None = None,
    extra_notes: str = "",
    process_context: str = "",
    previous_html: str = "",
) -> str:
    """Return the animation HTML fragment for one image (namespaced by image_id).

    The animation is built from the IMAGE ITSELF, its alt/caption, and — when provided —
    ``process_context``: the lesson's source-faithful description of the process the image shows,
    so the reveal is sequenced to match how the material explains it (e.g. an n8n workflow built
    node by node). ``concept`` is used solely to pick a reference style pattern, not as content.
    """
    settings = settings or get_settings()
    client = client or LLMClient(settings)

    ref_name, ref_html = _reference_html(concept, settings)
    ref_block = (f"\n\nREFERENCE PATTERN ({ref_name}) — match this structure/style only:\n{ref_html}"
                 if ref_html else "")

    process_block = (
        f"\nPROCESS DESCRIBED IN THE LESSON (sequence and build the animation to match this "
        f"process, in this order):\n{process_context.strip()}\n" if process_context.strip() else ""
    )
    allowed = ("what this image shows and the described process above"
               if process_block else "what this image shows and its alt/caption above")
    base_user = (
        f"IMAGE_ID: {image.image_id}\n"
        f"VISUAL TYPE: {visual_type or 'concept'}\n"
        f"IMAGE ALT/CAPTION: {image.alt} | {image.caption}\n"
        f"SOURCE IMAGE (recreate natively as an animation, do not embed the raw image): {image.src}\n"
        f"{process_block}"
        f"Base the animation ONLY on {allowed}. Do NOT add steps, labels, phases, nodes, or facts "
        f"that are not visible in the image or stated in that description.\n"
        f"Use a mostly WHITE background (match the source image's light background); keep it clean "
        f"so it blends into the tutorial page — no dark or coloured full-bleed backgrounds."
        f"{ref_block}"
    )
    if extra_notes.strip():
        base_user += (
            "\n\n=== REVISION REQUEST (HIGHEST PRIORITY) ===\n"
            "This is a REGENERATION. A reviewer looked at the previous animation and asked for these "
            "SPECIFIC changes. You MUST apply them exactly and make the change clearly visible in the "
            "new animation — this instruction overrides your default choices (while still obeying the "
            "hard rules: source-faithful, labelled, auto-loop, no buttons, namespaced):\n"
            f"\"{extra_notes.strip()}\"\n"
            "Produce a NOTICEABLY DIFFERENT animation that addresses the request above."
        )
        if previous_html.strip():
            base_user += (
                "\n\nCURRENT ANIMATION (this is what you produced before — REVISE THIS to satisfy the "
                "request above; keep what already works, change only what's asked, and keep it "
                "self-contained + namespaced by the image_id):\n" + previous_html.strip()[:5000]
            )
    system = read_agent_prompt("agent2_system", settings) + "\n\n" + visual_patterns()

    def generate(extra: str = "") -> str:
        return client.complete_text(
            purpose="agent2_animation", system=system, user=base_user + extra,
            model=settings.agent2_model,
            image_urls=[image.src] if image.src else None,
            meta={"image_id": image.image_id, "concept": concept},
        ).strip()

    html = _strip_fences(generate())
    issues = vt.validate_animation_html(html, image.image_id)
    if issues and not settings.use_mock:
        html = _strip_fences(generate(
            "\n\nThe previous attempt had these problems:\n- " + "\n- ".join(issues)
            + "\nRegenerate the animation fixing them."))

    # Eval-set self-validation (LLM judge against eval-sets/visual/) — one bounded retry
    # when the animation scores below the rubric threshold. Skipped under the offline mock.
    if not settings.use_mock and settings.self_validate_retries > 0:
        verdict = vt.self_validate(
            "visual", html,
            context=(f"CONCEPT: {concept}\nVISUAL TYPE: {visual_type or 'concept'}\n"
                     f"IMAGE: {image.alt} | {image.caption}"
                     + (f"\nPROCESS DESCRIBED IN THE LESSON:\n{process_context.strip()}"
                        if process_context.strip() else "")),
            client=client, settings=settings,
        )
        if not verdict.passed:
            fixes = "; ".join(d.improvement for d in verdict.dimensions if d.improvement) \
                or verdict.summary or "Improve the staged reveal, fidelity, and namespacing."
            html = _strip_fences(generate(
                "\n\nA reviewer scored the previous animation below the bar:\n"
                f"{fixes}\nRegenerate the animation addressing this feedback."))
    return html


def _strip_fences(html: str) -> str:
    h = html.strip()
    if h.startswith("```"):
        h = h.split("\n", 1)[-1]
        if h.endswith("```"):
            h = h[: h.rfind("```")]
    return h.strip()
