"""HTML Assembler — deterministic Jinja2 render of the final single-file tutorial.

Injects each block's tutorial HTML (animations already placed inline by Agent 1) and the MCQs
(as the JS engine's QUIZ_DATA) into the scrolling-feed shell, then appends the session-level
assessment as the concluding gated quiz step. No LLM — pure templating.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import Settings, get_settings
from ..schemas import MCQ, AssessmentQuestion, BlockResult
from ..tools.markdown import md_to_html
from ..utils.io import slug


def _env(settings: Settings) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(settings.templates_path)),
        autoescape=select_autoescape(enabled_extensions=("html", "j2"), default=False),
    )


def _quiz_data(blocks: list[BlockResult], mcqs: dict[int, list[MCQ]]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for idx, b in enumerate(blocks):
        qs = mcqs.get(b.block_id, [])
        out[str(idx)] = [m.to_quiz_entry() for m in qs]
    return out


def render(
    *,
    session_title: str,
    blocks: list[BlockResult],
    mcqs: dict[int, list[MCQ]],
    final_assessment: list[AssessmentQuestion] | None = None,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    final_assessment = final_assessment or []
    tmpl_blocks = [{"block_id": b.block_id, "title": b.title, "content_html": b.content_html}
                   for b in blocks]
    assessment = [{**q.to_entry(), "answer_html": md_to_html(q.answer)} for q in final_assessment]
    html = _env(settings).get_template("base_tutorial.html.j2").render(
        title=session_title,
        blocks=tmpl_blocks,
        quiz_data=_quiz_data(blocks, mcqs),
        assessment=assessment,
        has_final_assessment=bool(assessment),
    )
    if "</html>" not in html or "QUIZ_DATA" not in html:
        raise ValueError("Assembled HTML failed validation (missing structural markers).")
    return html


def write_tutorial(html: str, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def output_filename(course: str, session: str) -> str:
    return f"{slug(course)}_{slug(session)}_tutorial.html"


def publish_tutorial(html: str, course: str, session: str,
                     settings: Settings | None = None) -> Path:
    """Write the finished tutorial into the canonical library:
    ``generated_tutorials/<course-slug>/<session-slug>.html``.

    Versions are kept: the first build is ``<session>.html``; later rebuilds of the same
    course+session become ``<session>_v2.html``, ``<session>_v3.html``, … (never overwritten).
    """
    settings = settings or get_settings()
    course_dir = settings.generated_tutorials_path / slug(course)
    course_dir.mkdir(parents=True, exist_ok=True)
    base = slug(session)
    path = course_dir / f"{base}.html"
    version = 2
    while path.exists():
        path = course_dir / f"{base}_v{version}.html"
        version += 1
    path.write_text(html, encoding="utf-8")
    return path
