"""Stage 0.5 — Image description (vision).

After ingestion, EVERY extracted image is captioned so downstream agents know:
  • WHERE it belongs (``placement_context`` — which idea it illustrates), and
  • WHETHER it is concept-bearing enough to animate (``animation_worthy``).

Runs for both ingestion flows (PPTX and HTML). When the image pixels are reachable
(a local asset file, a data: URI, or an http(s) URL) a vision model is used; otherwise it
degrades to an alt/caption/heading heuristic so the pipeline always proceeds. Under the
offline mock the heuristic is used directly (no LLM, no cost).
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..config import Settings, get_settings
from ..llm.base import as_object
from ..llm.client import LLMClient
from ..schemas import ImageRef

_SYSTEM = (
    "You analyse a single image for a tutorial builder. Look at the image and describe it for a "
    "downstream content author and animator.\n\n"
    "Return ONLY JSON:\n"
    '{ "description": "<1-2 sentences: what the image depicts>",\n'
    '  "placement_context": "<one short phrase: which idea it illustrates / where it belongs>",\n'
    '  "animation_worthy": <true|false>,\n'
    '  "visual_type": "flowchart|lifecycle|architecture|comparison|process|concept|decorative|'
    'screenshot|logo" }\n\n'
    "animation_worthy = true ONLY for concept-bearing diagrams (flowchart, lifecycle, architecture, "
    "comparison, multi-step process). false for logos, icons, decorative photos, bullet screenshots, "
    "or repeated page chrome."
)

# Keywords that strongly suggest a concept-bearing (animatable) diagram.
_ANIM_KEYWORDS = (
    "diagram", "flow", "flowchart", "lifecycle", "life cycle", "architecture", "model",
    "process", "pipeline", "cycle", "comparison", "versus", " vs ", "phase", "stage",
    "workflow", "sequence", "timeline", "structure",
)
_SKIP_KEYWORDS = ("logo", "icon", "screenshot", "photo", "headshot", "avatar", "banner", "decorative")


def describe_images(
    assets: list[ImageRef],
    *,
    client: LLMClient | None = None,
    settings: Settings | None = None,
) -> list[ImageRef]:
    """Return copies of ``assets`` enriched with description / placement / animation hints.

    To stay fast and cheap on image-heavy decks, ONLY the most likely concept images get a
    vision call — deduped by source, limited to ``settings.max_vision_describe``, and run in
    parallel. Everything else (decorative, duplicated, or over the cap) gets a free heuristic.
    """
    settings = settings or get_settings()
    client = client or LLMClient(settings)

    # Pick vision candidates: reachable, heuristically concept-bearing, not heavily duplicated,
    # one per unique src, capped. (Skipped entirely under the offline mock.)
    candidates: list[ImageRef] = []
    seen_src: set[str] = set()
    if not settings.use_mock:
        # Describe user-provided images first so they're never crowded out by the cap.
        ordered = sorted(assets, key=lambda im: 0 if (im.source_ref or "") == "user-added" else 1)
        for im in ordered:
            if im.src in seen_src:
                continue
            if _reachable(im.src) and _heuristic_worthy(im):
                candidates.append(im)
                seen_src.add(im.src)
            if len(candidates) >= settings.max_vision_describe:
                break

    # Vision-describe candidates in parallel; map results back by src.
    described: dict[str, dict] = {}
    if candidates:
        with ThreadPoolExecutor(max_workers=min(6, len(candidates))) as pool:
            futs = {pool.submit(_vision_describe, im, client, settings): im.src for im in candidates}
            for f in futs:
                res = f.result()
                if res:
                    described[futs[f]] = res

    out: list[ImageRef] = []
    for im in assets:
        if im.src in described:
            out.append(im.model_copy(update=described[im.src]))
        else:
            out.append(im.model_copy(
                update=_heuristic(im, source="mock" if settings.use_mock else "heuristic")))
    return out


def _vision_describe(im: ImageRef, client: LLMClient, settings: Settings) -> dict | None:
    """One vision call for one image → update dict, or None on failure (caller uses heuristic)."""
    try:
        data = as_object(client.complete_json(
            purpose="image_describe", system=_SYSTEM,
            user=_context_text(im), model=settings.vision_model,
            image_urls=[im.src], meta=_heuristic_meta(im),
        ))
    except Exception:  # noqa: BLE001 — vision failure must never break ingestion
        return None
    worthy = data.get("animation_worthy")
    if isinstance(worthy, str):
        worthy = worthy.strip().lower() in ("true", "yes", "1")
    return {
        "description": (data.get("description") or "").strip(),
        "placement_context": (data.get("placement_context") or im.nearby_heading or "").strip(),
        "animation_worthy": bool(worthy) if worthy is not None else _heuristic_worthy(im),
        "description_source": "vision",
        "alt": im.alt or (data.get("visual_type") or "").strip(),
    }


def _reachable(src: str) -> bool:
    if not src:
        return False
    if src.startswith(("http://", "https://", "data:")):
        return True
    try:
        return Path(src).is_file()
    except OSError:
        return False


def _context_text(im: ImageRef) -> str:
    return (
        "Image context (text the deck/page gave near this image):\n"
        f"- alt: {im.alt or '(none)'}\n"
        f"- caption: {im.caption or '(none)'}\n"
        f"- nearby heading: {im.nearby_heading or '(none)'}\n\n"
        "Describe the IMAGE ITSELF (not just the text above)."
    )


def _blob(im: ImageRef) -> str:
    return f"{im.alt} {im.caption} {im.nearby_heading} {im.src}".lower()


def _heuristic_worthy(im: ImageRef) -> bool:
    if (im.source_ref or "") == "user-added":
        return True  # user-provided images always count as concept images (always animated)
    text = _blob(im)
    if any(k in text for k in _SKIP_KEYWORDS):
        return False
    if im.occurrences and im.occurrences > 2:  # repeated → chrome/decorative
        return False
    return any(k in text for k in _ANIM_KEYWORDS)


def _heuristic(im: ImageRef, *, source: str) -> dict:
    label = (im.alt or im.caption or im.nearby_heading or "a visual").strip()
    label = re.sub(r"\s+", " ", label)[:160]
    worthy = _heuristic_worthy(im)
    prefix = "[mock] " if source == "mock" else ""
    return {
        "description": f"{prefix}{label}.",
        "placement_context": (im.nearby_heading or label).strip(),
        "animation_worthy": worthy,
        "description_source": source,
    }


def _heuristic_meta(im: ImageRef) -> dict:
    # Passed to the mock LLM so its canned output reflects this image's heuristic hint.
    return {"alt": im.alt, "nearby_heading": im.nearby_heading,
            "worthy_hint": _heuristic_worthy(im)}
