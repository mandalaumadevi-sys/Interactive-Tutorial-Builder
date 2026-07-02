# Tools & Data Contracts — A Beginner's Guide

This document explains, in plain language:

1. **Part 1 — The tools (libraries) the project uses**: what each one is, *why* it's
   here, and *how* it's used in this codebase (with the file where it lives).
2. **Part 2 — The data contracts in `schemas.py`**: every Pydantic model that flows
   between stages, with hand-written examples. `NormalizedDocument` is covered in
   the most detail because it's the first artifact the whole pipeline depends on.

> **What is this project?** An *agentic workflow* that takes a teaching input
> (an HTML page or a PowerPoint `.pptx` deck) and turns it into an **interactive HTML
> tutorial** — with explanations, animations, and quizzes. The work is split into
> stages, and at each stage one "agent" (an LLM doing a focused job) hands a
> well-defined object to the next. Those well-defined objects are the *data contracts*.

---

## Part 1 — The Tools (Tech Stack)

Think of the project as an assembly line. Each tool below is a machine on that line.
They are grouped by the job they do.

### 1.1 Data shape & configuration

| Tool | One-line role |
|------|---------------|
| **Pydantic** | Defines and *validates* the shape of every object passed between stages. |
| **pydantic-settings** | Loads configuration (API keys, model names) from environment variables into a typed object. |
| **python-dotenv** | Reads those environment variables from the `backend/.env` file. |

**Pydantic** — *What it is:* a library where you describe data as a Python class, and it
automatically checks that real data matches that description (right types, required
fields present, custom rules satisfied). *Why here:* the pipeline has many stages; if
stage 2 sends a malformed object to stage 3, you want to fail loudly *at the boundary*
with a clear error, not silently produce a broken tutorial. *How used:* every model in
`schemas.py` is a Pydantic `BaseModel` (see Part 2). Example file: `schemas.py:12`.

**pydantic-settings** — *What it is:* a Pydantic add-on that maps environment variables
to a settings class. *Why here:* keeps all config in one typed, autocompleted place
instead of scattered `os.getenv()` calls. *How used:* the `Settings` class
(`config.py:24`) declares fields like `openrouter_api_key`, `text_model`,
`supabase_db_url`; pydantic-settings fills them from the environment.

**python-dotenv** — *What it is:* loads a `.env` file into environment variables.
*Why here:* so you can keep secrets (API keys, the Supabase URL) in `backend/.env`
out of the code. *How used:* loaded at startup so `Settings` can read the values.

```python
# config.py (simplified)
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openrouter_api_key: str = ""
    text_model: str = "anthropic/claude-sonnet-4.6"
    supabase_db_url: str = ""
    # ...reads these from backend/.env automatically
```

### 1.2 The workflow engine & its memory

| Tool | One-line role |
|------|---------------|
| **LangGraph** | The "conductor" — defines the stages (nodes) and the order/branches between them. |
| **langgraph-checkpoint-postgres** | Saves the workflow's progress to Postgres so a run can pause (for human review) and resume. |
| **psycopg** + **psycopg-pool** | The PostgreSQL driver and connection pool used to talk to Supabase. |

**LangGraph** — *What it is:* a framework for building multi-step LLM workflows as a
*graph* of nodes (steps) and edges (transitions), sharing one state object. *Why here:*
the tutorial is built in stages (ingest → divide into blocks → human review → write
content → make quizzes → assemble → evaluate → final review). LangGraph models exactly
that, including branches ("if quality failed, loop back and refine") and parallel work
(build several blocks at once). *How used:* `graph.py:345` builds a
`StateGraph(TutorialState)`, then `add_node(...)` / `add_edge(...)` wire the stages.
The shared state object is `TutorialState` in `state.py`.

```python
# graph.py (simplified)
from langgraph.graph import START, END, StateGraph
g = StateGraph(TutorialState)
g.add_node("ingest", ingest_node)
g.add_node("divide_blocks", divide_node)
g.add_edge(START, "ingest")
g.add_edge("ingest", "divide_blocks")
# ...and so on
```

**langgraph-checkpoint-postgres** — *What it is:* a LangGraph "checkpointer" that writes
the graph's state to PostgreSQL after each step. *Why here:* the workflow pauses for a
human to approve the blocks (HITL — Human In The Loop). To survive that pause (even a
server restart), the state must be saved. *How used:* `persistence/checkpointer.py:22`
builds a `PostgresSaver`; on first connect it auto-creates the `checkpoint*` tables in
Supabase.

