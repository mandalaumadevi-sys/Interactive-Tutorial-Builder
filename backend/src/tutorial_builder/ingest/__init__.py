"""Stage 0 — Ingestion. HTML and PPTX both converge on one NormalizedDocument.

A deck rarely contains the whole lesson — hands-on detail, prose, and key diagrams often live
outside it. So ingestion also accepts optional **add-ons** (passed via metadata):
  • ``extra_material_text`` / ``extra_material_path`` — extra reading material (Markdown/text/HTML)
    that is merged into the source so the divider + content agents cover it too.
  • ``extra_image_paths`` — extra images (e.g. a final workflow diagram missing from the deck)
    that are added to the asset pool, described, and placed/animated like any other image.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from bs4 import BeautifulSoup

from ..config import Settings, get_settings
from ..schemas import ImageRef, NormalizedDocument, SessionMeta
from ..tools.html_tools import session_title
from ..tools.markdown import md_to_html


def ingest(raw_path: str, input_type: str, *, run_id: str | None = None,
           metadata: dict | None = None, settings: Settings | None = None) -> NormalizedDocument:
    settings = settings or get_settings()
    path = Path(raw_path)
    metadata = metadata or {}
    if input_type == "pptx":
        from .pptx_loader import pptx_to_normalized

        doc = pptx_to_normalized(path, run_id=run_id, metadata=metadata, settings=settings)
    else:
        doc = _html_to_normalized(path, metadata=metadata)

    # Merge ONLY extra images into the source (so they're divided, described, placed/animated).
    # The reading material is deliberately NOT merged here — it stays supplementary so that block
    # division and the per-block MCQs are derived from the PPT/deck content ONLY. The material is
    # surfaced separately via material_html() and fed to Agent 1 to enrich hands-on detail.
    _merge_addon_images(doc, metadata, run_id=run_id, settings=settings)

    # Stage 0.5 — vision-describe every extracted image (placement + animation hints).
    # Identical for both flows; degrades to heuristics when pixels aren't reachable / mock.
    if doc.assets:
        from .image_describer import describe_images

        doc.assets = describe_images(doc.assets, settings=settings)
    return doc


def _merge_addon_images(doc: NormalizedDocument, metadata: dict, *, run_id: str | None,
                        settings: Settings) -> None:
    """Append extra images (from metadata) into ``doc`` in place — no heading, so they attach to
    the last deck section/block and get described + placed like any other image."""
    image_paths = metadata.get("extra_image_paths") or []
    if not image_paths:
        return
    parts: list[str] = []
    n = len(doc.assets)
    for p in image_paths:
        src = Path(p)
        if not src.is_file():
            continue
        n += 1
        alt = src.stem.replace("_", " ").replace("-", " ").strip()
        doc.assets.append(ImageRef(
            image_id=f"addon_{n:02d}", src=str(src), alt=alt,
            source_ref="user-added", format=(src.suffix.lstrip(".") or "png"),
        ))
        parts.append(f'<img src="{escape(str(src))}" alt="{escape(alt)}" '
                     f'data-occurrences="1" data-source-ref="user-added"/>')
    if parts:
        doc.normalized_html = (doc.normalized_html or "").rstrip() + "\n" + "\n".join(parts)


def material_html(metadata: dict) -> str:
    """Convert the supplied reading material (file or pasted text) to HTML.

    This is SUPPLEMENTARY — fed to Agent 1 to enrich content/hands-on, never used for block
    division or MCQ generation (those stay strictly PPT/deck-derived)."""
    path = metadata.get("extra_material_path")
    if path and Path(path).is_file():
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
        ext = Path(path).suffix.lower()
        if ext in (".html", ".htm"):
            soup = BeautifulSoup(raw, "lxml")
            body = soup.body or soup
            return "".join(str(c) for c in body.contents).strip()
        return md_to_html(raw)  # .md / .txt / no-extension → Markdown
    text = (metadata.get("extra_material_text") or "").strip()
    return md_to_html(text) if text else ""


def _html_to_normalized(path: Path, *, metadata: dict) -> NormalizedDocument:
    raw = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "lxml")
    for noise in soup(["script", "style", "link", "meta", "noscript"]):
        noise.decompose()
    body = soup.body or soup
    normalized_html = "".join(str(c) for c in body.contents).strip() or raw

    assets = _inventory_images(soup)
    name = metadata.get("session_name") or session_title(raw)
    meta = SessionMeta(
        session_name=name,
        course_name=metadata.get("course_name", "Course"),
        source_type="html",
        source_filename=path.name,
        learning_objectives=metadata.get("learning_objectives", []),
    )
    return NormalizedDocument(session_meta=meta, normalized_html=normalized_html, assets=assets)


def _inventory_images(soup: BeautifulSoup) -> list[ImageRef]:
    counts: dict[str, int] = {}
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if src:
            counts[src] = counts.get(src, 0) + 1
    assets: list[ImageRef] = []
    seen: set[str] = set()
    n = 0
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src or src in seen:
            continue
        seen.add(src)
        n += 1
        assets.append(ImageRef(
            image_id=f"img_{n:02d}",
            src=src,
            alt=(img.get("alt") or "").strip(),
            occurrences=counts.get(src, 1),
        ))
    return assets
