"""Owns the compiled LangGraph app and drives runs in background threads.

Graph state persists in Supabase Postgres via the PostgresSaver checkpointer (keyed by
thread_id = run_id), so both human gates (block-division review and final review) resume across
HTTP requests — and now across server restarts. Run metadata (RunInfo) is mirrored to the
``runs`` table and re-hydrated on startup so the run list survives a restart too.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

from psycopg.types.json import Json

from ..config import get_settings
from ..graph import build_graph, initial_state
from ..persistence.db import connection
from ..utils.events import RUN_BUS
from ..utils.io import run_dir
from ..utils.logging import now_iso
from .schemas import RunInfo, RunStatus

_APP = build_graph()  # Supabase Postgres checkpointer (falls back to in-memory if unreachable)
_STAGE_BY_NODE = {
    "human_block_review": "block",
    "human_content_review": "content",
    "human_animation_review": "animation",
    "human_mcq_review": "mcq",
    "human_assessment_review": "assessment",
    "human_final_review": "final",
}
# per-stage state keys driven by the generic stage-review endpoint
_STAGE_KEYS = {
    "content": ("content_accepted", "content_feedback"),
    "animation": ("animation_accepted", "animation_feedback"),
    "mcq": ("mcq_accepted", "mcq_feedback"),
}


def _cfg(run_id: str) -> dict:
    return {"configurable": {"thread_id": run_id}}


class RunManager:
    def __init__(self) -> None:
        self._runs: dict[str, RunInfo] = {}
        self._calls_baseline: dict[str, int] = {}   # ledger call-count at each run's start
        self._tokens_baseline: dict[str, int] = {}  # ledger token-count at each run's start
        self._lock = threading.Lock()
        self._hydrate()

    def _hydrate(self) -> None:
        """Load existing runs so the list survives a restart (Supabase, else local SQLite)."""
        from ..persistence import local
        from ..persistence.health import supabase_ok
        rows: list[dict] = []
        if supabase_ok() is False:
            try:
                rows = local.load_runs()
            except Exception:  # noqa: BLE001
                rows = []
            for data in rows:
                try:
                    info = RunInfo(**data)
                    self._runs[info.run_id] = info
                except Exception:  # noqa: BLE001
                    pass
            return
        try:
            with connection() as conn:
                fetched = conn.execute("select data from runs order by created_at desc").fetchall()
            rows = [r.get("data") or {} for r in fetched]
        except Exception:  # noqa: BLE001 — Supabase down → local SQLite
            try:
                rows = local.load_runs()
            except Exception:  # noqa: BLE001
                rows = []
        for data in rows:
            try:
                info = RunInfo(**data)
                # A run marked "running" can't actually be in-flight on a freshly-started process —
                # its thread died with the previous server. Flag it interrupted so the UI shows
                # Retry (resume from last checkpoint) instead of waiting on events that never come.
                if info.status == RunStatus.running:
                    info.status = RunStatus.failed
                    info.message = info.message or "Interrupted (server restarted) — use Retry to resume."
                self._runs[info.run_id] = info
            except Exception:  # noqa: BLE001
                pass

    # ── public ──
    def start_build(self, raw_bytes: bytes, filename: str, metadata: dict, *,
                    material: bytes | None = None, material_filename: str = "",
                    material_text: str = "", images: list[tuple[str, bytes]] | None = None) -> RunInfo:
        settings = get_settings()
        run_id = uuid.uuid4().hex[:12]
        ext = "pptx" if Path(filename).suffix.lower() in {".pptx", ".ppt"} else "html"
        rdir = run_dir(run_id, settings)
        in_path = rdir / f"input.{ext}"
        in_path.write_bytes(raw_bytes)

        metadata = dict(metadata or {})
        # Optional add-ons: extra reading material (hands-on detail the deck lacks) + extra images.
        if material:
            msuffix = Path(material_filename).suffix.lower() or ".md"
            mpath = rdir / f"material{msuffix}"
            mpath.write_bytes(material)
            metadata["extra_material_path"] = str(mpath)
        if material_text and material_text.strip():
            metadata["extra_material_text"] = material_text.strip()
        saved_images: list[str] = []
        for i, (img_name, img_bytes) in enumerate(images or [], start=1):
            if not img_bytes:
                continue
            suffix = Path(img_name).suffix.lower() or ".png"
            ipath = rdir / "extra_images" / f"addon_{i:02d}{suffix}"
            ipath.parent.mkdir(parents=True, exist_ok=True)
            ipath.write_bytes(img_bytes)
            saved_images.append(str(ipath))
        if saved_images:
            metadata["extra_image_paths"] = saved_images

        info = RunInfo(run_id=run_id, status=RunStatus.running,
                       course_name=metadata.get("course_name", ""),
                       session_name=metadata.get("session_name", ""),
                       created_at=now_iso(), updated_at=now_iso(), current_node="ingest")
        with self._lock:
            self._runs[run_id] = info
        RUN_BUS.reset(run_id)
        graph_input = initial_state(run_id, str(in_path), ext, metadata)
        # All DB work (baseline capture + persistence) happens in the background thread, NOT here,
        # so the HTTP request returns immediately and the event loop is never blocked on the DB.
        threading.Thread(target=self._drive, args=(run_id, graph_input), daemon=True).start()
        return info

    def resume_blocks(self, run_id: str, accepted: bool, feedback: str = "") -> RunInfo:
        return self._resume(run_id, {"blocks_accepted": accepted, "block_feedback": feedback})

    def resume_stage(self, run_id: str, stage: str, accepted: bool, feedback: str = "",
                     feedback_map: dict | None = None, reject: list | None = None,
                     block_feedback_map: dict | None = None) -> RunInfo:
        """Resume a per-agent gate (content | animation | mcq).

        content: per-block feedback map. animation: per-block feedback map + per-block reject.
        mcq: per-question feedback map + per-block (whole-block) feedback map + per-question reject.
        accepted=True (everything empty) = accept all and move on."""
        feedback_map = {k: v for k, v in (feedback_map or {}).items() if (v or "").strip()}
        block_feedback_map = {k: v for k, v in (block_feedback_map or {}).items() if (v or "").strip()}
        reject = [str(x) for x in (reject or [])]
        accept_all = accepted or (not feedback_map and not block_feedback_map and not reject)
        if stage == "content":
            return self._resume(run_id, {"content_accepted": accept_all,
                                         "content_feedback_map": {} if accept_all else feedback_map})
        if stage == "animation":
            return self._resume(run_id, {"animation_accepted": accept_all,
                                         "animation_feedback_map": {} if accept_all else feedback_map,
                                         "animation_reject": [] if accept_all else reject})
        if stage == "mcq":
            return self._resume(run_id, {"mcq_accepted": accept_all,
                                         "mcq_feedback_map": {} if accept_all else feedback_map,
                                         "mcq_block_feedback_map": {} if accept_all else block_feedback_map,
                                         "mcq_reject": [] if accept_all else reject})
        if stage == "assessment":
            # Assessment edits are applied in place (see edit_assessment); accept → assemble.
            return self._resume(run_id, {"assessment_accepted": True})
        raise ValueError(f"unknown review stage: {stage!r}")

    def edit_assessment(self, run_id: str, action: str = "question",
                        index: int | None = None, feedback: str = "") -> dict:
        """In-place edit of the session assessment while paused at the assessment gate.

        action: "question" (regenerate one), "all" (regenerate the set), "reject" (drop one)."""
        from ..agents import agent4_assessment as a4
        from ..config import get_settings
        from ..schemas import MCQ, AssessmentQuestion, BlockResult
        from ..llm.client import LLMClient

        vals = self.state_values(run_id)
        built = [BlockResult(**b) for b in vals.get("built_blocks_list", [])]
        lst = list(vals.get("final_assessment", []) or [])
        settings = get_settings()
        client = LLMClient(settings)
        session = (vals.get("metadata", {}) or {}).get("session_name", "Session")
        objectives = (vals.get("metadata", {}) or {}).get("learning_objectives", [])
        if action == "reject":
            if index is not None and 0 <= index < len(lst):
                del lst[index]
        elif action == "all":
            new = a4.run(built, session_name=session, learning_objectives=objectives,
                         client=client, settings=settings, extra_notes=feedback)
            lst = [m.model_dump(mode="json", by_alias=True) for m in new]
        else:  # revise this ONE question — hand the agent the current Q&A + the specific change
            cur = lst[index] if (index is not None and 0 <= index < len(lst)) else {}
            notes = (
                "REVISE THIS EXISTING assessment question rather than writing a brand-new one. Apply "
                "ONLY the requested change and keep the rest of the question/answer intact.\n"
                f"CURRENT QUESTION: {cur.get('question', '')}\n"
                f"CURRENT ANSWER: {cur.get('answer', '')}\n"
                f"REQUESTED CHANGE: {feedback}"
            )
            new = a4.run(built, session_name=session, learning_objectives=objectives, count=1,
                         client=client, settings=settings, extra_notes=notes)
            if new and index is not None and 0 <= index < len(lst):
                lst[index] = new[0].model_dump(mode="json", by_alias=True)
        # re-render the preview draft so "Open draft" stays current, then persist
        patch: dict = {"final_assessment": lst}
        try:
            from ..assembler import html_assembler
            mcqs = {int(k): [MCQ(**m) for m in v] for k, v in (vals.get("mcqs", {}) or {}).items()}
            patch["session_html_draft"] = html_assembler.render(
                session_title=session, blocks=built, mcqs=mcqs,
                final_assessment=[AssessmentQuestion(**m) for m in lst], settings=settings)
        except Exception:  # noqa: BLE001 — preview render is best-effort
            pass
        if action == "reject" and index is not None:
            patch["stage_feedback"] = [f"[assessment q{index}] rejected"]
        elif feedback.strip():
            patch["stage_feedback"] = [f"[assessment] {feedback.strip()}"]
        _APP.update_state(_cfg(run_id), patch)
        return {"final_assessment": lst}

    def resume_quality(self, run_id: str, decision: str, edits: dict | None = None,
                       notes: str = "") -> RunInfo:
        return self._resume(run_id, {"review_decision": decision, "review_edits": edits or {},
                                     "review_notes": notes})

    def edit_mcq(self, run_id: str, block_id: str, action: str = "question",
                 index: int | None = None, feedback: str = "") -> dict:
        """In-place edit of ONE block's MCQs while paused at the MCQ gate — no full re-run.

        action: "question" (regenerate one), "block" (regenerate all), "reject" (drop one).
        Updates only that block's questions in the checkpoint and returns the new list."""
        from ..agents import agent3_mcq as a3
        from ..config import get_settings
        from ..llm.client import LLMClient
        from ..schemas import MCQ, BlockDivision

        vals = self.state_values(run_id)
        division = BlockDivision(**(vals.get("division") or {}))
        block = next((b for b in division.blocks if str(b.block_id) == str(block_id)), None)
        if block is None:
            raise KeyError(block_id)
        lst = list((vals.get("mcqs", {}) or {}).get(str(block_id), []))
        settings = get_settings()
        client = LLMClient(settings)
        if action == "reject":
            if index is not None and 0 <= index < len(lst):
                del lst[index]
        elif action == "block":
            new = a3.run(block, client=client, settings=settings, extra_notes=feedback)
            lst = [m.model_dump(mode="json", by_alias=True) for m in new]
        else:  # targeted edit of ONE question — change only what the feedback asks, keep the rest
            if index is not None and 0 <= index < len(lst):
                edited = a3.edit(block, MCQ(**lst[index]), feedback, client=client, settings=settings)
                if edited is not None:
                    lst[index] = edited.model_dump(mode="json", by_alias=True)
        patch: dict = {"mcqs": {str(block_id): lst}}
        if action == "reject" and index is not None:
            patch["stage_feedback"] = [f"[mcq {block_id}:{index}] rejected"]
        elif feedback.strip():
            tag = f"[mcq {block_id}]" if action == "block" else f"[mcq {block_id}:{index}]"
            patch["stage_feedback"] = [f"{tag} {feedback.strip()}"]
        _APP.update_state(_cfg(run_id), patch)
        return {"block_id": str(block_id), "mcqs": lst}

    def edit_content(self, run_id: str, block_id: str, feedback: str = "") -> dict:
        """In-place re-author of ONE block (content + its animations) at the final review gate.

        Updates the checkpoint, re-renders the preview draft, and records the feedback to course
        memory (tagged) so it auto-applies on future runs of this course."""
        from ..agents import agent1_content as a1
        from ..llm.client import LLMClient
        from ..schemas import BlockDivision

        vals = self.state_values(run_id)
        division = BlockDivision(**(vals.get("division") or {}))
        block = next((b for b in division.blocks if str(b.block_id) == str(block_id)), None)
        if block is None:
            raise KeyError(block_id)
        settings = get_settings()
        client = LLMClient(settings)
        drafted = a1.author(block, memory=vals.get("memory", {}), client=client, settings=settings,
                            extra_notes=feedback, supplementary=vals.get("supplementary_material", ""))
        result = a1.apply_animations(drafted, block.images, client=client, settings=settings,
                                     extra_notes=feedback)
        built = [result.model_dump(mode="json") if str(b.get("block_id")) == str(block_id) else b
                 for b in (vals.get("built_blocks_list", []) or [])]
        patch: dict = {"built_blocks_list": built}
        if feedback.strip():
            patch["stage_feedback"] = [f"[content b{block_id}] {feedback.strip()}"]
        self._patch_with_draft(run_id, vals, patch, built_override=built)
        return {"block_id": str(block_id), "built_blocks": built}

    def edit_animation(self, run_id: str, block_id: str, action: str = "refine",
                       feedback: str = "", image_id: str = "") -> dict:
        """In-place animation edit: action "refine" (regenerate with feedback) or "reject" (drop it).

        With ``image_id`` set, only THAT one animation changes — every other animation in the block
        is kept exactly as-is (used by the animation gate for per-animation accept/reject/improve).
        Without ``image_id`` the whole block is (re)generated (used by the final review gate).
        Re-applying always starts from the authored marker HTML, so it never stacks."""
        from ..agents import agent1_content as a1
        from ..llm.client import LLMClient
        from ..schemas import BlockDivision, BlockResult, VisualDecision

        vals = self.state_values(run_id)
        division = BlockDivision(**(vals.get("division") or {}))
        block = next((b for b in division.blocks if str(b.block_id) == str(block_id)), None)
        cur = next((b for b in (vals.get("built_blocks_list", []) or [])
                    if str(b.get("block_id")) == str(block_id)), None)
        if block is None or cur is None:
            raise KeyError(block_id)
        settings = get_settings()
        client = LLMClient(settings)
        result = BlockResult(**cur)

        if image_id:
            # Single animation: keep every OTHER animation untouched, change only this image.
            reuse = {a.image_id: a for a in result.animations if a.image_id != image_id}
            notes_by_image: dict = {}
            if action == "reject":
                for v in result.visual_verdicts:
                    if v.image_id == image_id and v.decision == VisualDecision.ANIMATE:
                        v.decision = VisualDecision.SKIP
                note = f"[animation b{block_id}:{image_id}] rejected"
            else:  # refine just this one
                notes_by_image = {image_id: feedback}
                note = f"[animation b{block_id}:{image_id}] {feedback.strip()}" if feedback.strip() else ""
            result = a1.apply_animations(result, block.images, client=client, settings=settings,
                                         notes_by_image=notes_by_image, reuse=reuse)
        elif action == "reject":
            for v in result.visual_verdicts:
                if v.decision == VisualDecision.ANIMATE:
                    v.decision = VisualDecision.SKIP
            result = a1.apply_animations(result, block.images, client=client, settings=settings)
            note = f"[animation b{block_id}] rejected"
        else:  # refine the whole block
            result = a1.apply_animations(result, block.images, client=client, settings=settings,
                                         extra_notes=feedback)
            note = f"[animation b{block_id}] {feedback.strip()}" if feedback.strip() else ""

        built = [result.model_dump(mode="json") if str(b.get("block_id")) == str(block_id) else b
                 for b in (vals.get("built_blocks_list", []) or [])]
        patch: dict = {"built_blocks_list": built}
        if note:
            patch["stage_feedback"] = [note]
        self._patch_with_draft(run_id, vals, patch, built_override=built)
        return {"block_id": str(block_id), "built_blocks": built}

    def resume_final(self, run_id: str, notes: str = "") -> RunInfo:
        """Proceed from the final combined review (HITL #6) → assemble + publish + memory."""
        return self._resume(run_id, {"final_review_notes": notes})

    def _patch_with_draft(self, run_id: str, vals: dict, patch: dict, *,
                          built_override=None, mcqs_override=None, fa_override=None) -> None:
        """Apply a state patch, also refreshing ``session_html_draft`` so the final-review preview
        reflects the edit. Best-effort: a render failure still applies the rest of the patch."""
        from ..assembler import html_assembler
        from ..schemas import MCQ, AssessmentQuestion, BlockResult

        settings = get_settings()
        patch = dict(patch)
        try:
            built_src = built_override if built_override is not None else vals.get("built_blocks_list", [])
            mcqs_src = mcqs_override if mcqs_override is not None else (vals.get("mcqs", {}) or {})
            fa_src = fa_override if fa_override is not None else (vals.get("final_assessment", []) or [])
            built = [BlockResult(**b) for b in built_src]
            mcqs = {int(k): [MCQ(**m) for m in v] for k, v in mcqs_src.items()}
            fa = [AssessmentQuestion(**m) for m in fa_src]
            session = (vals.get("metadata", {}) or {}).get("session_name", "Session")
            patch["session_html_draft"] = html_assembler.render(
                session_title=session, blocks=built, mcqs=mcqs, final_assessment=fa, settings=settings)
        except Exception:  # noqa: BLE001 — preview render is best-effort
            pass
        _APP.update_state(_cfg(run_id), patch)

    def retry(self, run_id: str) -> RunInfo:
        """Re-drive a failed (or stuck) run from its last good checkpoint."""
        info = self.get_run(run_id)
        if info is None:
            raise KeyError(run_id)
        info.status, info.updated_at, info.message = RunStatus.running, now_iso(), ""
        self._persist(info)
        RUN_BUS.reset(run_id)
        threading.Thread(target=self._drive, args=(run_id, None), daemon=True).start()
        return info

    def finalize(self, run_id: str) -> RunInfo:
        """Assemble the final tutorial directly from the run's current state (blocks + MCQs +
        assessment), bypassing the graph. Deterministic, so it always works — even for runs stuck
        at an old/removed gate. Persists the file + DB copy, updates memory, marks the run completed."""
        from ..assembler import html_assembler
        from ..config import get_settings
        from ..memory import cross_session
        from ..memory.run_state import defined_concepts, mcq_topics
        from ..schemas import MCQ, AssessmentQuestion, BlockResult

        info = self.get_run(run_id)
        if info is None:
            raise KeyError(run_id)
        settings = get_settings()
        vals = self.state_values(run_id)
        meta = vals.get("metadata", {}) or {}
        course = meta.get("course_name", "Course")
        session = meta.get("session_name", "Session")
        blocks = [BlockResult(**b) for b in vals.get("built_blocks_list", [])]
        mcqs = {int(k): [MCQ(**m) for m in v] for k, v in (vals.get("mcqs", {}) or {}).items()}
        fa = [AssessmentQuestion(**m) for m in vals.get("final_assessment", [])]
        html = html_assembler.render(session_title=session, blocks=blocks, mcqs=mcqs,
                                     final_assessment=fa, settings=settings)
        html_assembler.write_tutorial(html, run_dir(run_id, settings) /
                                      html_assembler.output_filename(course, session))
        published = html_assembler.publish_tutorial(html, course, session, settings)
        try:
            from ..persistence import tutorials as tut_store
            tut_store.save(run_id, course, session, html, str(published), settings=settings)
        except Exception:  # noqa: BLE001
            pass
        try:
            cross_session.update(course, new_concepts=defined_concepts(blocks),
                                 new_mcq_topics=mcq_topics(mcqs),
                                 feedback=list(vals.get("division_feedback", []))
                                 + list(vals.get("stage_feedback", [])),
                                 session=session, settings=settings)
        except Exception:  # noqa: BLE001
            pass
        try:
            _APP.update_state(_cfg(run_id), {"final_html": html, "output_path": str(published),
                                             "status": "completed"})
        except Exception:  # noqa: BLE001
            pass
        info.status, info.output_path, info.review_stage = RunStatus.completed, str(published), ""
        info.updated_at = now_iso()
        self._persist(info)
        RUN_BUS.finish(run_id, {"type": "run", "status": "completed", "output_path": str(published)})
        return info

    def get_run(self, run_id: str) -> RunInfo | None:
        return self._runs.get(run_id)

    def list_runs(self) -> list[RunInfo]:
        return sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)

    def state_values(self, run_id: str) -> dict:
        return dict(_APP.get_state(_cfg(run_id)).values)

    def tutorial_html(self, run_id: str) -> str | None:
        return self.state_values(run_id).get("final_html") or self.state_values(run_id).get(
            "session_html_draft")

    # ── internals ──
    def _resume(self, run_id: str, patch: dict) -> RunInfo:
        info = self.get_run(run_id)
        if info is None:
            raise KeyError(run_id)
        _APP.update_state(_cfg(run_id), patch)
        info.status, info.updated_at, info.review_stage = RunStatus.running, now_iso(), ""
        self._persist(info)
        RUN_BUS.reset(run_id)
        threading.Thread(target=self._drive, args=(run_id, None), daemon=True).start()
        return info

    def _drive(self, run_id: str, graph_input) -> None:
        info = self._runs[run_id]
        cfg = _cfg(run_id)
        # First drive of a fresh build: capture the LLM-usage baseline + write the initial record.
        # Done here (background thread) so it never blocks the HTTP request that started the build.
        if graph_input is not None and run_id not in self._calls_baseline:
            from .. import cost
            self._calls_baseline[run_id] = cost.current_calls()
            self._tokens_baseline[run_id] = cost.current_tokens()
            self._persist(info)
        try:
            _APP.invoke(graph_input, cfg)
        except Exception as err:  # noqa: BLE001
            info.status, info.message, info.updated_at = RunStatus.failed, str(err), now_iso()
            self._persist(info)
            RUN_BUS.finish(run_id, {"type": "run", "status": "failed", "message": str(err)})
            return

        snap = _APP.get_state(cfg)
        vals = snap.values
        info.current_node = vals.get("current_node", info.current_node)
        info.session_name = (vals.get("metadata", {}) or {}).get("session_name", info.session_name)
        info.updated_at = now_iso()
        # Per-run LLM usage = ledger delta since this run started.
        from .. import cost
        info.llm_calls = max(0, cost.current_calls() - self._calls_baseline.get(run_id, cost.current_calls()))
        info.llm_tokens = max(0, cost.current_tokens() - self._tokens_baseline.get(run_id, cost.current_tokens()))
        open_gate = next((n for n in (snap.next or ()) if n in _STAGE_BY_NODE), None)
        if open_gate:
            info.status = RunStatus.needs_review
            info.review_stage = _STAGE_BY_NODE[open_gate]
            self._persist(info)
            RUN_BUS.finish(run_id, {"type": "run", "status": "needs_review",
                                    "stage": info.review_stage,
                                    "calls": info.llm_calls, "tokens": info.llm_tokens})
        else:
            status = vals.get("status", "completed")
            info.status = RunStatus(status) if status in RunStatus._value2member_map_ \
                else RunStatus.completed
            info.review_stage = ""
            info.output_path = vals.get("output_path")
            self._persist(info)
            RUN_BUS.finish(run_id, {"type": "run", "status": info.status.value,
                                    "output_path": info.output_path,
                                    "calls": info.llm_calls, "tokens": info.llm_tokens})

    def _persist(self, info: RunInfo) -> None:
        status = info.status.value if hasattr(info.status, "value") else str(info.status)
        from ..persistence.health import supabase_ok
        if supabase_ok() is False:  # known down → straight to local SQLite (no slow PG retry)
            try:
                from ..persistence import local
                d = info.model_dump(mode="json"); d["status"] = status
                local.save_run(d)
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            with connection() as conn:
                conn.execute(
                    """
                    insert into runs
                        (run_id, course_name, session_name, status, created_at, updated_at, data)
                    values (%s, %s, %s, %s, coalesce(%s::timestamptz, now()), now(), %s)
                    on conflict (run_id) do update set
                        course_name = excluded.course_name,
                        session_name = excluded.session_name,
                        status = excluded.status,
                        updated_at = now(),
                        data = excluded.data
                    """,
                    (info.run_id, info.course_name, info.session_name, status,
                     info.created_at or None, Json(info.model_dump(mode="json"))),
                )
        except Exception:  # noqa: BLE001 — Supabase down → mirror to local SQLite
            try:
                from ..persistence import local
                d = info.model_dump(mode="json")
                d["status"] = status
                local.save_run(d)
            except Exception:  # noqa: BLE001 — persistence must never break a run
                pass


MANAGER = RunManager()