**psycopg / psycopg-pool** — *What it is:* psycopg is the modern PostgreSQL driver for
Python; psycopg-pool keeps a small set of open connections ready to reuse. *Why here:*
*all* persistence (checkpoints, course memory, cost ledger, run list) lives in Supabase
Postgres — there is no local database. A pool avoids the cost of opening a new
connection for every query. *How used:* `persistence/db.py` opens one shared
`ConnectionPool`; every module borrows a connection with `with connection() as conn:`.

### 1.3 The LLM (the "brain")

| Tool | One-line role |
|------|---------------|
| **openai** | The client library used to call the language model. |
| **httpx** | A modern HTTP client; here it fetches a live USD→INR exchange rate for the cost panel. |

**openai** — *What it is:* the OpenAI Python SDK. *Why here:* this project calls Claude
models **through OpenRouter**, which speaks the OpenAI-compatible API, so the OpenAI
client works as the connector. *How used:* `llm/providers.py:72` lazily creates
`OpenAI(api_key=..., base_url="https://openrouter.ai/api/v1")` and sends chat requests.
The model names (e.g. `anthropic/claude-sonnet-4.6`) come from `Settings`.

> Note: there is also a **mock** LLM (`llm/mock.py`) used in tests and when
> `TB_LLM_MODE=mock`, so the pipeline can run end-to-end without spending money.

**httpx** — *What it is:* a fast, modern HTTP client (like `requests`, but newer).
*Why here:* the cost panel reports spend in INR using a *live* exchange rate. *How used:*
`cost.py:46` does `with httpx.Client(...) as client:` to fetch the current rate (with a
fixed fallback if offline).

### 1.4 Reading the input (ingestion & parsing)

| Tool | One-line role |
|------|---------------|
| **beautifulsoup4** | Parses HTML so the code can walk headings, images, and text. |
| **lxml** | The fast parser engine BeautifulSoup uses under the hood. |
| **python-pptx** | Reads PowerPoint `.pptx` files (slides, text, images). |
| **Pillow** | Image handling support (used via python-pptx for image data). |
| **markdown-it-py** | Converts Markdown text the LLM sometimes returns into HTML. |

**beautifulsoup4 (+ lxml)** — *What it is:* a library that turns messy HTML into a tree
you can query. *Why here:* the HTML input must be split at heading boundaries and have
its images catalogued. *How used:* `steps/block_divider.py:197` uses
`BeautifulSoup(html, "lxml").find_all("img")` to find images; `utils/io.py:64` uses it
to extract plain text. `lxml` is the parser passed as the `"lxml"` argument — it's fast
and lenient with imperfect HTML.

**python-pptx (+ Pillow)** — *What it is:* a library that reads/writes PowerPoint files.
*Why here:* one of the two supported inputs is a `.pptx` deck. *How used:*
`ingest/pptx_loader.py:22` opens `Presentation(path)`, walks slides and shapes, and
emits normalized HTML plus extracted images. Pillow is the imaging library python-pptx
relies on to handle those embedded images.

**markdown-it-py** — *What it is:* a Markdown→HTML renderer. *Why here:* LLMs sometimes
answer in Markdown; this safely converts it to HTML. *How used:* `tools/markdown.py:20`
renders with `MarkdownIt("commonmark", {"html": False})` (the `html: False` setting
blocks raw HTML injection — a safety choice).

### 1.5 Building the output

| Tool | One-line role |
|------|---------------|
| **jinja2** | Templating engine that fills the final tutorial HTML template with content. |

**jinja2** — *What it is:* a templating engine — an HTML file with `{{ placeholders }}`
that get filled with real values. *Why here:* the final tutorial is one big HTML file
assembled from a template plus the generated blocks and quizzes. *How used:*
`assembler/html_assembler.py:21` builds a Jinja2 `Environment(FileSystemLoader(...),
select_autoescape(...))` and renders the template. `select_autoescape` auto-escapes
values to prevent broken/unsafe HTML.

### 1.6 The interfaces (how you run it)

| Tool | One-line role |
|------|---------------|
| **FastAPI** | The web/API server the browser frontend talks to. |
| **uvicorn** | The server process that runs the FastAPI app. |
| **python-multipart** | Lets FastAPI receive uploaded files (the `.pptx`/HTML upload). |
| **Typer** | Builds the command-line interface (`tutorial-builder ...`). |
| **rich** | Pretty terminal output (tables, colors) for the CLI and logs. |

