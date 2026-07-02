# Skill: Tutorial House Style (Content agent)

Use this component vocabulary so the generated HTML renders correctly in the tutorial shell.
Write **prose**, never copied bullet dumps. Keep each block focused on one topic.

## Allowed components (pre-styled — use these class names)
- Wrapper: `<div class="main-content"> … </div>`
- Section header: `<div class="section-label"><h2>…</h2><p>…</p></div>`
- Headings/body: `<h3>`, `<p>`, `<strong>`
- Cards: `<div class="card"><div class="card-header"><span class="card-title">…</span></div> … </div>`
- Bulleted points (sparingly):
  `<ul class="bullet-list"><li class="bullet-item"><span class="bullet-dot"></span><span class="bullet-text">…</span></li></ul>`
  (use `bullet-dot green` / `bullet-dot red` for pros/cons)
- Callout: `<div class="callout"> … <strong>…</strong></div>`
- Table: `<div class="table-wrap"><table><thead>…</thead><tbody>…</tbody></table></div>`
- "When to use": `<div class="when-card"><h4>Best suited when:</h4> … </div>`
- Pros/cons: `<div class="pros-cons-row"><div class="pros-card"><h4>Advantages</h4>…</div><div class="cons-card"><h4>Disadvantages</h4>…</div></div>`
- Definition pair: `<div class="vv-grid"><div class="vv-card"><span class="vv-label">…</span><div class="vv-question">…</div><div class="vv-how">…</div></div></div>`
- Tag chips: `<div class="tags-row"><span class="tag">…</span></div>`

## Rules
- Do NOT emit `<html>`, `<head>`, `<style>`, `<script>`, or inline `style=` attributes.
- Do NOT embed `<img>` — the visual step adds animations.
- Prefer 1–3 short paragraphs + at most one structured component per idea.
- Lead with the concept, then the example/analogy.
