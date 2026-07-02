"""FastAPI application — REST + SSE for the tutorial builder.

The web UI is a separate static frontend (see ../../../../frontend/), served on its
own port and pointed at this API via CORS. This app exposes only the JSON/SSE API.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from ..schemas import BlockDivision
from ..utils.events import RUN_BUS
from .run_manager import MANAGER
from .schemas import (
    AnimationEditRequest, AssessmentEditRequest, BlockReviewRequest, ContentEditRequest,
    FinalProceedRequest, FinalReviewRequest, McqEditRequest, StageReviewRequest, StartResponse,
)


def create_app() -> FastAPI:
    app = FastAPI(title="Interactive Tutorial Builder", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])

    # ── builds ──
    @app.post("/api/builds", response_model=StartResponse)
    async def start_build(
        deck: UploadFile,
        metadata: str = Form("{}"),
        material: UploadFile | None = File(None),   # optional extra reading material (md/txt/html)
        material_text: str = Form(""),              # …or pasted instead of a file
        images: list[UploadFile] = File([]),        # optional extra images (e.g. workflow diagram)
    ) -> StartResponse:
        try:
            meta = json.loads(metadata or "{}")
        except json.JSONDecodeError as err:
            raise HTTPException(422, f"Invalid metadata JSON: {err}")
        if not (meta.get("course_name") or "").strip():
            raise HTTPException(422, "course_name is required")
        if not (meta.get("session_name") or "").strip():
            raise HTTPException(422, "session_name is required")
        raw = await deck.read()
        if not raw:
            raise HTTPException(422, "Empty file")
        material_bytes = await material.read() if material is not None else None
        image_files = [(img.filename or f"image_{i}.png", await img.read())
                       for i, img in enumerate(images or [], start=1)]
        image_files = [(n, b) for (n, b) in image_files if b]
        info = MANAGER.start_build(
            raw, deck.filename or "input.html", meta,
            material=material_bytes, material_filename=(material.filename if material else ""),
            material_text=material_text, images=image_files,
        )
        return StartResponse(run_id=info.run_id, status=info.status.value)

    @app.get("/api/builds/{run_id}/events")
    async def stream_events(run_id: str):
        async def gen():
            ch = RUN_BUS.open(run_id)
            idx = 0
            while True:
                with ch.lock:
                    items = ch.history[idx:]
                    idx = len(ch.history)
                for ev in items:
                    if ev.get("type") == "_end":
                        return
                    yield f"data: {json.dumps(ev)}\n\n"
                if ch.done and idx >= len(ch.history):
                    return
                await asyncio.sleep(0.25)

        return StreamingResponse(gen(), media_type="text/event-stream")

    # ── runs ──
    @app.get("/api/runs")
    def list_runs() -> list[dict]:
        return [r.model_dump() for r in MANAGER.list_runs()]

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        info = MANAGER.get_run(run_id)
        if info is None:
            raise HTTPException(404, "run not found")
        return info.model_dump()

    @app.get("/api/runs/{run_id}/artifacts")
    def get_artifacts(run_id: str) -> JSONResponse:
        info = MANAGER.get_run(run_id)
        if info is None:
            raise HTTPException(404, "run not found")
        vals = MANAGER.state_values(run_id)
        division = vals.get("division") or {}
        try:
            division_view = BlockDivision(**division).model_dump() if division else {}
        except Exception:  # noqa: BLE001
            division_view = division
        return JSONResponse({
            "review_stage": info.review_stage,
            "status": info.status.value,
            "division": division_view,
            "divider_validation": vals.get("divider_validation"),
            "built_blocks": vals.get("built_blocks_list", []),
            "mcqs": vals.get("mcqs", {}),
            "final_assessment": vals.get("final_assessment", []),
            "quality_report": vals.get("quality_report"),
            # per-stage advisory metrics shown at each gate (content / visual / mcq / final_quality)
            "eval_scores": vals.get("eval_scores", {}),
        })

    @app.get("/api/runs/{run_id}/tutorial")
    def get_tutorial(run_id: str, download: bool = False):
        if MANAGER.get_run(run_id) is None:
            raise HTTPException(404, "run not found")
        html = MANAGER.tutorial_html(run_id)
        if not html:
            raise HTTPException(409, "tutorial not ready")
        headers = {}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="{run_id}_tutorial.html"'
        return HTMLResponse(content=html, headers=headers)

    # ── reviews ──
    @app.post("/api/reviews/{run_id}/blocks")
    def submit_block_review(run_id: str, req: BlockReviewRequest) -> dict:
        try:
            info = MANAGER.resume_blocks(run_id, accepted=req.accepted, feedback=req.feedback)
        except KeyError:
            raise HTTPException(404, "run not found")
        return info.model_dump()

    @app.post("/api/reviews/{run_id}/stage/{stage}")
    def submit_stage_review(run_id: str, stage: str, req: StageReviewRequest) -> dict:
        """Per-agent gate: content | animation | mcq. accept → next stage; feedback → refine."""
        try:
            info = MANAGER.resume_stage(run_id, stage, accepted=req.accepted, feedback=req.feedback,
                                        feedback_map=req.feedback_map, reject=req.reject,
                                        block_feedback_map=req.block_feedback_map)
        except KeyError:
            raise HTTPException(404, "run not found")
        except ValueError as err:
            raise HTTPException(422, str(err))
        return info.model_dump()

    @app.post("/api/runs/{run_id}/finalize")
    def finalize_run(run_id: str) -> dict:
        """Assemble the final tutorial from the run's current state (works even for stuck/old runs)."""
        try:
            return MANAGER.finalize(run_id).model_dump()
        except KeyError:
            raise HTTPException(404, "run not found")

    @app.post("/api/runs/{run_id}/retry")
    def retry_run(run_id: str) -> dict:
        """Re-run a failed/stuck run from its last checkpoint."""
        try:
            return MANAGER.retry(run_id).model_dump()
        except KeyError:
            raise HTTPException(404, "run not found")

    @app.post("/api/runs/{run_id}/mcq/edit")
    def edit_mcq(run_id: str, req: McqEditRequest) -> dict:
        """Regenerate/reject ONE block's MCQs in place (no full gate reload)."""
        try:
            return MANAGER.edit_mcq(run_id, req.block_id, req.action, req.index, req.feedback)
        except KeyError:
            raise HTTPException(404, "run or block not found")

    @app.post("/api/runs/{run_id}/assessment/edit")
    def edit_assessment(run_id: str, req: AssessmentEditRequest) -> dict:
        """Regenerate/reject one assessment question (or the whole set) in place."""
        try:
            return MANAGER.edit_assessment(run_id, req.action, req.index, req.feedback)
        except KeyError:
            raise HTTPException(404, "run not found")

    @app.post("/api/runs/{run_id}/content/edit")
    def edit_content(run_id: str, req: ContentEditRequest) -> dict:
        """Regenerate ONE block's content (+its animations) in place at the final review gate."""
        try:
            return MANAGER.edit_content(run_id, req.block_id, req.feedback)
        except KeyError:
            raise HTTPException(404, "run or block not found")

    @app.post("/api/runs/{run_id}/animation/edit")
    def edit_animation(run_id: str, req: AnimationEditRequest) -> dict:
        """Regenerate or reject ONE block's animation in place at the final review gate."""
        try:
            return MANAGER.edit_animation(run_id, req.block_id, req.action, req.feedback, req.image_id)
        except KeyError:
            raise HTTPException(404, "run or block not found")

    @app.post("/api/reviews/{run_id}/final")
    def submit_final_proceed(run_id: str, req: FinalProceedRequest) -> dict:
        """Proceed from the combined final review (HITL #6) → assemble + publish + memory."""
        try:
            info = MANAGER.resume_final(run_id, notes=req.notes)
        except KeyError:
            raise HTTPException(404, "run not found")
        return info.model_dump()

    @app.post("/api/reviews/{run_id}")
    def submit_final_review(run_id: str, req: FinalReviewRequest) -> dict:
        try:
            info = MANAGER.resume_quality(run_id, req.decision, edits=req.edits, notes=req.notes)
        except KeyError:
            raise HTTPException(404, "run not found")
        return info.model_dump()

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    # ── persistence status (Supabase vs local SQLite fallback) ──
    @app.get("/api/db-status")
    def db_status() -> JSONResponse:
        from ..persistence.health import status
        return JSONResponse(status())

    # ── generated tutorials (scanned from the on-disk library — the source of truth) ──
    @app.get("/api/tutorials")
    def list_tutorials() -> list[dict]:
        import datetime
        from urllib.parse import quote
        from ..config import get_settings
        base = get_settings().generated_tutorials_path
        out: list[dict] = []
        if base.exists():
            for f in sorted(base.rglob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True):
                rel = f.relative_to(base)
                course = rel.parts[0].replace("_", " ").title() if len(rel.parts) > 1 else ""
                enc = quote(str(rel))
                out.append({
                    "course_name": course,
                    "session_name": f.stem.replace("_", " ").title(),
                    "rel_path": str(rel),
                    "updated_at": datetime.datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
                    "tutorial_url": f"/api/tutorials/file?path={enc}",
                    "download_url": f"/api/tutorials/file?path={enc}&download=true",
                })
        return out

    @app.get("/api/courses")
    def list_courses() -> list[dict]:
        """Existing courses + their sessions (from the on-disk library) for autocomplete."""
        from ..config import get_settings
        base = get_settings().generated_tutorials_path
        courses: dict[str, set] = {}
        if base.exists():
            for f in base.rglob("*.html"):
                rel = f.relative_to(base)
                if len(rel.parts) < 2:
                    continue
                course = rel.parts[0].replace("_", " ").title()
                session = f.stem.replace("_", " ").title()
                courses.setdefault(course, set()).add(session)
        return [{"name": c, "sessions": sorted(s)} for c, s in sorted(courses.items())]

    @app.get("/api/tutorials/file")
    def tutorial_file(path: str, download: bool = False):
        from ..config import get_settings
        base = get_settings().generated_tutorials_path.resolve()
        target = (base / path).resolve()
        # path-traversal guard: must stay within the library
        if base not in target.parents or not target.is_file() or target.suffix != ".html":
            raise HTTPException(404, "tutorial not found")
        html = target.read_text(encoding="utf-8")
        headers = {"Content-Disposition": f'attachment; filename="{target.name}"'} if download else {}
        return HTMLResponse(content=html, headers=headers)

    # ── cost ──
    # How much THIS app has spent on the shared OpenRouter key, plus the key's total
    # usage / remaining credit and the derived 'others' figure. See tutorial_builder.cost.
    @app.get("/api/cost")
    def cost() -> JSONResponse:
        from ..cost import cost_summary
        return JSONResponse(cost_summary())

    # ── root ──
    # The UI lives in the separate `frontend/` app (served on its own port).
    @app.get("/")
    def index():
        return HTMLResponse(
            "<h1>Tutorial Builder API</h1>"
            "<p>This is the backend API. The web UI is the separate <code>frontend/</code> "
            "app — start it with <code>frontend.sh</code> (or open <code>frontend/index.html</code>) "
            "and it will talk to this API.</p>"
            '<p>Health check: <a href="/api/health">/api/health</a></p>'
        )

    return app


app = create_app()
