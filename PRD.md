# PRD — Interactive Tutorial Builder (Agentic Workflow)

**Status:** v3 (implemented; running end-to-end via web UI + CLI)
**Owner:** gen-ai-content@nxtwave.co.in
**Date:** 2026-06-30 (v3) · 2026-06-30 (v2) · 2026-06-13 (v1)
**Orchestration:** LangGraph (Python) · **API:** FastAPI (REST + SSE) · **UI:** React + Vite

---

## 0. Revision History

### v3 — 2026-06-30 (five HITL gates, per-gate advisory eval, image-describer, descriptive assessment, web app + Supabase)

The system has moved well past the v2 design. The shipping implementation differs from v1/v2 in several structural ways; this revision documents what is actually built (`backend/src/tutorial_builder/` + `frontend/`).

1. **Five human-in-the-loop gates, not two.** The pipeline now pauses for review at **block division → content → animation → MCQ → assessment**, each surfaced in the web UI with element-level controls. (v1/v2 had only block-division + a single final review.) Gates are LangGraph `interrupt_before` stops on `human_block_review`, `human_content_review`, `human_animation_review`, `human_mcq_review`, `human_assessment_review`.
2. **Per-gate advisory eval replaces the automated self-refine loop.** Each producing stage attaches an advisory rubric score (`steps/stage_eval.py`) that the reviewer sees at that stage's gate. The automated judge→retry→escalate loop (`quality_node`/`refine_node`/`final_quality_check`) still exists in code but is **not wired into the compiled graph** — quality control is now human-driven at each gate, plus agent self-validation (see #8). Refinement is "refine this element with my feedback," triggered by the human, not by a threshold.
3. **Animation split into its own agent + its own gate.** Agent 1 now has two phases — `author` (write block HTML + per-image animate/skip verdicts, leaving a marker) and `apply_animations` (place Agent 2's output at the marker). Agent 2 runs between the content gate and the animation gate so animations are reviewed independently of prose.
4. **Image-describer stage (Stage 0.5).** Every extracted image is vision-captioned at ingest into `{description, placement_context, animation_worthy, description_source}` and these hints drive Agent 1's animate/skip decision and Agent 2's build. Capped at `TB_MAX_VISION_DESCRIBE` (default 10) most-likely concept images; the rest use a free heuristic. Runs identically for HTML and PPTX.
5. **Add-on material at upload.** Besides the deck/HTML, the user can attach (a) **extra reading material** (`.md`/`.txt`/`.html` or pasted) and (b) **extra images** (e.g. a final workflow diagram missing from the deck). Extra images are **merged into the source** (divided, described, placed, animated like any other). Reading material is kept **supplementary** — it enriches Agent 1's prose but is **deliberately NOT divided and NOT used for block MCQs**, so division and per-block quizzes stay anchored to the deck.
6. **Descriptive (open-ended) final assessment.** The session assessment is now **direct question + model answer** items (short/long, with a Bloom's K-level), rendered as a **read-through carousel — no options, no auto-grading**. (v1/v2 specified a gated final MCQ set.) Per-block gating MCQs are unchanged (still `QUIZ_DATA`, still continue-gated).
7. **Persistence is a real database with fallback.** Supabase Postgres is the primary store for LangGraph checkpoints, course memory, the cost ledger, run metadata, and published tutorials. If Supabase is unreachable the app **falls back to a local SQLite store** (`<runs_dir>/local_store.sqlite`), then to an in-memory checkpointer as a last resort — and switches back to Supabase automatically when it returns. A `GET /api/db-status` endpoint + header badge expose the active backend.
8. **Agent self-validation ("skills").** Agents validate their own output against packaged skill specs (`skills/house_style.md`, `skills/visual_patterns.md`) and validators (`skills/mcq_validator.py`, `skills/assessment_validator.py`) with `TB_SELF_VALIDATE_RETRIES` (default 1) before a gate ever sees the output.
9. **Provider + cost.** LLM calls go through OpenRouter (OpenAI-compatible) by default with a one-env-var switch to Google **Gemini** (`TB_LLM_PROVIDER=gemini`). Default model is `anthropic/claude-sonnet-4.6` for text, vision, and judge. A **cost panel** tracks this app's real USD spend on the (shared) OpenRouter key, derives others' usage, and converts to INR at a live FX rate.
10. **Web application + CLI.** A React/Vite front end (Workflow/Builder · Generated tutorials · Workflow-animation tabs) talks to a FastAPI backend over REST + SSE. A `tutorial-builder` CLI runs a build headlessly. A **DeepEval** harness (`eval/deepeval_harness/`) supplements the rubric eval-sets with golden-replay accuracy + faithfulness checks.

> **v2 changes (still in force):** source-only content (Agent 1 invents no facts/examples/analogies/numbers; source analogies preserved); no analogy-based MCQ or assessment questions (concept-direct, session terminology); content/process images are **mandatory** to animate (only chrome is skipped); animations follow the lesson's described process order using the diagram's real component names. See §7/§11 for how these live in the prompts and eval-sets.

### v2 — 2026-06-30 (content fidelity + mandatory image animation)

1. **Source-only content (Agent 1).** Block text uses **only** the source PPT/reading material — no invented facts, examples, analogies, statistics, or explanations. Rephrasing source wording into clean prose is encouraged. Source analogies are preserved; new ones are never invented.
2. **No analogy-based questions (Agent 3 MCQ & Agent 4 Assessment).** Questions test the concept **directly** using the session's own terminology. An analogy may teach in the body but is never the subject of a question.
3. **Mandatory animation of content/process images.** Any image carrying a process or structure (workflow/automation, flowchart, architecture, lifecycle, comparison, process-bearing screenshot) **must** be animated. Only pure chrome is skipped.
4. **Animations follow the described process.** Build order matches how the lesson explains the image, preserving the diagram's real component/node names.
5. **Animation count per block.** Guideline 1–2/block, not a hard cap: every content/process image animates even if a block has 3+.
6. **Element-level HITL controls.** Accept / improve per content block; accept / reject / regenerate per animation; plus division, MCQ, assessment gates.

---

## 1. Summary

An agentic AI workflow that converts a course session's source material (HTML **or** PPTX, plus optional add-on material) into a single, self-contained **interactive HTML tutorial** — a guided, progressively-revealed learning experience that:

1. Splits the session into logical **content blocks**.
2. Rewrites each block into rich interactive HTML, replacing concept/process diagrams with **inline animations**.
3. Gates progress with **mandatory MCQs** after each block.
4. Concludes with a **descriptive session-level assessment** (read-through, model answers).

The workflow is built around **memory**, **eval-sets**, **LLM-judge / DeepEval evaluation**, **agent self-validation**, and **five human-in-the-loop (HITL) checkpoints**, all driven through a web UI (or a headless CLI).

The final artifact follows the reference output structure (`backend/samples/REFERENCE_OUTPUT.html`): `content block 1 → continue → MCQ → continue → content block 2 → … → final assessment carousel`.

---

## 2. Business Problem

Learners consume passive content (reading material, PPTs, recordings) that never verifies understanding *during* learning. Building interactive tutorials by hand is slow and does not scale to thousands of sessions. We need an automated system that turns session content into structured, interactive, assessment-driven tutorials with consistent quality.

---

## 3. Goals & Non-Goals

### Goals
- Accept a single session as **HTML or PPTX** (+ optional add-on reading material and images) and produce one render-ready interactive HTML file.
- Divide content into cohesive blocks (default target 4–5; configurable) using deterministic parsing + LLM structuring.
- Vision-describe images at ingest; replace concept/process diagrams with self-contained inline animations; skip only decorative chrome.
- Generate mandatory, technically-correct gating MCQs per block + a descriptive session assessment.
- Enforce quality via per-stage advisory eval, rubric eval-sets, agent self-validation, and human review at every stage.
- Persist memory (human feedback, accepted concepts/topics, course/style trend) across sessions of a course.
- Pause for human approval at five checkpoints, with element-level accept/refine/reject controls.

### Non-Goals
- No multi-session / full-course batch orchestration (single session per run; course memory is shared but runs are independent).
- No video/audio generation.
- No LMS write-back integration (output is an HTML file + a library entry).
- No automated auto-ship: the pipeline never finalizes without passing through the human gates.

---

## 4. Users & Personas

| Persona | Need |
|---|---|
| **Content Reviewer** (instructional designer) | Step through the five gates: approve/adjust block division; accept/refine content; accept/reject/regenerate animations; accept/refine/reject MCQs; accept/edit the assessment. Provide feedback the system learns from. |
| **Content Ops** | Run the pipeline at scale, monitor advisory eval scores + cost, resume paused/failed runs. |
| **Learner** (end consumer) | Experience the tutorial: read → answer gating MCQs → progress → read-through assessment. |

---

## 5. Inputs & Outputs

### 5.1 Inputs
Two ingestion flows converge on one normalized contract:

**Flow A — HTML input** — a single HTML file for the full session (`backend/samples/getting-started.html`): headings, paragraphs, tables, lists, code, `<img>`, custom components.

**Flow B — PPTX input** — a `.pptx` (`ingest/pptx_loader.py`): per-slide title → heading, body placeholders → paragraphs/lists, each embedded picture exported to `assets/` and referenced via `<img …>`. Slide order = document order.

Both flows produce the same `NormalizedDocument` (`normalized_html` + `assets[]` + `session_meta`); nothing downstream knows the source format. See `docs/normalized_html_contract.md`.

**Add-on material (optional, at upload):**
- **Extra reading material** (`.md`/`.txt`/`.html` file or pasted text) → kept as `supplementary_material`, fed to Agent 1 to enrich hands-on detail. **Not divided; not used for block MCQs.**
- **Extra images** (e.g. a final workflow diagram missing from the deck) → merged into the asset pool and treated like any other image (described, placed, animated). User-added images (`source_ref="user-added"`) are forced to **animate** even if a verdict would otherwise SKIP them.

**Stage 0.5 — Image describer** (`ingest/image_describer.py`): every asset is vision-captioned into `{description, placement_context, animation_worthy, description_source}` (capped at `TB_MAX_VISION_DESCRIBE`; heuristic fallback for the rest and in mock mode). These hints flow onto each block's images.

> Optional: session learning objectives (hints for block tagging + MCQ/assessment coverage). Default: "Not provided."

### 5.2 Output
A single self-contained `.html` file (no external runtime deps beyond fonts), assembled by Jinja2 templates (`backend/templates/`):
- Scrolling, stepped layout: each block is a `<div class="block">` step with a **Continue** gate.
- Gating MCQs injected via JS from a `QUIZ_DATA` object into `#quiz-area-N`; the gate stays locked until all questions in the step are answered.
- Content/process images replaced by inline, namespaced animations (`<style>`+`<svg>`+JS) built step by step from the material's described process; chrome images left as-is/omitted.
- A concluding **descriptive assessment** carousel: direct question + model answer per item (short/long, Bloom's K-level), read-through, no options, no grading.

Outputs are written to the run dir and **published** to the on-disk library `generated_tutorials/<course>/<session>.html` (never overwritten — re-runs publish `<session>_v2.html`, `_v3.html`, …), and saved to the DB (best-effort).

---

## 6. High-Level Architecture

```
        ┌──────────────────────────────── PERSISTENCE (Supabase Postgres → SQLite fallback → memory) ───────────────────────────────┐
        │  LangGraph checkpoints · course memory · cost ledger · run metadata · published tutorials                                   │
        └──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

  ingest (+image-describe) ─▶ divide ─▶ 👤 BLOCK GATE ─(accept)─┐         (feedback → divide)
                                                                ▼
   Agent 1 author (HTML + animate/skip) ─▶ 👤 CONTENT GATE ─(accept)─┐    (per-block refine → re-author flagged blocks)
                                                                     ▼
   Agent 2 apply animations (vision + ref lib) ─▶ 👤 ANIMATION GATE ─(accept)─┐  (per-block refine / reject)
                                                                              ▼
   Agent 3 per-block MCQs ─▶ 👤 MCQ GATE ─(accept)─┐  (per-question or per-block refine / reject)
                                                   ▼
   Agent 4 descriptive assessment ─▶ 👤 ASSESSMENT GATE ─(accept/edit)─▶ assemble ─▶ memory ─▶ END
```

LangGraph specifics (`graph.py`):
- **Nodes** = each stage; **state** = `TutorialState` (§9). Per-block work runs in a `ThreadPoolExecutor` (`_MAX_WORKERS=6`) and writes into dicts keyed by `block_id` merged by reducers.
- **`interrupt_before`** at the five `human_*_review` nodes; routers (`route_block_review`, `route_content_review`, …) loop back to the producing stage when the gate returns feedback, else advance.
- **Checkpointer** persists state so a run resumes after human action or failure (Supabase Postgres → SQLite → in-memory).
- The compiled graph path: `ingest → divide → block gate → content → content gate → animation → animation gate → mcq → mcq gate → assessment → assessment gate → assemble → memory → END`. (The legacy automated `draft/quality/refine/quality-gate` nodes remain in the source but are not added to the compiled graph.)

---

## 7. Detailed Workflow

### Stage 0 — Ingestion & Normalization
Detect input type. Flow A normalizes HTML; Flow B converts PPTX → normalized HTML + exported images. Merge add-on **images** into the source; keep add-on **reading material** as `supplementary_material`. Output: `document` (`NormalizedDocument`), `candidate_blocks`, `metadata`, loaded `memory`.

### Stage 0.5 — Image Describer
Vision-caption assets (`description/placement_context/animation_worthy`); attach hints onto each candidate block's images by `src`.

### Stage 1 — Block Divider (LLM)
`steps/block_divider.py` using `backend/prompts/Block_division.md`: build the heading tree, then merge/split candidate sections into a cohesive set (target `TB_MIN_BLOCKS`–`TB_MAX_BLOCKS`, default 4–5; images stay with their section). Output: `BlockDivision` (`session_name`, `heading_tree`, `division_reasoning`, `blocks[]`) + a `divider_validation` report. Advisory eval-set: `block_divider`.

### Stage 2 — HITL #1: Block Division Gate
Present heading tree, block count, and per-block titles/headings/reasoning + validation. Reviewer **accepts** → content; or **gives feedback** ("merge 2&3", "split Agile") → loop back to `divide` with feedback + previous division injected; repeat until accepted. Feedback is written to course memory.

### Stage 3a — Agent 1 Content (author) → HITL #2: Content Gate
`agents/agent1_content.py::author` (parallel over blocks): rewrite each block into house-style interactive HTML (`skills/house_style.md`), using **only source information** (+ supplementary material) — invent no facts/examples/analogies/numbers; preserve source analogies. Decide **animate vs skip** per image from the vision hints; **content/process images are mandatory to animate**, only chrome is skipped; leave an `<!--HF_ANIM:image_id-->` marker for each animate verdict. Self-validates (structure + `content`/`visual-decision` rubric) with `TB_SELF_VALIDATE_RETRIES`. Advisory `content` score shown at the gate; blocks with `quality_issues` are flagged. Reviewer **accepts** or leaves **per-block feedback** → only flagged blocks are re-authored.

### Stage 3b — Agent 2 Animation (apply) → HITL #3: Animation Gate
For each ANIMATE marker, `agents/agent2_animation.py` (vision) classifies the image, matches the closest reference pattern (`reference_animations/{waterfall,agile,v-model}-model-animation.html` + `skills/visual_patterns.md`), and emits a **self-contained inline animation** (namespaced `<style>`+`<svg>`+JS, auto-loop, `prefers-reduced-motion` safe, responsive) keyed by `image_id`. The reveal **follows the lesson's described process** using the diagram's real component/node names. `agent1_content.py::apply_animations` places it at the marker. Advisory `visual` score at the gate. Reviewer per block: **accept / refine (regenerate with feedback) / reject** (reject flips that block's ANIMATE verdicts to SKIP so re-applying yields no animation).

### Stage 3c — Agent 3 MCQ → HITL #4: MCQ Gate
`agents/agent3_mcq.py` using `backend/prompts/MCQ_generator_prompt.md`: per-block MCQs (cover sub-topics, single clear problem, 4 balanced options, no partial correctness, **no analogies**, material-only terminology, explanation, Bloom level). Emits canonical `-END-` text → parsed (`tools/mcq_parser.py`) → `QUIZ_DATA` shape `{question, options[], multi, correctIndexes[], explanation}`. Count is **adaptive** — clamped to `TB_MCQ_MIN`..`TB_MCQ_MAX` (2..3) around a signal of `max(learning_objectives, word_count/150, TB_MCQ_PER_BLOCK=2)`. Correct-answer positions are balanced across options. Self-validates via `skills/mcq_validator.py`. Advisory `mcq` score at the gate. Reviewer controls are **per-question** (`"block:index"`): refine one question, refine a whole block's set, or reject a question.

### Stage 4 — Agent 4 Assessment → HITL #5: Assessment Gate
`agents/agent4_assessment.py`: a session-wide **descriptive** assessment (default `TB_FINAL_ASSESSMENT_COUNT`=5) of direct question + model-answer items (short/long, Bloom K-level), **source-only and concept-direct** (never analogy-framed), informed by the MCQ topics already used (to avoid overlap). Self-validates via `skills/assessment_validator.py`. A full draft (blocks + MCQs + assessment) is rendered for preview. Reviewer **accepts/edits** the assessment (or regenerates/reject individual questions via `/assessment/edit`); proceeds straight to assembly.

### Stage 5 — Assembler (deterministic)
`assembler/html_assembler.py` (Jinja2): stitch blocks, per-block MCQ steps (`QUIZ_DATA` ↔ `#quiz-area-N`), and the assessment carousel into the single output HTML in the required order, animations already inline. Writes to the run dir, **publishes** to `generated_tutorials/<course>/<session>.html`, and saves to the DB (best-effort).

### Stage 6 — Memory
`memory/cross_session.py`: persist this run's defined concepts, MCQ topics, every gate's feedback (de-duplicated), and an eval-history entry to the course's row. Ends the run.

> **Quality model.** Quality is enforced by (1) agent **self-validation** before each gate, (2) **advisory eval scores** displayed at each gate, and (3) **human review** at all five gates with element-level refine/reject. The older automated judge→retry→escalate loop (`steps/final_quality_check.py`, `quality_node`/`refine_node`) and the `final_quality` rubric remain in the codebase and are exercised by the DeepEval e2e harness, but are not part of the live compiled graph.

---

## 8. Agent / Stage Specifications

| Agent / Stage | Module | Input | Output | Capability | Eval-set |
|---|---|---|---|---|---|
| Image describer | `ingest/image_describer.py` | assets (pixels) | per-image description/placement/animation_worthy | vision | — |
| Block Divider | `steps/block_divider.py` | candidate blocks (+objectives, feedback) | heading tree + blocks JSON + validation | text | `block_divider` |
| Agent 1 (author) | `agents/agent1_content.py` | one block (+memory, supplementary, vision hints) | block HTML (source-only) + animate/skip verdicts + markers | text + layout | `content`, `visual-decision` |
| Agent 2 (animation) | `agents/agent2_animation.py` | image pixels + process narrative + ref library | inline namespaced SVG/CSS/JS animation | **vision** | `visual` |
| Agent 1 (apply) | `agents/agent1_content.py` | block + returned animations | block HTML with animations placed | deterministic | — |
| Agent 3 (MCQ) | `agents/agent3_mcq.py` | block content | `-END-` → `QUIZ_DATA[block]` | text | `mcq` |
| Agent 4 (assessment) | `agents/agent4_assessment.py` | full session + MCQ topics used | descriptive Q+A items | text | `assessment` |
| Stage eval | `steps/stage_eval.py` | stage output + rubric | advisory score per gate | text (judge) | reuses rubrics |
| Assembler | `assembler/html_assembler.py` | blocks + MCQ + assessment | final HTML | deterministic | (`final_quality`) |

---

## 9. Shared State Schema (`state.py`)

`TutorialState` (TypedDict, `total=False`) threaded through every node; per-block writes use dict reducers (`merge_dict`) and list reducers (`operator.add`). Key fields:

```python
# identity/config: run_id, course_id, input_type, raw_input_path, config, metadata, memory,
#                  status, current_node, review_stage
# ingest:          document (NormalizedDocument), candidate_blocks, supplementary_material
# division/HITL1:  division (BlockDivision), divider_validation, division_feedback[+],
#                  blocks_accepted, block_feedback, review_iteration
# build/HITL2-4:   built_blocks_list[], mcqs{block_id->QUIZ_DATA}(merge),
#                  content_accepted/content_feedback_map,
#                  animation_accepted/animation_feedback_map/animation_reject,
#                  mcq_accepted/mcq_feedback_map/mcq_block_feedback_map/mcq_reject,
#                  stage_feedback[+]
# assessment/HITL5: final_assessment[], assessment_accepted
# assembly:        session_html_draft, final_html, output_path
# eval:            eval_scores{stage->metrics}(merge), quality_report, escalations[+], retries
# (legacy final review: review_decision/review_edits/review_notes/final_feedback/final_approved)
```

---

## 10. Memory Design

Persistent, **course-scoped** store (`memory/cross_session.py`) — a `course_memory` row per course (key = course name, or `"<course> :: <module>"`), with four jsonb categories:

1. **Human feedback / corrections** — division edits + every gate's feedback (de-duplicated), injected into prompts on future runs of the course.
2. **Accepted few-shot signals** — `prior_concepts` (defined concepts) and `mcq_topics` from completed runs.
3. **Course/style trend** — `eval_history` (per-session scores) as a quality/difficulty signal.

Backing store: Supabase Postgres, with a local SQLite fallback (`persistence/local.py`) and a legacy `backend/memory_store/cross_session_memory.json` for offline/mock dev. Operational memory: LangGraph checkpoints (same fallback chain) so a paused/failed run resumes (`/api/runs/{id}/retry`).

---

## 11. Evaluation & Validation Framework

- **Rubric eval-sets** (`backend/eval-sets/`): `block_divider`, `content`, `visual-decision`, `visual`, `mcq`, `assessment`, `final_quality` — each with `rubric.json` (weighted dimensions, anchors, `pass_threshold` default 7.0) + `good_examples.json`/`bad_examples.json` (visual-decision also has `animate_examples.json`/`skip_examples.json`).
- **Per-gate advisory eval** (`steps/stage_eval.py`): an LLM judge scores `content`/`visual`/`mcq` output; the score is shown to the reviewer at that gate (advisory, not blocking).
- **Agent self-validation** (`skills/`): structural + rubric checks (`mcq_validator`, `assessment_validator`, `house_style.md`, `visual_patterns.md`) with `TB_SELF_VALIDATE_RETRIES` retries before any gate.
- **DeepEval harness** (`eval/deepeval_harness/`): `run_deepeval_golden` replays labelled good/bad exemplars through each agent's GEval rubric (+ Faithfulness) and reports judge accuracy vs. golden labels for `block_divider/content/visual/mcq/assessment`; `run_deepeval_e2e` scores an assembled tutorial against its source with the session-level `final_quality` rubric + Faithfulness. Requires a real API key (refuses mock).
- **v2/v3 rubric posture:** `content` rewards source-only fidelity + faithful reuse of source analogies (penalizes invented ones); `visual-decision` treats skipping a content/process image as a failure; `visual` rewards build order matching the described process + real diagram names; `assessment` penalizes analogy-framed questions.
- **Reporting:** per-run JSONL event log (`runs/<id>/log.jsonl`) of node start/done + scores; SSE stream to the UI; cost ledger.

---

## 12. Output Contract

- Single `.html`, scroll/stepper layout; one `<div class="block">` per step.
- **Order:** content block → Continue → MCQ step → Continue → next block → … → descriptive assessment carousel.
- **Gating MCQs:** a `QUIZ_DATA` JS object, `quizIndex → [ {question, options[], multi, correctIndexes[], explanation} ]`, rendered into `#quiz-area-N`; Continue locks until all answered.
- **Assessment:** read-through carousel of `{question, answer, question_type, blooms_level}` items — no options, no grading.
- **Animations:** inline `<style>`+`<svg>`(+JS), namespaced by `image_id`, `.anim` wrapper, auto-loop, reduced-motion safe — replacing the original `<img>` in place.
- **Self-contained:** no external JS deps (fonts allowed).

---

## 13. Tech Stack

- **Orchestration:** Python + LangGraph (nodes, typed state, dict/list reducers, conditional edges, `interrupt_before`, Postgres/SQLite/in-memory checkpointer).
- **LLM:** OpenRouter (OpenAI-compatible) by default; one-env switch to Google **Gemini** (`TB_LLM_PROVIDER`). Default model `anthropic/claude-sonnet-4.6` for text/vision/judge; vision used for image-describer + Agent 2. Prompt caching on the shared system prefix (`TB_PROMPT_CACHE`), per-call timeout (`TB_LLM_TIMEOUT`), temperature `TB_TEMPERATURE`, opt-in mock mode (`TB_LLM_MODE=mock`).
- **Ingestion:** `python-pptx` + image export; BeautifulSoup/lxml for HTML; Markdown for add-on material.
- **Assembly:** Jinja2 HTML shell + component templates (`backend/templates/`).
- **Persistence:** Supabase Postgres (pooled, `psycopg`) → local SQLite → in-memory; schema in `backend/supabase_schema.sql`.
- **API:** FastAPI (REST + SSE), CORS-open; run manager in `api/run_manager.py`.
- **UI:** React + Vite (`frontend/`): tabs **Workflow/Builder**, **Generated tutorials**, **Workflow animation**; gate components `BlockGate/ContentGate/AnimationGate/McqGate/AssessmentGate/FinalGate`, plus `CostPanel`, `DbStatus`.
- **Eval:** rubric-driven LLM judge + DeepEval (GEval + Faithfulness).
- **Cost:** OpenRouter USD ledger + live USD→INR (`cost.py`, `/api/cost`).
- **CLI:** `tutorial-builder run|info`.

---

## 14. Key API Endpoints (`api/app.py`)

| Method · Path | Purpose |
|---|---|
| `POST /api/builds` | Start a build (deck + optional material/material_text/images + metadata). |
| `GET /api/builds/{id}/events` | SSE stream of node/gate events. |
| `GET /api/runs`, `/api/runs/{id}`, `/api/runs/{id}/artifacts` | List/inspect runs; gate artifacts (division, blocks, mcqs, assessment, eval_scores). |
| `GET /api/runs/{id}/tutorial?download=` | Rendered tutorial HTML. |
| `POST /api/reviews/{id}/blocks` | Block gate: accept / feedback. |
| `POST /api/reviews/{id}/stage/{stage}` | Content / animation / mcq gate: accept / feedback_map / reject / block_feedback_map. |
| `POST /api/runs/{id}/mcq/edit`, `/assessment/edit` | In-place regenerate/reject one MCQ / assessment item. |
| `POST /api/reviews/{id}` | (Legacy) final review approve/edit/reject. |
| `POST /api/runs/{id}/finalize`, `/retry` | Assemble from current state; resume a stuck/failed run. |
| `GET /api/db-status`, `/api/cost`, `/api/tutorials`, `/api/courses` | Persistence backend; cost panel; published library; course autocomplete. |

---

## 15. Milestones (status)

1. **M1 — Ingestion + Block Divider + HITL gate** — ✅ (HTML + PPTX, image-describer, add-on material).
2. **M2 — Agent 1 + Agent 3 + Assembler** — ✅ gated tutorial.
3. **M3 — Agent 2 vision animations + reference library** — ✅ split into its own agent + gate.
4. **M4 — Agent 4 descriptive assessment + full Assembler** — ✅.
5. **M5 — Five HITL gates + per-gate advisory eval + self-validation** — ✅ (automated self-refine loop superseded).
6. **M6 — Memory + run resume + Supabase/SQLite persistence** — ✅.
7. **M7 — Web app (FastAPI + React) + cost panel + DeepEval harness** — ✅.

---

## 16. Open Questions / Risks

- **MCQ / assessment counts** — defaults 2 gating MCQs/block + 5 descriptive assessment items; confirm desired counts/difficulty per course.
- **PPTX fidelity** — complex decks (SmartArt, grouped shapes) may not export cleanly; may need a rasterize-slide fallback.
- **Animation generalization** — reference library covers SDLC patterns; novel diagram types (n8n/automation) rely on vision + the lesson's process narrative; build-order fidelity is the key quality risk to monitor (feed approved ones back via memory).
- **Process-narrative dependency** — Agent 2's build order is only as good as Agent 1's prose; if the prose under-describes a workflow image, the animation sequences generically.
- **Quality without an automated gate** — quality now leans on self-validation + advisory scores + human gates; advisory scores don't block, so monitor that reviewers act on low scores (the DeepEval harness is the offline backstop).
- **Vision cost/latency** — image-describer (capped at `TB_MAX_VISION_DESCRIBE`) + Agent 2 are the expensive paths; the animate/skip gate and the describe cap are the primary controls.
- **Supabase availability** — free projects auto-pause; the SQLite fallback keeps runs working but loses cross-machine sharing until Supabase returns.

---

*End of PRD v3.*
