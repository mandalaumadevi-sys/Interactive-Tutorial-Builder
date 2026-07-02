# Build Plan — Interactive Tutorial Builder (Agentic Workflow)

Companion to `PRD.md` and `docs/normalized_html_contract.md`. This is the *how we build it* plan: phases, sequencing, deliverables, and acceptance criteria.

Stack (locked): **Python + LangGraph**, dual ingestion (HTML + PPTX), vision-based animations, two HITL checkpoints, memory + eval-sets + self-refine.

---

## 1. Guiding principles

1. **One pipeline, two front doors.** HTML and PPTX both normalize into the *same* contract (`normalized_html` + `assets`). Nothing downstream knows the source format.
2. **Walking skeleton first.** Get an end-to-end tutorial rendering with stubbed/mock LLM calls before making any single agent "good." Wire the graph, then fill the nodes.
3. **Eval-sets are the spec.** Each agent's rubric (`project/eval-sets/*`) defines "done." Build the agent against its rubric, not against vibes.
4. **Deterministic where possible.** Assembly, parsing, and format conversion (`-END-` → `QUIZ_DATA`) are plain code, not LLM calls. Reserve LLMs for division, content, animation, MCQs, and judging.
5. **Bounded autonomy.** Self-refine retries once, then escalates to a human. The graph must always terminate.

---

## 2. Component inventory (what gets built)

| # | Component | Type | Eval-set |
|---|---|---|---|
| C0 | Ingestion (HTML normalizer + PPTX→HTML) | deterministic | — |
| C1 | Block Divider | LLM node | `block_divider` |
| C2 | HITL #1 (division review/loop) | interrupt + UI | — |
| C3 | Agent 1 — Content & layout | LLM node | `content`, `visual-decision` |
| C4 | Agent 2 — Animation (vision + ref lib) | LLM (vision) node | `visual` |
| C5 | Agent 3 — MCQ generator (+ `-END-`→`QUIZ_DATA`) | LLM + parser | `mcq` |
| C6 | Agent 4 — Final assessment | LLM node | `assessment` |
| C7 | Assembler (blocks+MCQ+anim → HTML) | deterministic | `final_quality` |
| C8 | Judge harness (rubric scorer) | LLM | uses all rubrics |
| C9 | Self-refine controller | graph logic | — |
| C10 | HITL #2 (final review/regen) | interrupt + UI | — |
| C11 | Memory (feedback, few-shot, course profile) | store | — |
| C12 | Run state / checkpointer + logging | infra | — |

---

## 3. Phased delivery

### Phase 0 — Foundations (infra)
**Build:** repo skeleton, `TutorialState` schema, LangGraph graph compiled with SQLite checkpointer, mock LLM client (returns canned fixtures), per-run JSONL logging, config loader (mcq counts, thresholds, max-refine).
**Deliverable:** an empty graph that runs node→node→END on a fixture with mocks.
**Acceptance:** `run(fixture)` completes; state checkpoints written; run resumable after a forced interrupt.

### Phase 1 — Ingestion (C0)
**Build:** HTML normalizer (strip chrome, map components, localize images, occurrences count, invariants check). Then PPTX path (`python-pptx` → same contract; image export; SmartArt rasterize fallback).
**Deliverable:** `getting-started.html` → valid `NormalizedDocument`; a sample `.pptx` → equivalent `NormalizedDocument`.
**Acceptance:** all §6 contract invariants pass for both flows; images land in `assets/` with manifest.

### Phase 2 — Block Divider + HITL #1 (C1, C2)
**Build:** divider node using `project/prompts/Block_division.md` with structured-output; HITL interrupt that surfaces (a) heading tree, (b) block count, (c) per-block titles+headings+reasoning; feedback loop back into the divider.
**Deliverable:** approved `BlockDivision` for the SDLC sample matching the reference 5-block split.
**Acceptance:** 3–7 blocks; division passes `block_divider` eval ≥ threshold; feedback re-division works and is written to memory.

### Phase 3 — Walking skeleton to HTML (C3-lite, C5, C7)
**Build:** Agent 1 authoring block HTML **without** animations (skip all images for now); Agent 3 MCQs + `-END-`→`QUIZ_DATA` parser; Assembler producing the full stepped HTML (content→continue→MCQ→…) with the shared CSS/JS shell.
**Deliverable:** a rendering, gated tutorial from the SDLC sample (static images, real MCQs).
**Acceptance:** output structurally matches `sdlc_models_session_scroll_v2.html`; `QUIZ_DATA` wired to `quiz-area-N`; continue-gate locks until answered.

### Phase 4 — Animations (C4, finish C3)
**Build:** Agent 1 visual-decision (animate/skip per `visual-decision` rubric); Agent 2 vision pipeline (see image + match reference library: waterfall/agile/v-model) emitting namespaced inline SVG/CSS/JS; Agent 1 embeds returned animation in place of the `<img>`.
**Deliverable:** SDLC tutorial with the three diagrams replaced by working animations.
**Acceptance:** decorative images skipped; concept images animated; animations self-contained, auto-loop, reduced-motion safe; `visual` eval ≥ threshold.

