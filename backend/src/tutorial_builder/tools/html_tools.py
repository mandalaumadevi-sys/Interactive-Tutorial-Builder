"""BeautifulSoup utilities — the deterministic HTML parser (no LLM, no judgment).

Splits a curriculum HTML document at hard heading boundaries into candidate content
blocks and inventories each block's images with the context an LLM needs to judge
concept-relevance.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from ..schemas import CandidateBlock, ImageRef

# Slide-deck pages: each is a self-contained section (heading + content nested inside).
SLIDE_CONTAINER_CLASS = "os-page"


def html_to_text(html: str) -> str:
    return BeautifulSoup(html or "", "lxml").get_text(" ", strip=True)


def _word_count(html: str) -> int:
    return len(html_to_text(html).split())


def _dim(style: str, prop: str) -> int | None:
    m = re.search(rf"{prop}\s*:\s*(\d+(?:\.\d+)?)px", style or "")
    return int(float(m.group(1))) if m else None


def _global_occurrences(soup: BeautifulSoup) -> dict[str, int]:
    counts: dict[str, int] = {}
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if src:
            counts[src] = counts.get(src, 0) + 1
    return counts


def _caption_for(img: Tag) -> str:
    fig = img.find_parent("figure")
    if fig:
        cap = fig.find("figcaption")
        if cap:
            return cap.get_text(" ", strip=True)[:200]
    nxt = img.find_next(["figcaption", "small", "em"])
    return nxt.get_text(" ", strip=True)[:200] if nxt else ""


def _heading_text(el: Tag) -> str:
    for h in el.find_all_previous(["h1", "h2", "h3"]):
        t = h.get_text(" ", strip=True)
        if t:
            return t[:160]
    return ""


def _extract_images(container: Tag, occ: dict[str, int], block_id: int) -> list[ImageRef]:
    images: list[ImageRef] = []
    seen: set[str] = set()
    for img in container.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src or src in seen:
            continue
        seen.add(src)
        style = img.get("style", "")
        images.append(ImageRef(
            image_id=f"img_b{block_id}_{len(images) + 1:02d}",
            src=src,
            alt=(img.get("alt") or "").strip(),
            caption=_caption_for(img),
            nearby_heading=_heading_text(img),
            width=_dim(style, "width"),
            height=_dim(style, "height"),
            occurrences=occ.get(src, 1),
            # preserve the user-added marker so Agent 1's "always animate user images" override fires
            source_ref=(img.get("data-source-ref") or "").strip(),
        ))
    return images


def _block_images(content_html: str, occ: dict[str, int], block_id: int) -> list[ImageRef]:
    return _extract_images(BeautifulSoup(content_html or "", "lxml"), occ, block_id)


def parse_blocks(html: str) -> list[CandidateBlock]:
    """Rule-based split into candidate blocks. No reasoning.

    - Slide decks (``.os-page`` containers): each slide is one candidate block.
    - Prose articles: split at hard ``<h1>``/``<h2>`` boundaries (content follows as siblings).
    - Headingless docs: the whole document is one candidate block.
    """
    soup = BeautifulSoup(html, "lxml")
    for noise in soup(["script", "style", "link", "meta", "noscript"]):
        noise.decompose()

    occ = _global_occurrences(soup)

    slides = soup.find_all("div", class_=SLIDE_CONTAINER_CLASS)
    if slides:
        return _slide_blocks(slides, occ)

    root = soup.body or soup
    boundaries = [el for el in root.find_all(["h1", "h2"]) if el.get_text(strip=True)]
    boundary_ids = {id(el) for el in boundaries}

    if not boundaries:
        body_html = "".join(str(c) for c in root.contents)
        title = soup.title.get_text(strip=True) if soup.title else "Session"
        return [CandidateBlock(block_id=1, title=title, content_html=body_html,
                               images=_block_images(body_html, occ, 1),
                               word_count=_word_count(body_html))]

    blocks: list[CandidateBlock] = []
    for i, head in enumerate(boundaries, start=1):
        parts: list[str] = [str(head)]
        for node in head.next_siblings:
            if isinstance(node, Tag) and id(node) in boundary_ids:
                break
            parts.append(str(node))
        content_html = "".join(parts)
        blocks.append(CandidateBlock(
            block_id=i,
            title=head.get_text(" ", strip=True),
            content_html=content_html,
            images=_block_images(content_html, occ, i),
            word_count=_word_count(content_html),
        ))
    return blocks


def _slide_blocks(slides: list[Tag], occ: dict[str, int]) -> list[CandidateBlock]:
    blocks: list[CandidateBlock] = []
    for i, slide in enumerate(slides, start=1):
        head = slide.find(["h1", "h2", "h3", "h4"])
        title = head.get_text(" ", strip=True) if head else f"Slide {i}"
        content_html = "".join(str(c) for c in slide.contents)
        blocks.append(CandidateBlock(
            block_id=i,
            title=title or f"Slide {i}",
            content_html=content_html,
            images=_extract_images(slide, occ, i),
            word_count=_word_count(content_html),
        ))
    return blocks


def heading_tree(html: str) -> list[dict]:
    soup = BeautifulSoup(html or "", "lxml")
    out: list[dict] = []
    for h in soup.find_all(["h1", "h2", "h3", "h4"]):
        t = h.get_text(" ", strip=True)
        if t:
            out.append({"level": int(h.name[1]), "text": t[:200]})
    return out


def session_title(html: str) -> str:
    soup = BeautifulSoup(html or "", "lxml")
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(" ", strip=True)
    h2 = soup.find("h2")
    if h2 and h2.get_text(strip=True):
        return h2.get_text(" ", strip=True)
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)
    return "Session"
