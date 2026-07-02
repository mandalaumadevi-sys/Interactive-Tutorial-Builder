# Animation Flow — Block by Block (Start to End)

How a single image becomes a self-contained, on-page animation.
Traced with one **real** image from the `software_development_models.html` slide deck.

Each block below shows: **who runs it · LLM or not · INPUT it receives · OUTPUT it produces.**

---

## The seed: one parsed image

Before the animation flow starts, the `ingest` phase (BeautifulSoup, **no LLM**) has already
turned the raw 163 KB deck into candidate blocks and inventoried every image. One of them:

```
ImageRef
  image_id    : img_b4_03
  src         : https://.../static/.../waterfall-phases.png
  alt         : "Waterfall model phases"
  caption     : "Requirements -> Design -> Implementation -> Testing -> Deployment"
  size        : 900x520
  occurrences : 1
```

This object is the single source of truth for everything below. It carries the **exact image
URL** (needed for vision), a **stable id** (used as the placement anchor), and **size/occurrence
signals** (used to decide animate vs skip). No tokens spent yet.

---

## BLOCK 1 — Decide: animate or skip?

| | |
|---|---|
| **Who** | Agent 1 (content builder) |
| **LLM?** | YES — text + vision |
| **Runs** | once per block, judges all images in the block together |