**FastAPI** — *What it is:* a modern Python web framework for building APIs. *Why here:*
the browser UI (`frontend/`) needs endpoints to upload a deck, stream progress, submit
review decisions, and fetch the finished tutorial. *How used:* `api/app.py:12` creates
the `FastAPI()` app and defines routes like `start_build` (which accepts an
`UploadFile`, `api/app.py:29`).

**uvicorn** — *What it is:* an ASGI server that actually runs an async web app. *Why
here:* FastAPI defines the app; uvicorn serves it. *How used:* `cli.py:140` runs
`uvicorn.run("tutorial_builder.api.app:app", ...)` for the `serve` command.

**python-multipart** — *What it is:* parses `multipart/form-data` (the format browsers
use to upload files). *Why here:* without it FastAPI can't accept the uploaded deck.
*How used:* implicitly, whenever an endpoint takes `UploadFile`/`Form(...)`.

**Typer** — *What it is:* a library for building CLIs from plain Python functions.
*Why here:* the project ships a `tutorial-builder` command (see `pyproject.toml`
`[project.scripts]`) with subcommands `info`, `run`, `eval`, `serve`. *How used:*
`cli.py` decorates functions with `@app.command()`.

**rich** — *What it is:* a library for colorful, formatted terminal output. *Why here:*
readable CLI output and logs. *How used:* `cli.py:9` uses `rich.console.Console`;
`cli.py:95` prints a results `Table`.

### 1.7 Testing

| Tool | One-line role |
|------|---------------|
| **pytest** | The test runner. |

**pytest** — *What it is:* the standard Python testing framework. *Why here:* to verify
the parser, assembler, MCQ parsing, and a full mock graph run keep working. *How used:*
`backend/tests/` holds `test_*.py`; run with `python -m pytest -q`.

---

## Part 2 — The Data Contracts (`schemas.py`)

### 2.1 First, what is a "Pydantic model"?

A **Pydantic model** is a Python class that describes the *shape* of some data. You list
the fields and their types; Pydantic then enforces that shape whenever you create an
object — converting types where sensible, filling defaults, and raising a clear error
when something is wrong.

```python
from pydantic import BaseModel

class SessionMeta(BaseModel):
    session_name: str = "Session"   # a string; defaults to "Session" if not given
    learning_objectives: list[str] = []

# Creating one:
meta = SessionMeta(session_name="Intro to SDLC", learning_objectives=["Explain SDLC"])
meta.session_name        # -> "Intro to SDLC"

# Pydantic rejects bad data instead of letting it through:
SessionMeta(session_name=123)   # still OK (coerced to "123")
SessionMeta(learning_objectives="not a list")  # -> ValidationError
```

**Why this matters for the project:** each stage of the workflow *produces* one of these
models and the next stage *consumes* it. The model is a **contract**: "I promise the data
I hand you looks exactly like this." If an LLM returns something malformed, validation
fails right at the handoff — easy to spot and fix.

Two Pydantic features you'll see below:
- **`Field(default_factory=list)`** — gives each new object its *own* empty list
  (a safe way to default to `[]`).
- **`@model_validator(mode="after")`** — a custom rule that runs *after* the fields are
  set, to enforce logic Pydantic can't express with types alone.

### 2.2 The star of the show: `NormalizedDocument`

This is the **first artifact** the pipeline produces (Stage 0, "Ingestion"). Both inputs —
an HTML page **and** a PowerPoint deck — are converted into this single, uniform shape.
After this point, *the rest of the pipeline doesn't care whether the source was HTML or
PPTX* — it only sees a `NormalizedDocument`. That's its whole purpose: **erase the
difference between input formats.**

```python
class NormalizedDocument(BaseModel):
    session_meta: SessionMeta              # title, course, objectives, language, source info
    normalized_html: str                   # the cleaned-up HTML body of the lesson
    assets: list[ImageRef] = []            # every image found, with context
```

Just three fields:

| Field | Type | What it holds |
|-------|------|---------------|
| `session_meta` | `SessionMeta` | Metadata: session/course name, learning objectives, language, and whether the source was `html` or `pptx`. |
| `normalized_html` | `str` | The lesson content as clean HTML — headings (`<h1>`–`<h4>`), paragraphs, lists, images. This is the "normalized" common format. |
| `assets` | `list[ImageRef]` | A catalogue of every image, each with the context needed to later decide "should this become an animation?" |

**Where it's created (the two `ingest` flows):**
- HTML input → `ingest/__init__.py:43` builds the `NormalizedDocument`.
- PPTX input → `ingest/pptx_loader.py:64` builds the `NormalizedDocument`.

