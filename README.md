# Interactive Tutorial Builder — Agentic Workflow

Converts a course session (**HTML** or **PPTX**) into a single, self-contained **interactive HTML
tutorial**: content is split into blocks, each block is rewritten as a guided learning step with an
inline animation replacing concept diagrams, every block is gated by mandatory MCQs, and the session
ends with a multi-question assessment.

Built on **LangGraph** with memory, eval-sets, an LLM judge, bounded self-refinement, and **two
human-in-the-loop checkpoints** (block-division review and final review) surfaced through a web UI.

See `PRD.md`, `PLAN.md`, and `docs/normalized_html_contract.md` for the full design.

---

## Project structure

```
interactive tutorial builder/
├── backend/                 ← all the Python (the agentic pipeline + API)
│   ├── src/tutorial_builder/   config, graph, agents, ingest, assembler, llm, api …
│   ├── templates/  prompts/  eval-sets/  reference_animations/  samples/
│   ├── runs/  memory_store/    (runtime output — created as you build)
│   ├── tests/
│   ├── pyproject.toml
│   └── .env  .env.example      (your API key + settings live here)
├── frontend/                ← the web UI (React + Vite)
│   ├── index.html             (Vite entry)
│   ├── package.json  vite.config.js
│   └── src/
│       ├── App.jsx  main.jsx  api.js  pipeline.js  styles.css
│       └── components/         UploadCard, BlockGate, ContentGate, AnimationGate,
│                               McqGate, FinalGate, PipelineTab, TutorialsTab, CostPanel, DbStatus
├── .venv/                   ← Python virtual environment (shared, gitignored)
├── backend.sh               ← start the API only            (port 8000)
├── frontend.sh              ← start the web UI (Vite dev)    (port 5173)
├── run.sh                   ← start BOTH together
└── docs/  PRD.md  PLAN.md
```

**Frontend vs backend, simply:** everything in `frontend/` is the React web app you click on;
everything in `backend/` is Python that does the actual work. They run as two separate servers
and talk over HTTP. The UI has **three tabs**: **Workflow** (upload → the 5 review gates → output),
**Generated tutorials** (your library of finished builds), and **Workflow animation** (a live map
showing which stage the run is in). A header badge shows whether persistence is on Supabase or the
local SQLite fallback.

---

## One-time setup

```bash
cd "interactive tutorial builder"
python3 -m venv .venv
source .venv/bin/activate
pip install -e backend          # installs the backend package + dependencies
( cd frontend && npm install )  # installs the React/Vite frontend deps (Node 18+)
```

Add your OpenRouter key in `backend/.env` (copy from `backend/.env.example`):

```
OPENROUTER_API_KEY=sk-or-...
```

With no key present the pipeline runs end-to-end on a built-in **mock LLM** (set `TB_LLM_MODE=mock`),
useful for testing the wiring at zero cost. Models, MCQ counts, thresholds, and paths are all
configurable in `backend/.env` (see `backend/.env.example`).

---

## Run it

### Both servers at once (easiest)
```bash
./run.sh
```
Then open **http://127.0.0.1:5173**. (Ctrl-C stops both.)

### Or run them separately (two terminals)
```bash
./backend.sh      # terminal 1 → API on http://127.0.0.1:8000
./frontend.sh     # terminal 2 → UI  on http://127.0.0.1:5173
```

On upload you can also attach **add-on material** — extra reading material / hands-on (pasted or a
`.md`/`.txt`/`.html` file) and extra images (e.g. a final workflow diagram missing from the deck).
Decks rarely contain the full lesson; these are merged into the source so the tutorial covers the
hands-on detail and the images get described, placed, and animated like any other visual.

In the UI: on the **Workflow** tab upload a session → step through the five review gates
(**block division → content → animations → MCQs → final review + assessment**), accepting or
refining each → open / download the result. The **Workflow animation** tab shows live which stage
the run is in; the **Generated tutorials** tab lists every finished build. Every gate's feedback is
saved to course memory (de-duplicated, so the same note is never stored twice).

