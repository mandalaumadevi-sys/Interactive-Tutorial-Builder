"""Render Markdown answers to safe HTML for the tutorial.

Used for the descriptive assessment answers so headings, lists, bold, and line breaks
display properly. Raw HTML in the source is escaped (commonmark preset, html=False), so
model-generated text can't inject markup — only the markdown structure becomes tags.
"""

from __future__ import annotations

import html as _html


def md_to_html(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    try:
        from markdown_it import MarkdownIt
        # html=False → raw HTML in the source is escaped (no script/markup injection).
        return MarkdownIt("commonmark", {"html": False}).render(text).strip()
    except Exception:  # noqa: BLE001 — fall back to escaped paragraphs + line breaks
        paras = [p.strip() for p in _html.escape(text).split("\n\n") if p.strip()]
        return "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paras)
