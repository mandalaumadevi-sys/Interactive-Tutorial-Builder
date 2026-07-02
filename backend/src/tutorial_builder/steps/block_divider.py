"""Block Divider (LLM) — group source sections into final, cohesive teaching blocks.

Reads the user-maintained division prompt (``prompts/Block_division.md``, with its worked examples
and merge/split rules) and applies it to the session's sections. Many real inputs use flat headings
(e.g. every section is an ``<h1>``), so the deterministic parser emits one *section* per heading;
this step groups those sections into a small number of cohesive blocks (target 4–5).

It does NOT rewrite content. The model only decides which section ids group together; the system
rebuilds each block's exact HTML (and image inventory) from those ids, so no content is ever lost.
Self-validates (rule-based + eval-set) with one corrective re-run.
"""

from __future__ import annotations

import json

from bs4 import BeautifulSoup

from ..config import Settings, get_settings
from ..llm.client import LLMClient
from ..schemas import (
    Block,
    BlockDivision,
    CandidateBlock,
    HeadingNode,
    ImageRef,
    SelfValidation,
)
from ..tools import validation_tools as vt
from ..tools.html_tools import heading_tree, html_to_text
from ..utils.io import read_agent_prompt

MAX_WORDS = 900
PREVIEW_CHARS = 1200


def run(
    candidates: list[CandidateBlock],
    objectives: list[str],
    *,
    feedback: str = "",
    previous: list[Block] | None = None,
    normalized_html: str = "",
    session_name: str = "Session",
    guidance: str = "",
    client: LLMClient | None = None,
    settings: Settings | None = None,
) -> tuple[BlockDivision, SelfValidation]:
    settings = settings or get_settings()
    client = client or LLMClient(settings)
    lo, hi = settings.min_blocks, settings.max_blocks

    sections_json = json.dumps([
        {"id": c.block_id, "title": c.title, "word_count": c.word_count,
         "preview": html_to_text(c.content_html)[:PREVIEW_CHARS],
         "image_alts": [im.alt for im in c.images if im.alt]}
        for c in candidates
    ], indent=2)

    if feedback and previous:
        system = read_agent_prompt("block_refine_with_feedback", settings)
        user = (f"The human reviewer provided this feedback:\n\"{feedback}\"\n\n"
                f"Previous blocks:\n{json.dumps([_block_min(b) for b in previous], indent=2)}\n\n"
                f"SOURCE SECTIONS (group these by id):\n{sections_json}\n\n"
                + _output_override(lo, hi, session_name)
                + "\nRevise ONLY the blocks mentioned in the feedback; keep the rest unchanged.")
    else:
        system = settings.block_division_prompt_file.read_text(encoding="utf-8")
        user = (
            f"SOURCE SECTIONS — the document uses flat headings, so treat each of these as one "
            f"indivisible section, in order. Apply the rules and worked examples above to GROUP "
            f"them into cohesive blocks:\n{sections_json}\n\n"
            f"LEARNING OBJECTIVES (hints): {json.dumps(objectives)}\n\n"
            + _output_override(lo, hi, session_name)
        )

    if guidance:
        user += "\n\n" + guidance

    src_map = _src_image_map(candidates)

    def generate(extra: str = "") -> tuple[list[Block], str, list[dict]]:
        data = client.complete_json(
            purpose="block_divide", system=system, user=user + extra,
            model=settings.divider_model,
            meta={"candidate_count": len(candidates), "session_name": session_name,
                  "target_blocks": hi, "min_blocks": lo, "max_blocks": hi,
                  "has_feedback": bool(feedback)},
        )
        if isinstance(data, list):
            rows, reasoning, tree = data, "", []
        else:
            rows = data.get("blocks", [])
            reasoning = data.get("division_reasoning", "")
            tree = data.get("heading_tree", [])
        return _to_blocks(rows, candidates, src_map), reasoning, tree

    blocks, reasoning, tree = generate()
    issues = _rule_checks(blocks, objectives, lo, hi)
    if issues and not settings.use_mock:
        blocks, reasoning, tree = generate(
            "\n\nThe previous attempt had these problems:\n- " + "\n- ".join(issues)
            + f"\nFix them. Remember: GROUP into {lo}-{hi} blocks (aim for 4-5), cover every "
            "section exactly once, and keep each concept whole."
        )
        issues = _rule_checks(blocks, objectives, lo, hi)

    validation = vt.self_validate(
        "block_divider",
        json.dumps([{"title": b.title, "objectives": b.learning_objectives_hint,
                     "word_count": b.word_count_estimate} for b in blocks]),
        context=f"Objectives: {objectives}",
        client=client, settings=settings,
    )
    if issues:
        validation.passed = False
        validation.summary = (validation.summary + " | rule issues: " + "; ".join(issues)).strip()

    heading = ([HeadingNode(**h) for h in tree if isinstance(h, dict) and "text" in h]
               or [HeadingNode(**h) for h in heading_tree(normalized_html)])
    division = BlockDivision(
        session_name=session_name,
        total_blocks=len(blocks),
        heading_tree=heading,
        division_reasoning=reasoning,
        blocks=blocks,
    )
    return division, validation