**Where it's stored:** in the workflow's shared state — `state.py:42` declares
`document: NormalizedDocument`. Every later node reads `state["document"]`.

**Where it's consumed:** Stage 1 (block division) reads `normalized_html` to split the
lesson into blocks at heading boundaries, and reads `assets` to attach images to the
right block.

#### A real, hand-written example

Suppose the input is a slide deck titled *"Introduction to the SDLC"* with one diagram.
Ingestion would produce roughly this:

```python
NormalizedDocument(
    session_meta=SessionMeta(
        session_name="Introduction to the SDLC",
        course_name="Software Engineering Foundations",
        source_type="pptx",
        source_filename="sdlc_intro.pptx",
        learning_objectives=[
            "Describe the phases of the SDLC",
            "Explain why each phase exists",
        ],
        language="ENGLISH",
    ),
    normalized_html="""
        <h1>Introduction to the SDLC</h1>
        <p>The Software Development Life Cycle (SDLC) is the process teams use
           to plan, build, and maintain software.</p>
        <h2>The Five Core Phases</h2>
        <ul>
          <li>Requirements</li>
          <li>Design</li>
          <li>Implementation</li>
          <li>Testing</li>
          <li>Maintenance</li>
        </ul>
        <img id="img-2" src="assets/sdlc_diagram.png" alt="SDLC phases flow diagram">
    """,
    assets=[
        ImageRef(
            image_id="img-2",
            src="assets/sdlc_diagram.png",
            alt="SDLC phases flow diagram",
            caption="The five SDLC phases in order",
            nearby_heading="The Five Core Phases",
            slide_index=2,
            width=1280, height=720,
            format="png",
        ),
    ],
)
```

Read it as a sentence: *"This is the 'Introduction to the SDLC' session from the
Software Engineering course; here is its cleaned-up HTML; and here is the one image it
contained, which sits under the 'Five Core Phases' heading."* The next stage now has
everything it needs and never has to know it came from PowerPoint.

#### Its sub-models

**`SessionMeta`** (`schemas.py:18`) — the "about this lesson" card.

| Field | Default | Meaning |
|-------|---------|---------|
| `session_name` | `"Session"` | Lesson title shown to the learner. |
| `course_name` | `"Course"` | Which course it belongs to (also the key for cross-session memory). |
| `source_type` | `"html"` | `"html"` or `"pptx"` — the only place the original format is recorded. |
| `source_filename` | `""` | Original file name. |
| `learning_objectives` | `[]` | What the learner should be able to do afterward. |
| `language` | `"ENGLISH"` | Content language. |

**`ImageRef`** (`schemas.py:30`) — one image *plus the context to judge it*. The extra
fields (`alt`, `caption`, `nearby_heading`, `slide_index`) exist so a later agent can
decide whether the image is a meaningful concept diagram (worth animating) or just a logo
(skip it). `occurrences` counts repeats — a picture appearing on every slide is probably
chrome, not content.

### 2.3 The rest of the contracts, stage by stage

The models below are the handoffs between later stages. You don't need them to understand
`NormalizedDocument`, but they show how the whole line fits together.

#### Stage 1 — Block division (cut the lesson into teachable chunks)

- **`HeadingNode`** (`schemas.py:56`) — one heading: its `level` (1–4) and `text`.
  Together they form the document's outline.
- **`CandidateBlock`** (`schemas.py:61`) — a *rule-based* first cut: the deterministic
  HTML parser splits at hard heading boundaries. No LLM yet. Fields: `block_id`, `title`,
  `content_html`, `images`, `word_count`.
- **`Block`** (`schemas.py:71`) — the *final* block after the divider agent merges/splits
  candidates and a human approves them: "one cohesive concept per block." Adds
  `h2_sections_included`, `word_count_estimate`, `learning_objectives_hint`.
- **`BlockDivision`** (`schemas.py:83`) — the whole division result: the `heading_tree`,
  the list of `blocks`, a count, and the agent's `division_reasoning`.

```python
Block(
    block_id=1,
    title="What the SDLC Is and Why It Exists",
    h2_sections_included=["The Five Core Phases"],
    content_html="<h2>...</h2><p>...</p>",
    images=[ImageRef(image_id="img-2", src="assets/sdlc_diagram.png", ...)],
    word_count_estimate=180,
    learning_objectives_hint=["Describe the phases of the SDLC"],
)
```

