# Normalized HTML Contract

**Purpose:** Both ingestion flows (A: HTML upload, B: PPTX upload) must converge on **one** canonical document shape so everything downstream (block divider → agents → assembler) has a single, predictable input.

This document defines that shape. Stage 0 (Ingestion) is the only stage allowed to produce it; every later stage may *read* it but must not depend on the original source format.

---

## 1. Top-level structure

The normalized document is a UTF-8 HTML fragment (the *body* content — no `<html>/<head>` shell) plus a sidecar `assets` manifest. It is emitted as a single object:

```json
{
  "session_meta": {
    "session_name": "Software Development Models",
    "source_type": "html | pptx",
    "source_filename": "getting-started.html",
    "learning_objectives": ["...", "..."],     // [] if not provided
    "language": "ENGLISH"
  },
  "normalized_html": "<section class=\"session\"> ... </section>",
  "assets": [ /* Asset objects, see §4 */ ]
}
```

`normalized_html` is the string consumed by the Block Divider. `assets` is the resolved image manifest used by Agent 1 / Agent 2.

---

## 2. Allowed / normalized elements

The normalizer maps any source into this **restricted, predictable** element vocabulary. Anything not listed is either mapped to the nearest equivalent or dropped (with a warning logged).

| Concept | Canonical markup |
|---|---|
| Session title | `<h1>` (exactly one, first) |
| Major topic | `<h2>` |
| Sub-topic | `<h3>` |
| Detail item | `<h4>` |
| Paragraph | `<p>` |
| Unordered list | `<ul><li>…</li></ul>` |
| Ordered list | `<ol><li>…</li></ol>` |
| Table | `<table><thead>…</thead><tbody>…</tbody></table>` |
| Code block | `<pre><code class="language-xxx">…</code></pre>` |
| Inline code | `<code>…</code>` |
| Image | `<img>` (see §3) |
| Callout / note | `<aside class="note">…</aside>` |
| Quick tip | `<aside class="tip">…</aside>` |
| Collapsible | `<details><summary>…</summary>…</details>` |
| Bold / emphasis | `<strong>`, `<em>` |
| Link | `<a href>` |

### Custom component mapping
Source custom components are normalized to the `<aside>` vocabulary so the assembler has one rule set:

| Source component | Normalized |
|---|---|
| `<MultiLineNote>` | `<aside class="note">` |
| `<MultiLineQuickTip>` | `<aside class="tip">` |
| `<details>/<summary>` | kept as-is |

### Dropped (chrome / non-content)
- Navigation, headers/footers, page chrome, script/style from the source.
- Purely decorative wrappers collapse to their content.

---

## 3. Image normalization (critical — feeds visual-decision + Agent 2)

Every `<img>` in `normalized_html` MUST carry a stable id and resolvable src, and have a matching entry in `assets`:

```html
<img
  id="img_b?_NN"            <!-- assigned at division time; placeholder "img_NN" pre-division -->
  src="assets/waterfall_model.png"
  alt="Waterfall model diagram with sequential phases and arrows"
  data-occurrences="1"      <!-- how many times this exact src appears in the session -->
  data-source-ref="slide-7" <!-- pptx slide index, or original html node path -->
/>
```

Rules:
- `src` always points to a **locally exported PNG** under `assets/` — never a remote URL or embedded base64. (Flow B exports embedded pictures; Flow A downloads/copies remote images locally.)
- `alt` is preserved from source; if missing, left empty `""` (visual-decision treats empty-alt repeated images as chrome).
- `data-occurrences` enables the "logo/bullet repeated 32×/96× → skip" rule without re-counting later.
- Images appear **in document order at the position they occur** so the divider can assign each image to the block it falls in.

---

## 4. Asset manifest

```json
{
  "image_id": "img_07",
  "src": "assets/waterfall_model.png",
  "alt": "Waterfall model diagram with sequential phases and arrows",
  "width": 1280,
  "height": 720,
  "occurrences": 1,
  "source_ref": "slide-7",
  "bytes": 84213,
  "format": "png"
}
```

The manifest is the authoritative list Agent 1 iterates over for visual decisions; `width/height/bytes` help heuristics (tiny repeated icons → skip).

---

## 5. Flow-specific normalization notes

### Flow A — HTML
1. Parse with a lenient parser (lxml/BeautifulSoup).
2. Strip scripts/styles/nav/chrome; unwrap decorative containers.
3. Map custom components (§2). Map heading levels; if no `<h1>`, synthesize one from filename/title.
4. Localize images: download remote `src`/decode base64 → `assets/`, fill manifest, count occurrences.

### Flow B — PPTX (`python-pptx`)
1. Iterate slides in order. Slide title placeholder → `<h2>` (or `<h1>` for slide 1 / detected title slide).
2. Body placeholders → `<p>` / `<ul>` (use outline level for nesting → `<h3>/<h4>` vs list items).
3. Tables → `<table>`. Code-looking monospace text → `<pre><code>`.
4. Export each embedded picture → `assets/`, emit `<img>` at the slide's position, record `source_ref: slide-N`.
5. **Fallback:** for slides dominated by SmartArt/grouped shapes that don't export as a single clean picture, rasterize the whole slide region to one PNG and emit it as a single concept image (logged).

---

## 6. Invariants (validated before leaving Stage 0)

- [ ] Exactly one `<h1>`.
- [ ] Heading levels are well-nested (no `<h3>` before any `<h2>`).
- [ ] Every `<img>` has a unique `id`, a local `src`, and a matching `assets` entry.
- [ ] No `<script>`, no inline event handlers, no remote `src`.
- [ ] Document order preserved (headings + images interleaved as in source).
- [ ] `session_meta.session_name` non-empty.

A normalized document that fails any invariant halts the run with a clear ingestion error (not a silent downstream failure).