def _output_override(lo: int, hi: int, session_name: str) -> str:
    return (
        "OUTPUT OVERRIDE — follow all the rules and worked examples above, but return THIS exact "
        "JSON shape (do NOT include content_html; the system rebuilds exact HTML from the section "
        "ids you reference, so no content is lost):\n"
        "{\n"
        f'  "session_name": "{session_name}",\n'
        '  "total_blocks": <int>,\n'
        '  "heading_tree": [{"level": 1, "text": "..."}],\n'
        '  "division_reasoning": "why each merge / split decision",\n'
        '  "blocks": [\n'
        '    {"title": "learner-facing title", "source_section_ids": [1, 2, 3],\n'
        '     "objectives": ["2-4 learner-facing objectives"]}\n'
        "  ]\n"
        "}\n"
        f"REQUIREMENTS: GROUP every source section into exactly one block, preserving order. "
        f"Produce {lo}-{hi} blocks total (aim for 4-5); NEVER exceed {hi}. Merge the intro/agenda "
        "and small related sections; keep each model/concept (e.g. Waterfall, Agile, V-Model) whole."
    )


def _block_min(b: Block) -> dict:
    return {"title": b.title, "objectives": b.learning_objectives_hint}


def _src_image_map(candidates: list[CandidateBlock]) -> dict[str, ImageRef]:
    out: dict[str, ImageRef] = {}
    for c in candidates:
        for im in c.images:
            out.setdefault(im.src, im)
    return out


def _section_ids(row: dict, cand_by_title: dict[str, int]) -> list[int]:
    """Resolve a returned block's source section ids (tolerant of field-name variants)."""
    for key in ("source_section_ids", "source_block_ids", "section_ids"):
        ids = row.get(key)
        if ids:
            return [int(i) for i in ids if isinstance(i, int) or str(i).isdigit()]
    # fall back to matching section titles (h2_sections_included)
    titles = row.get("h2_sections_included") or row.get("sections") or []
    return [cand_by_title[t] for t in titles if t in cand_by_title]


def _to_blocks(rows, candidates, src_map) -> list[Block]:
    cand_by_id = {c.block_id: c for c in candidates}
    cand_by_title = {c.title: c.block_id for c in candidates}
    blocks: list[Block] = []
    for i, r in enumerate(rows, start=1):
        ids = _section_ids(r, cand_by_title)
        content_html = r.get("content_html", "")
        if not content_html and ids:
            content_html = "".join(cand_by_id[s].content_html for s in ids if s in cand_by_id)
        sections = [cand_by_id[s].title for s in ids if s in cand_by_id]
        images = _images_from_html(content_html, src_map, i)
        blocks.append(Block(
            block_id=i,
            title=r.get("title", f"Block {i}"),
            h2_sections_included=sections,
            content_html=content_html,
            images=images,
            word_count_estimate=len(html_to_text(content_html).split()),
            learning_objectives_hint=r.get("objectives", []),
        ))
    return blocks


def _images_from_html(html: str, src_map: dict[str, ImageRef], block_id: int) -> list[ImageRef]:
    imgs: list[ImageRef] = []
    seen: set[str] = set()
    for n, img in enumerate(BeautifulSoup(html or "", "lxml").find_all("img"), start=1):
        src = (img.get("src") or "").strip()
        if not src or src in seen:
            continue
        seen.add(src)
        ref = src_map.get(src)
        if ref is not None:
            imgs.append(ref.model_copy(update={"image_id": f"img_b{block_id}_{n:02d}"}))
        else:
            imgs.append(ImageRef(image_id=f"img_b{block_id}_{n:02d}", src=src,
                                 alt=(img.get("alt") or "").strip()))
    return imgs


def _rule_checks(blocks: list[Block], objectives: list[str], lo: int, hi: int) -> list[str]:
    issues: list[str] = []
    if not (lo <= len(blocks) <= hi):
        issues.append(f"block count {len(blocks)} outside target {lo}-{hi}")
    for b in blocks:
        if not b.title:
            issues.append(f"block {b.block_id} missing title")
        if not b.content_html.strip():
            issues.append(f"block {b.block_id} missing content (no source sections grouped)")
        if b.word_count_estimate and b.word_count_estimate > MAX_WORDS:
            issues.append(f"block {b.block_id} very long ({b.word_count_estimate}w) — consider splitting")
    if objectives:
        covered = {o for b in blocks for o in b.learning_objectives_hint}
        missing = [o for o in objectives if o not in covered]
        if missing:
            issues.append(f"objectives not mapped to any block: {missing}")
    return issues