### Phase 5 — Final assessment + parallelism (C6, fan-out)
**Build:** Agent 4 session-level assessment as concluding step; convert per-block work to a LangGraph fan-out (parallel branches over blocks) with dict reducers.
**Deliverable:** complete tutorial incl. final assessment; blocks generated in parallel.
**Acceptance:** wall-clock drops vs sequential; concurrent block writes merge without loss; final assessment step renders.

### Phase 6 — Evaluation + self-refine (C8, C9)
**Build:** judge harness (weighted rubric scorer per stage); self-refine controller (score < threshold → retry with critique once → escalate). Wire as conditional edges after each producing stage.
**Deliverable:** every stage scored + logged; low scores trigger one retry then escalate.
**Acceptance:** a deliberately bad fixture produces a retry then an escalation (no infinite loop); scores logged per run.

### Phase 7 — HITL #2 (C10)
**Build:** final-review interrupt presenting rendered tutorial + escalations; approve → END, or regenerate (whole / specific block / MCQ / animation) → loop to the right stage.
**Deliverable:** human can approve or send targeted regen requests.
**Acceptance:** targeted regen re-runs only the relevant branch; approval finalizes; corrections written to memory.

### Phase 8 — Memory (C11)
**Build:** course-scoped store for (1) feedback/corrections, (2) accepted few-shot examples, (3) course/style profile; inject into prompts on subsequent runs.
**Deliverable:** a second session in the same course reflects prior feedback/style.
**Acceptance:** approved examples retrievable as few-shot; course profile applied; feedback changes future divisions/style.

### Phase 9 — Hardening
**Build:** error handling (bad input, oversized decks, vision failures), cost/latency tuning, docs, regression fixtures for each eval-set.
**Acceptance:** runs on ≥3 distinct sessions end-to-end; all eval-sets green; resumable; documented.

---

## 4. Dependency / sequencing graph

```
P0 Foundations
   └─▶ P1 Ingestion ─▶ P2 Divider+HITL1 ─▶ P3 Skeleton(HTML+MCQ+Assemble)
                                              ├─▶ P4 Animations
                                              └─▶ P5 Final assessment + fan-out
                                                     └─▶ P6 Eval + self-refine
                                                            └─▶ P7 HITL2
                                                                   └─▶ P8 Memory ─▶ P9 Harden
```
Critical path: P0→P1→P2→P3. P4 and P5 can proceed in parallel once P3 lands.

---

## 5. Runtime flow (what one run does)

1. **Ingest** → normalized doc (HTML or PPTX).
2. **Divide** → blocks + heading tree → **pause (HITL #1)** → loop until approved.
3. **Fan out per block (parallel):**
   - Agent 1: visual-decision → (animate) dispatch to Agent 2 → author HTML → embed animation.
   - Agent 3: MCQs → `QUIZ_DATA`.
4. **Agent 4** → final assessment.
5. **Assemble** → single HTML.
6. **Evaluate** each stage → below threshold → retry once → else escalate.
7. **Pause (HITL #2)** → approve or targeted regen.
8. **Finalize** → write output + update memory.

---

## 6. Key decisions already locked (from PRD Q&A)

- Greenfield; LangGraph; HTML **and** PPTX flows; vision + reference-library animations.
- HITL at block division **and** final review.
- MCQs emitted as the output HTML's `QUIZ_DATA` shape (`-END-` internal → converted).
- Memory = feedback/corrections + few-shot + course profile (+ run checkpoints).
- Self-refine = retry once, then escalate to human.
- Defaults: **2 gating MCQs/block, 5 in final assessment** (configurable).

---

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| PPTX SmartArt/grouped shapes export poorly | Rasterize-slide fallback → single concept image (logged). |
| Vision animation diverges from real diagram | Reference-library matching + `fidelity_to_source` eval dim; escalate on low score. |
| Novel diagram types (no ref pattern) | Grow library via memory (approved animations become exemplars). |
| Parallel state collisions | Dict reducers keyed by `block_id`; no shared mutable writes. |
| Refine loop never terminates | Hard cap (1 retry) → escalate to HITL #2. |
| Cost/latency from vision step | animate/skip gate before Agent 2; cache by image hash. |

---

## 8. Definition of Done (v1)

- Both ingestion flows produce a valid normalized document.
- A full SDLC-equivalent tutorial renders, structurally matching the reference output, with: gated MCQs, three working animations, and a final assessment.
- All seven eval-sets pass at threshold on the reference session.
- Both HITL checkpoints function (division loop + final regen).
- Memory persists across two runs of the same course.
- A run can be interrupted and resumed from checkpoint.

---

*End of build plan.*
