# Skill: Animation Pattern Library (Visual agent)

Reference patterns distilled from `waterfall-model-animation.html`. Pick the one matching the
visual type, then write self-contained inline HTML/CSS/SVG/JS.

## Patterns by visual type
- **flowchart / process** — lay nodes out as `<rect>`/`<div>`; reveal them in sequence
  (staggered `opacity`/`transform`); draw connecting arrows with SVG `stroke-dashoffset`
  (animate from full length → 0); arrowheads as small `<polygon>` markers that fade in as each
  segment finishes.
- **architecture** — stack layers bottom-up; each layer fades+rises (`transform: translateY`)
  with an incremental `transition-delay`.
- **lifecycle / state machine** — render states around a loop/line; highlight the active state
  step by step (toggle a `.current` class on a timer or a "Next" button).
- **comparison** — two columns/rows; reveal paired items one at a time with green/red accents.
- **concept** — central node with satellites; reveal satellites sequentially; optional
  click-to-expand detail.

## Hard rules (every animation)
- Self-contained: inline `<style>`/`<svg>`/`<script>` only. NO external libraries or network.
- Scope all CSS classes and element ids with a unique prefix (e.g. `vz-…`) to avoid colliding
  with the surrounding tutorial page.
- Loop the reveal OR provide a "Next step" control.
- Respect `prefers-reduced-motion: reduce` → show the finished diagram, no motion.
- Recreate ONLY what the source concept shows — no invented steps or mappings.
- Output the raw `<div>…</div>` fragment only (no markdown fences, no prose).