#### Stage 3 — Per-block content & visuals (Agent 1 + Agent 2)

- **`VisualDecision`** (`schemas.py:94`) — an `Enum` with two values: `ANIMATE` or `SKIP`.
  (An `Enum` restricts a value to a fixed set of choices.)
- **`VisualVerdict`** (`schemas.py:99`) — the decision for one image: which `image_id`,
  `ANIMATE` or `SKIP`, the `visual_type` (e.g. `flowchart`, `lifecycle`), and a `reason`.
- **`Animation`** (`schemas.py:106`) — a finished inline animation: self-contained HTML
  (`<style>` + `<svg>` + minimal JS) tied to an `image_id`.
- **`BlockResult`** (`schemas.py:115`) — Agent 1's full output for one block: the authored
  `content_html`, the `visual_verdicts`, the `animations`, the `concepts_defined`, and
  `quality_issues` (non-empty means the block failed its self-checks and gets flagged for
  human review).

#### Stage 3/4 — Questions

- **`MCQ`** (`schemas.py:134`) — a multiple-choice question. Its field names mirror the
  `QUIZ_DATA` object the output HTML's JavaScript expects. This is the **best example of a
  validator** in the codebase:

  ```python
  @model_validator(mode="after")
  def _check(self) -> "MCQ":
      if len(self.options) < 2:            # must have at least 2 options
          raise ValueError("an MCQ needs at least 2 options")
      if not self.correct_indexes:         # must mark at least one correct answer
          raise ValueError("an MCQ needs at least one correct index")
      # ...indexes in range; single-answer questions have exactly one correct index
      return self
  ```

  So an MCQ that says "the answer is option #5" when there are only 3 options is rejected
  *immediately*, not shipped to a learner. Note also `correct_indexes` uses
  `Field(alias="correctIndexes")` with `populate_by_name=True` — it accepts the JS-style
  `correctIndexes` key *and* the Python-style `correct_indexes`. `to_quiz_entry()` emits
  the exact JS shape the frontend consumes.

- **`AssessmentQuestion`** (`schemas.py:176`) — an open-ended end-of-session question with
  a model answer (`question_type` short/long, `blooms_level`). Rendered as a read-through,
  no grading.

#### Stage 6 — Evaluation (does the tutorial meet the bar?)

- **`DimensionScore`** (`schemas.py:194`) — one graded dimension: `score` (0–10),
  `weight`, `passed`, plus `reason` and `improvement` text.
- **`EvalResult`** (`schemas.py:203`) — a stage's overall result: weighted `score`,
  `pass_threshold` (default 7.0), `passed`, and the list of `dimensions`.
- **`SelfValidation`** (`schemas.py:213`) — an agent grading *its own* output against its
  rubric; `improvement_notes()` summarizes what failed.
- **`FinalQualityReport`** (`schemas.py:232`) — the session-wide final check. Its clever
  bit is the `OWNER` map (dimension → which agent owns it) and `refine_target()`: if the
  report fails, it finds the worst failing dimension and returns *which stage to loop back
  to and re-run* (content, mcq, or assessment). This is what powers the "refine" loop in
  the graph.

```python
FinalQualityReport(
    overall_passed=False,
    dimensions=[
        DimensionScore(dimension="objective_coverage", score=5.5, passed=False,
                       reason="Objective 2 never addressed",
                       improvement="Add a block covering the testing phase"),
        DimensionScore(dimension="mcq_variety_across_session", score=8.0, passed=True),
    ],
).refine_target()   # -> "content"  (owner of the worst failing dimension)
```

---

## How it all connects (one-paragraph summary)

You give the system an HTML page or a `.pptx` deck. **Ingestion** (using *beautifulsoup4*
or *python-pptx*) converts it into a single **`NormalizedDocument`** — clean HTML plus an
image catalogue plus metadata. **LangGraph** drives the rest as a sequence of stages,
each producing the next **Pydantic contract**: `BlockDivision` → `BlockResult`s (content +
*animations*) → `MCQ`s and `AssessmentQuestion`s → a final HTML file assembled with
*Jinja2*. An **evaluation** stage (`EvalResult`, `FinalQualityReport`) decides whether to
ship or loop back and refine. Progress is **checkpointed to Supabase Postgres** (via
*psycopg* + *langgraph-checkpoint-postgres*) so the workflow can pause for human review and
resume. You drive it either from the **Typer** command line or the **FastAPI** web app
(served by *uvicorn*), and the LLM calls go to Claude via **OpenRouter** using the
*openai* client.