**INPUT** (the image-decision slice of Agent 1's prompt):

```
IMAGES IN THIS BLOCK:
- img_b4_02: alt='' size=32x32 occurrences=56        <- tiny + repeated 56x  => icon
- img_b4_03: alt='Waterfall model phases' size=900x520 occurrences=1   <- big + unique => concept
LABELLED EXAMPLES - ANIMATE: [process flows, diagrams, ...]
LABELLED EXAMPLES - SKIP:    [logos, icons, decorative, ...]
+ the images themselves attached as VISION
```

**OUTPUT** (`image_decisions` inside Agent 1's JSON):

```json
[
  {"image_id": "img_b4_02", "decision": "skip",           "reason": "decorative icon"},
  {"image_id": "img_b4_03", "decision": "send_to_agent2", "visual_type": "process_flow"}
]
```

Agent 1 also drops a placement marker into its rewritten lesson HTML:
`<!--HF_ANIM:img_b4_03-->`.

➡️ Only `img_b4_03` continues. **The blocks below run once per `send_to_agent2` image.**

---

## BLOCK 2 — Pick a reference style

| | |
|---|---|
| **Who** | `agent2.animate()` helper |
| **LLM?** | NO — rule-based keyword match |
| **Runs** | once per animated image |

**INPUT:** the block title / concept text — `"Waterfall model phases"`.

**LOGIC:** keyword table lookup (`waterfall`, `agile`, `scrum`, `v-model`...), then read that
reference file and trim to the first 4000 chars (`_MAX_REF_CHARS`).

**OUTPUT:**

```
ref_name = "waterfall-model-animation.html"
ref_html = "<...4 KB of the real reference animation, used as a structural template...>"
```

If no keyword matches, the reference block is simply left out. Deterministic — no LLM needed
to pick a filename.

---

## BLOCK 3 — Generate the animation

| | |
|---|---|
| **Who** | Agent 2 (animation generator) |
| **LLM?** | YES — text + vision |
| **Runs** | 1 base call (+ up to 2 retries from Blocks 4 & 5) |

**INPUT the model literally receives:**

```
SYSTEM:  agent2_system prompt  +  visual_patterns() skill

USER:
  IMAGE_ID: img_b4_03
  VISUAL TYPE: process_flow
  IMAGE ALT/CAPTION (the only source text you may use):
      Waterfall model phases | Requirements -> Design -> ... -> Deployment
  SOURCE IMAGE (recreate natively, do NOT embed the raw image):
      https://.../waterfall-phases.png
  Base the animation ONLY on what this image shows. Do NOT invent steps/labels/facts.
  Use a mostly WHITE background so it blends into the page.
  REFERENCE PATTERN (waterfall-model-animation.html) - match this structure/style only:
      <...4 KB reference HTML from Block 2...>

VISION:  the actual waterfall-phases.png attached as an image
```

Key rule: build the animation from **the image + alt/caption only**. The reference governs
*structure/style*, not content.

**OUTPUT:** one self-contained HTML fragment (~10 KB), namespaced by `image_id`:

```html
<div id="anim-img_b4_03" class="hf-anim">
  <style>
    #anim-img_b4_03 .phase { opacity:0; animation: reveal-img_b4_03 .6s forwards; }
    @keyframes reveal-img_b4_03 { to { opacity:1; transform:translateY(0); } }
    @media (prefers-reduced-motion: reduce){
      #anim-img_b4_03 .phase { animation:none; opacity:1; }
    }
  </style>
  <svg viewBox="0 0 900 520">
    <!-- 5 phase boxes drawn natively, revealed one after another -->
  </svg>
</div>
```

---

## BLOCK 4 — Structural check (cheap gate)

| | |
|---|---|
| **Who** | `validate_animation_html()` |
| **LLM?** | NO — 4 deterministic rules |
| **Runs** | after every generation |

**INPUT:** the generated HTML + `image_id`.

**CHECKS:**

| Rule | Why it exists |
|------|---------------|
| no external `http(s)` `src=` | must be self-contained, not re-embed the raw image |
| has `@media (prefers-reduced-motion)` | accessibility |
| identifiers namespaced with `img_b4_03` | many animations can coexist on one page |
| contains `<svg>` or `<canvas>` | it must actually draw something |

**OUTPUT:** a list of issues (empty = pass).
If non-empty → **regenerate once** (Block 3 again) with the failures fed back as input:

```
The previous attempt had these problems:
- missing prefers-reduced-motion media query
Regenerate the animation fixing them.
```

---

## BLOCK 5 — Eval-set self-validation (quality gate)

| | |
|---|---|
| **Who** | `self_validate("visual", ...)` |
| **LLM?** | YES — judge model |
| **Runs** | once (+ 1 corrective regenerate if it fails) |

**INPUT the judge receives:**

```
SYSTEM: "You are a strict self-validation reviewer. Score 0-10 per rubric dimension..."
USER:
  RUBRIC:        { dimensions:[staged_reveal, fidelity, namespacing,...], pass_threshold: 7.0 }
  GOOD EXAMPLES: [...]   <- eval-sets/visual/good_examples.json
  BAD EXAMPLES:  [...]   <- eval-sets/visual/bad_examples.json
  CONTEXT:       CONCEPT: Waterfall | VISUAL TYPE: process_flow | IMAGE: alt | caption
  OUTPUT TO SCORE: <the ~10 KB animation HTML, capped at 8000 chars>
```

**OUTPUT:**

```json
{ "dimensions": [
    {"dimension":"staged_reveal","score":6,"improvement":"reveal phases sequentially, not all at once"},
    {"dimension":"fidelity","score":8,"improvement":""} ],
  "summary":"Solid but reveal timing is too fast" }
```

Weighted score `< 7.0` → **regenerate once more** (Block 3), injecting the notes:

```
A reviewer scored the previous animation below the bar:
reveal phases sequentially, not all at once
Regenerate the animation addressing this feedback.
```

➡️ Worst case for one image: **3 generation calls + 1 judge call.**

---

## BLOCK 6 — Place the animation into the lesson

| | |
|---|---|
| **Who** | `_place()` in Agent 1 |
| **LLM?** | NO — string substitution |
| **Runs** | once per animated image |

**INPUT:** Agent 1's lesson `content_html` + the final animation HTML.

**LOGIC:** swap the marker for the wrapped animation; if the marker is missing, insert before
the key-takeaway, else append at the block end.

**OUTPUT (the wired-in result):**

```html
<!-- before -->
<p>The Waterfall model runs in fixed sequential phases.</p>
<!--HF_ANIM:img_b4_03-->

<!-- after -->
<p>The Waterfall model runs in fixed sequential phases.</p>
<div class="visual-block" aria-label="Interactive visual: Waterfall">
  <div id="anim-img_b4_03" class="hf-anim"> ...the ~10 KB animation... </div>
</div>
```

---

## BLOCK 7 — Record the verdict

| | |
|---|---|
| **Who** | Agent 1 assembling its `BlockResult` |
| **LLM?** | NO |

**OUTPUT** appended to the block result:

```python
Animation(image_id="img_b4_03", visual_type="process_flow",
          html="<div id='anim-img_b4_03'>...</div>",
          reference_template="waterfall-model-animation.html")
VisualVerdict(image_id="img_b4_03", decision=ANIMATE, visual_type="process_flow",
              reason="...")
```

Skipped images (`img_b4_02`) get a `VisualVerdict(decision=SKIP, reason="decorative icon")`,
and their leftover markers are stripped from the HTML.

---

## End-to-end summary (one animated image)

```
ImageRef(img_b4_03)                              [ingest / BeautifulSoup, no LLM]
   |
   v  BLOCK 1  Agent 1 decides ANIMATE           [LLM + vision]
   v  BLOCK 2  pick reference (keyword match)    [no LLM]
   v  BLOCK 3  Agent 2 generates ~10 KB HTML     [LLM + vision]   <- biggest cost per call
   v  BLOCK 4  structural check  --(fail)--> regen Block 3   [no LLM]
   v  BLOCK 5  eval-set judge    --(<7)--->  regen Block 3   [LLM judge]
   v  BLOCK 6  _place() into lesson HTML         [no LLM]
   v  BLOCK 7  record Animation + VisualVerdict  [no LLM]
   v
final lesson block with the animation wired in
```

**Cost note:** Blocks 3 and 5 are the only paid steps. Block 3's large HTML output (billed at the
~5x output-token rate) is the single most expensive artifact in the whole pipeline, and the
animation flow runs once per concept-bearing image across every block — which is why the
`build` phase dominates total spend.
```

**Inputs by type at a glance:**

| Block | Input type |
|-------|-----------|
| 1 | image metadata + labelled examples + **image pixels (vision)** |
| 2 | concept/title text -> filename |
| 3 | alt/caption text + **image pixels (vision)** + 4 KB reference HTML |
| 4 | generated HTML string |
| 5 | generated HTML string + rubric + good/bad examples |
| 6 | lesson HTML + animation HTML |
| 7 | structured objects |