> `run.sh`/`frontend.sh` run `npm install` on first use, then the Vite dev server (`npm run dev`).
> For a static production bundle: `cd frontend && npm run build` → `frontend/dist/`.
> The frontend defaults to the API at `http://<host>:8000`. To point it elsewhere, open it with
> `?api=http://host:port`, or set `window.API_BASE` (see `frontend/src/api.js`).

### Database / persistence

Persistence (runs, resumable checkpoints, and course memory/feedback) uses **Supabase Postgres**
when reachable. You don't connect it manually — the backend opens a pooled connection at startup
from `SUPABASE_DB_URL` in `backend/.env`; you only need the Supabase project to be **active** (free
projects auto-pause). If Supabase is unreachable (paused/deleted/wrong creds), the app **automatically
falls back to a local SQLite store** at `<runs_dir>/local_store.sqlite` so runs and feedback still
persist — and switches back to Supabase the moment it's reachable again (no code change). Check the
current backend at `GET /api/db-status` or the header badge. A `FATAL: tenant/user … not found`
error means the Supabase project is paused or the ref is stale — restore it in the dashboard.

### Command line (no UI)
```bash
source .venv/bin/activate
tutorial-builder info        # shows config + whether the LLM is "real" or "mock"
tutorial-builder run backend/samples/software_development_models.html \
  --course "Practical SE" --module "SDLC"
# → backend/runs/<run_id>/<...>_tutorial.html
```

---

## Pipeline

Five human-in-the-loop gates (👤). Each producing stage runs across all blocks concurrently, then
pauses for review; **accept** advances, **refine** regenerates that stage with your feedback and
re-presents it. Each gate shows the stage's advisory eval score.

```
ingest (+image descriptions) → divide → 👤 block review ─(accept)─┐  └(feedback)→ divide
   ┌──────────────────────────────────────────────────────────────┘
   ▼ Agent 1 author content + animate/skip → 👤 content review ─(accept)─┐  └(refine)→ content
   ▼ Agent 2 animations                     → 👤 animation review ─(accept)─┐  └(refine)→ animation
   ▼ Agent 3 per-block MCQs                  → 👤 MCQ review ─(accept)─┐  └(refine)→ mcq
   ▼ Agent 4 assessment → draft → quality (self-refine once) → 👤 final review + accept assessment
                                                                ├ approve → assemble → memory → END
                                                                └ reject  → divide
```

| Stage | What it does | Eval-set |
|---|---|---|
| Ingest (`ingest/`) | HTML normalize / PPTX→HTML → `NormalizedDocument` + image inventory | — |
| Image describer (`ingest/image_describer.py`) | vision-caption every image → `{description, placement, animation_worthy}` (both flows; heuristic fallback) | — |
| Block Divider (`steps/block_divider.py`) | group candidate sections into 3–7 cohesive blocks | `block_divider` |
| Agent 1 (`agents/agent1_content.py`) | **`author`**: rewrite block to house-style HTML + animate/skip per image (uses the vision hints). **`apply_animations`**: place Agent 2's output | `content`, `visual-decision` |
| Agent 2 (`agents/agent2_animation.py`) | vision → inline namespaced SVG/CSS/JS animation (ref library) | `visual` |
| Agent 3 (`agents/agent3_mcq.py`) | per-block MCQs (`-END-` → `QUIZ_DATA`) | `mcq` |
| Agent 4 (`agents/agent4_assessment.py`) | session-wide assessment | `assessment` |
| Stage eval (`steps/stage_eval.py`) | advisory score per gate (content / visual / mcq) | reuses above |
| Assembler (`assembler/`) | stitch blocks + MCQs + assessment into the stepper shell | `final_quality` |
| Quality + refine (`steps/final_quality_check.py`, `graph.py`) | LLM judge → self-refine once → always escalate to the final human gate with metrics | `final_quality` |
| Memory (`memory/`) | course-scoped concepts, MCQ topics, feedback, eval history | — |

The web UI has two tabs: **Builder** (upload + the five review gates) and **Execution pipeline**
(a read-only live map that highlights the current stage and which gate is waiting on you).
Animation generation is its own reviewable stage (split out of Agent 1) so each agent's output is
gated independently. With no API key, set `TB_LLM_MODE=mock` to run the whole flow offline.

## Testing
```bash
cd backend && TB_LLM_MODE=mock pytest -q
```