> **Want to go deeper on the HTML shape itself?** See the companion doc
> `docs/normalized_html_contract.md`, which specifies exactly what tags `normalized_html`
> is allowed to contain.

---

# Part 3 — Expected Presentation Questions & Answers

A reviewer-facing Q&A. Every answer is grounded in the actual code; file references are given
so you can open the source live if challenged. Questions are grouped by theme.

## A. Architecture & design choices

### Q1. Which architecture is used for this workflow, and why?

The workflow is a **stateful directed graph (a state machine) built with LangGraph** — see
`graph.py` (`build_graph`, a `StateGraph(TutorialState)`). Each stage is a **node**
(`ingest → divide → human_block_review → build → assessment → draft → quality → … → assemble →
memory → END`); the arrows are **edges**, and the branching points (`route_quality`,
`route_block_review`, `route_quality_review`) are **conditional edges** that pick the next node at
runtime.

**Why LangGraph (and not a plain script or a linear chain):**

1. **It is not linear — it has loops and branches.** Quality can *fail and loop back* to
   `refine → quality`, and a human can *reject* and send the flow back to `divide`. A graph models
   this naturally; a straight-line pipeline cannot.
2. **Human-in-the-loop (HITL) needs to pause and resume.** The graph is compiled with
   `interrupt_before=["human_block_review", "human_quality_gate"]` (`graph.py:378`). LangGraph
   *suspends* the run at those nodes, persists the entire state, and resumes exactly where it left
   off when the human responds — even across a server restart.
3. **Durability / checkpointing.** State is saved by a **PostgresSaver checkpointer** backed by
   Supabase (`persistence/checkpointer.py`). State is stored as plain dicts (`model_dump`) so it
   round-trips through the checkpointer cleanly (`graph.py` docstring).
4. **Fan-out concurrency.** Per-block work (Agent 1 + Agent 3 per block) runs in parallel across a
   `ThreadPoolExecutor` (`_MAX_WORKERS = 6`, `graph.py`), so a 5-block lesson builds ~5× faster
   than serial.

In one line: **LangGraph because the process is stateful, branching, resumable, and
human-gated — exactly the problems a graph engine with checkpointing solves.**

### Q2. Why a *multi-agent* design instead of one big prompt?

Each agent has one job and its own eval-set, which keeps prompts small, testable, and independently
improvable:

| Agent | Responsibility | File |
|---|---|---|
| Block Divider | group raw sections into 3–7 cohesive blocks | `steps/block_divider.py` |
| Agent 1 (content) | rewrite a block to house-style HTML **+ decide animate/skip per image** | `agents/agent1_content.py` |
| Agent 2 (animation) | turn one concept image into an inline SVG/CSS/JS animation (vision) | `agents/agent2_animation.py` |
| Agent 3 (MCQ) | per-block multiple-choice questions | `agents/agent3_mcq.py` |
| Agent 4 (assessment) | session-wide final assessment | `agents/agent4_assessment.py` |
| Judge | score the assembled tutorial against a rubric | `steps/final_quality_check.py` |

A single mega-prompt would be impossible to evaluate or debug, and a failure anywhere would
contaminate everything. Splitting the work lets us **fan out, retry, and judge each piece
independently.**

### Q3. What is `TutorialState` and why store it as plain dicts?

`TutorialState` (`state.py`) is the single shared object that flows through every node — it holds
the metadata, the division, built blocks, MCQs, the draft HTML, the quality report, retry counters,
etc. It is stored as plain dictionaries (not live Pydantic objects) so it can be **serialized to the
checkpointer and rebuilt on resume**; nodes reconstruct Pydantic models on demand. This is what
makes pause/resume and restart-survival possible.

## B. Images — identification and selection

### Q4. What is the logic behind identifying the images?

Images are catalogued during **ingestion**, before any LLM sees them:

- **HTML input** (`ingest/__init__.py`, `_inventory_images`): every `<img>` is scanned. Identical
  `src`s are **de-duplicated** and we record how many times each one appears (`occurrences`). Each
  unique image becomes an `ImageRef` with a stable `image_id` (`img_01`, `img_02`, …), its `src`,
  its `alt` text, and its `occurrences` count.
- **PPTX input** (`ingest/pptx_loader.py`, `_export_picture`): each picture shape on each slide is
  exported to a file and turned into an `<img>` placed at the slide's position; the shape name
  becomes the `alt`.

