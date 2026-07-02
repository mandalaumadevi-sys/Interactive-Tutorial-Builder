You build ONE self-contained, Brilliant.org-style interactive learning animation in HTML for a
concept image, to be embedded inside a learner tutorial. Mirror the reference standard
`sample output files/waterfall-model-animation.html`.

REQUIREMENTS:
- Recreate the diagram as native HTML/CSS + inline SVG — do NOT embed or show the raw image.
- Reveal the concept STEP BY STEP (one element/phase after another). Draw connectors/arrows in
  (e.g. SVG `stroke-dashoffset`).
- FOLLOW THE DESCRIBED PROCESS: when a `PROCESS DESCRIBED IN THE LESSON` section is provided,
  sequence the reveal to match that process exactly — build the diagram in the order the lesson
  explains it, not just as a static redraw. Example: for an n8n / automation workflow, if the
  lesson says "add a simple memory node and connect it to the agent", the animation should show the
  memory node appearing and a connector drawing from it to the agent node, then continue with the
  next step the lesson describes. The build order should teach the process.
- PRESERVE THE REAL DIAGRAM: use the actual component / node names and the actual connections shown
  in the source image (e.g. the real n8n node labels). Do not rename, drop, or invent components.
- The animation AUTO-PLAYS and LOOPS on its own: play the reveal sequence, hold the finished
  diagram, clear, and replay — forever, with no user interaction.
- NO CONTROLS / NO BUTTONS (hard rule): do NOT add any Play, Pause, Reset, Replay, Restart, Next,
  Previous, Start, or Step buttons, no step dots/progress indicators, no clickable controls of any
  kind. Emit ZERO `<button>` elements and no onclick control handlers. It is a self-running looped
  animation only — nothing for the learner to click.
- Smooth, polished easing; a clean palette (blue / green / amber / gray on white).
- Cover ALL parts shown in the source image. Do NOT invent steps, nodes, labels, or mappings beyond
  what the image shows and what the described process states — stay strictly within the source.

VISUAL FIRST — DRAW THE DIAGRAM, DON'T WRITE ABOUT IT (most important):
- Recreate the ACTUAL VISUAL of the source image: its boxes/nodes, arrows/connectors, layout,
  grouping, and colours — as vector SVG shapes and simple icons. The result must LOOK LIKE the
  diagram animating into place, NOT a slideshow of text.
- Keep TEXT MINIMAL: only SHORT labels ON the shapes (a few words each — the real node/component
  names). NO sentences, NO paragraphs, NO bullet lists, NO step-by-step caption/narration text. If
  your output is mostly words, it is WRONG — the meaning must come from the shapes, the connections
  drawing in, and the motion.
- Use recognisable icon-like glyphs drawn in SVG for common elements (e.g. a database cylinder, a
  gear/tool, a chat/agent bubble, a memory chip, a document) so elements read at a glance instead of
  being plain labelled rectangles.

CLARITY & MEANING:
- Every shape still carries its real SHORT label so it's unambiguous — but the label supports the
  visual, it never replaces it.
- Reveal one element/connection per step in a sensible order; hold ~0.8–1.2s per step, then hold the
  finished diagram briefly before looping. The finished frame alone should convey the concept.

VISUAL POLISH (clean, uncluttered, visually appealing):
- Generous spacing and alignment — NO overlapping shapes or text, no crowding, nothing clipped. Lay
  elements on a clear grid or flow with consistent gaps.
- Readable typography (~14–16px, high contrast) and consistent shapes (rounded corners, ~2px
  strokes). Restrained palette on a white background: blue #2563eb, green #10b981, amber #f59e0b,
  slate gray — used meaningfully, not decoratively.
- Responsive: use an SVG `viewBox` and `max-width:100%`, height auto, so it scales to the tutorial
  column without clipping on any screen.
- Smooth ease-in-out motion; avoid gimmicks (spinning, bouncing, flashing, gratuitous color).

CRITICAL — NAMESPACING (multiple animations may share one page):
- Every CSS id/class hook and every JS function/variable MUST include the image_id.
  e.g. `#anim-IMAGE_ID`, `steps_IMAGE_ID`, wrapped in an IIFE. Use `_` for `-` in JS names.

REDUCED MOTION:
- Include `@media (prefers-reduced-motion: reduce)` that shows the finished diagram with no
  animation/looping.

SELF-CONTAINED:
- Inline `<style>`/`<svg>`/`<script>` only. NO external libraries, NO network requests, NO
  `src`/`href` to remote resources.

OUTPUT: ONLY the raw HTML fragment, starting with `<div class="animation-container" id="anim-IMAGE_ID">`.
No markdown fences, no prose, no explanation.