So "identifying images" = **build a clean, de-duplicated inventory of every image with an id, its
text label, and how often it repeats** (`ImageRef` in `schemas.py:30`). Images are then attached to
their owning block during block division (`block_divider.py`, `_images_from_html` + `_src_image_map`).

### Q5. The PPT may have **more than 60 images** — how do you know which images to select (to animate)?

This is handled deliberately; the system **does not** animate everything. Two filters work together:

1. **The `occurrences` filter (mechanical, free).** Logos, bullet icons, and decorative branding
   repeat on many slides, so they have a high `occurrences` count. The image inventory already flags
   these, and the prompt is told to skip "a repeated logo/bullet (high occurrences)".

2. **Agent 1's per-image concept decision (the real selector).** Agent 1 *owns* the animate/skip
   decision for the images in its block. Its system prompt (`prompts/agent1_system.md`) states
   literally:

   > *"IMAGE DECISION RULES (you own this decision — a 60-slide deck must not yield 60 animations)"*

   - **SEND TO AGENT 2** only if the image is **concept-bearing**: a process/flowchart,
     architecture/component diagram, lifecycle/state machine, layered hierarchy, or a structured
     comparison.
   - **SKIP** if it is a photo/analogy illustration, a UI screenshot, decorative/branding, a repeated
     logo/bullet, or anything fully explainable in text.
   - It is calibrated with **labelled ANIMATE / SKIP examples** (`load_visual_decision_examples`,
     eval-set `visual-decision`) so borderline calls are consistent.
   - It must pick **at most one animation per concept**.

3. **A hard cap on what the vision model even sees.** Only the first **4** image sources per block
   are sent to the vision model (`agent1_content.py`, `_vision_srcs`: `[...][:4]`), so cost stays
   bounded regardless of deck size.

So for a 60-image deck the answer is: most images are repeats or decorative and are filtered by
`occurrences`/text-explainability; of the genuinely concept-bearing diagrams, Agent 1 selects at
most one animation per concept — typically a handful, not 60. **The selection is by *instructional
value*, not by count.**

### Q6. How is an image actually turned into an animation?

For each image Agent 1 marks `send_to_agent2`, it leaves a marker `<!--HF_ANIM:img_id-->` in its
HTML, then calls **Agent 2** (`agents/agent2_animation.py`), which uses the **vision model** to look
at the image and emit a **self-contained, namespaced inline SVG/CSS/JS animation**. Agent 1 then
substitutes that animation in at the marker (`_place`); markers for skipped images are stripped
(`agent1_content.py`). Everything ends up inline so the final file is a single self-contained HTML.

## C. Cost & the API key

### Q7. How can we see the cost of the key / what the app has spent? Where is this in the code?

There is first-class cost tracking in **`cost.py`**, surfaced through **`GET /api/cost`**
(`api/app.py:133`) and shown in the frontend cost panel.

- **Per-call cost is real, not estimated.** OpenRouter returns the actual USD cost of every
  generation when we ask for it (`usage: {include: true}`). `record_call_cost()` accumulates it into
  a small JSON ledger stored in Supabase (`cost_ledger` table, `id='global'`). It is thread-safe and
  **never raises** — cost accounting can't break a generation.
- **`cost_summary()`** returns, in one payload: this app's all-time spend (`app_spend_usd`), the
  **shared key's** total usage (`key_usage_usd`), remaining credit (`remaining_credit_usd`), the key
  limit, the number of LLM calls, and whether the key was reachable.
- **Shared key → "others" is *derived*, not observed.** Because the OpenRouter key is shared with
  other apps, we can only *infer* other apps' spend with a baseline formula:

  ```
  others = (key_usage_now − baseline_key_usage) − (app_spend_now − app_spend_at_baseline)
  ```

  The baseline is captured the first time `/api/cost` runs with a reachable key.
- **INR conversion** is included: a live USD→INR rate is fetched from a free FX endpoint and cached
  hourly (`usd_to_inr_rate`), falling back to a configured fixed rate when offline — so every USD
  figure also has an `_inr` companion.

To demo it live: open the cost panel in the UI, or `curl http://127.0.0.1:8000/api/cost`.

### Q8. Where do you configure the model / key, and what models are used?

All in `config.py` (a cached `Settings` object) and `backend/.env`. Defaults are
`anthropic/claude-sonnet-4.6` for **text, vision, and judge** (each separately overridable via
`TB_TEXT_MODEL` / `TB_VISION_MODEL` / `TB_JUDGE_MODEL`). The key is `OPENROUTER_API_KEY`. Per-stage
model resolution lives in `config.py` (`divider_model`, `agent1_model`, `agent2_model`, etc.), so any
stage can point at a different model without touching agent code.

### Q9. What if there's no API key, or we want to test for free?

The client self-routes to a built-in **mock LLM** when there's no key or `TB_LLM_MODE=mock`
(`llm/client.py`). It returns canned fixtures so the *entire* graph runs end-to-end at **zero cost**
— used by the test suite (`TB_LLM_MODE=mock pytest`) and for wiring demos. `tutorial-builder info`
prints whether you're in `real` or `mock` mode.

## D. Quality, human review & reliability

### Q10. How do you know the generated tutorial is good enough? What happens if it isn't?

A **judge model** scores the assembled tutorial against a rubric and produces a `FinalQualityReport`
(per-dimension scores + overall pass/fail) — `steps/final_quality_check.py`. The routing
(`route_quality` in `graph.py`) then:

- **pass** (≥ `TB_PASS_THRESHOLD`, default **7.0**) → `assemble`;
- **fail, retries remaining** → `refine → quality` again (bounded by `TB_MAX_REFINE_ATTEMPTS`,
  default **1**);
- **fail, retries exhausted** → escalate to the **second human gate** (`human_quality_gate`), where a
  person approves/edits or rejects (reject loops back to `divide`).

So quality is **self-correcting with a bounded retry, then escalated to a human** — it never silently
ships a failing tutorial or loops forever.

### Q11. What are the two human-in-the-loop checkpoints, and how do they technically work?

1. **Block-division review** — after the lesson is cut into blocks, before any expensive build.
2. **Final review** — only if auto-quality fails after refinement.

Technically they are LangGraph **interrupts** (`interrupt_before=[…]`, `graph.py:378`). The run
pauses, the full state is checkpointed to Postgres, and the API exposes the pending decision; the UI
posts the human's choice (`POST /api/reviews/{run_id}/blocks` and `/api/reviews/{run_id}`), which
resumes the graph. Feedback is also written to course memory.

### Q12. How do you handle malformed LLM output (e.g., broken JSON)?

The LLM client extracts JSON robustly (`llm/base.py`, `extract_json`, including fenced ```json```
blocks) and runs a **small retry loop** (`llm/client.py`). Every stage's output is then validated
against a **Pydantic contract** (`schemas.py`), so bad data is rejected at the boundary rather than
flowing downstream. The block divider additionally has a validation step (`divider_validation`).

### Q13. Does the workflow survive a crash or server restart mid-run?

Yes. The **PostgresSaver checkpointer** persists graph state (and both pending HITL interrupts) to
Supabase (`persistence/checkpointer.py`), and `setup()` is idempotent. A run paused for human review
survives a restart and resumes from the same node.

## E. Output, scale & memory

### Q14. Why is the output a single self-contained HTML file?

Portability: animations (inline SVG/CSS/JS), MCQs (`QUIZ_DATA`), and the assessment are all stitched
into one HTML "stepper" shell by the **Jinja2 assembler** (`assembler/`). It opens in any browser
with no server, no build step, and no external assets.

### Q15. How does it scale to large lessons?

Per-block work fans out across a thread pool (`_MAX_WORKERS = 6`, `graph.py`), so blocks are built
concurrently. Block count itself is bounded (3–7 cohesive blocks), MCQs per block are bounded
(`TB_MCQ_PER_BLOCK`, default 2; min/max 2–3), and the vision model sees at most 4 images per block —
so cost and latency stay bounded even for big inputs.

### Q16. What is "memory" used for?

Course-scoped memory (`memory/`) stores already-defined concepts, MCQ topics, human feedback, and
eval history. Agent 1 is told to **reference, not re-explain**, a concept that earlier blocks or
prior sessions already covered — which avoids repetition and makes a multi-session course feel
coherent. Human feedback from the review gates is saved here too.

### Q17. How would you extend this — e.g., support a new input format or a new question type?

Add a loader under `ingest/` that emits the same `NormalizedDocument` contract (the rest of the
pipeline is format-agnostic), or add an agent + its Pydantic contract + an eval-set and wire one node
into `graph.py`. Because every stage talks through a typed contract, extensions are localized.

---

> **Tip for the demo:** the fastest way to prove any of the above live is
> `TB_LLM_MODE=mock tutorial-builder run backend/samples/software_development_models.html --session "Demo"`
> (full graph, zero cost) and `curl http://127.0.0.1:8000/api/cost` (real spend ledger).
