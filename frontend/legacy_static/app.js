// ── Backend connection ────────────────────────────────────────────────────
const API_BASE = (
  new URLSearchParams(location.search).get("api") ||
  window.API_BASE ||
  `http://${location.hostname || "127.0.0.1"}:8000`
).replace(/\/$/, "");
const api = path => `${API_BASE}${path}`;

const $ = id => document.getElementById(id);
let RUN_ID = null, ES = null;

const esc = s => String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
const NODE_LABELS = {
  ingest:"Reading the session & describing images", divide:"Dividing into content blocks",
  content:"Agent 1 — writing block content", animation:"Agent 2 — building animations",
  mcq:"Agent 3 — writing quizzes", assessment:"Building the final assessment",
  draft:"Assembling a draft", quality:"Checking quality", refine:"Refining low-scoring parts",
  assemble:"Finalizing the tutorial", memory:"Updating course memory",
};
function setStatus(s){ const p=$("status-pill"); p.className="pill "+s; p.textContent=s.replace("_"," "); p.classList.remove("hidden"); }
function setProgress(msg){ $("progress-msg").textContent = msg; }
function show(id){ $(id).classList.remove("hidden"); } function hide(id){ $(id).classList.add("hidden"); }
const GATE_CARDS = ["block-card","content-card","animation-card","mcq-card","final-card"];
function hideGates(){ GATE_CARDS.forEach(hide); }

// ── Tabs ──────────────────────────────────────────────────────────────────
document.querySelectorAll(".tab").forEach(t => t.onclick = () => {
  document.querySelectorAll(".tab").forEach(x => x.classList.toggle("active", x===t));
  $("tab-builder").classList.toggle("hidden", t.dataset.tab!=="builder");
  $("tab-pipeline").classList.toggle("hidden", t.dataset.tab!=="pipeline");
});

// ── Pipeline diagram (read-only live map) ───────────────────────────────────
const PIPELINE = [
  {id:"ingest",          label:"Ingest + image descriptions",        kind:"auto"},
  {id:"divide",          label:"Divide into content blocks",         kind:"auto"},
  {id:"block",           label:"Review block division",              kind:"human"},
  {id:"content",         label:"Agent 1 · Author block content",     kind:"auto"},
  {id:"reviewContent",   label:"Review content",                     kind:"human"},
  {id:"animation",       label:"Agent 2 · Generate animations",      kind:"auto"},
  {id:"reviewAnimation", label:"Review animations",                  kind:"human"},
  {id:"mcq",             label:"Agent 3 · Generate MCQs",            kind:"auto"},
  {id:"reviewMcq",       label:"Review MCQs (accept per block)",     kind:"human"},
  {id:"assessment",      label:"Agent 4 · Final assessment",         kind:"auto"},
  {id:"quality",         label:"Quality check + self-refine (once)", kind:"auto"},
  {id:"final",           label:"Final review + accept assessment",   kind:"human"},
  {id:"assemble",        label:"Publish tutorial",                   kind:"auto"},
];
const NODE_TO_STEP = {
  ingest:"ingest", divide:"divide", human_block_review:"block",
  content:"content", human_content_review:"reviewContent",
  animation:"animation", human_animation_review:"reviewAnimation",
  mcq:"mcq", human_mcq_review:"reviewMcq",
  assessment:"assessment", draft:"assessment",
  quality:"quality", refine:"quality",
  prepare_quality_review:"final", human_quality_gate:"final",
  assemble:"assemble", memory:"assemble",
};
const STAGE_TO_STEP = {block:"block", content:"reviewContent", animation:"reviewAnimation",
                       mcq:"reviewMcq", quality:"final"};
const STEP_IDX = Object.fromEntries(PIPELINE.map((s,i)=>[s.id,i]));
let pipeReached = -1, pipeWaiting = null, pipeDone = false;

function resetPipeline(){ pipeReached=-1; pipeWaiting=null; pipeDone=false; renderPipeline(); }
function pipeOnNode(node){ const id=NODE_TO_STEP[node]; if(id==null) return;
  pipeReached=Math.max(pipeReached, STEP_IDX[id]); pipeWaiting=null; renderPipeline(); }
function pipeOnGate(stage){ const id=STAGE_TO_STEP[stage]; if(id==null) return;
  pipeReached=Math.max(pipeReached, STEP_IDX[id]); pipeWaiting=id; renderPipeline(); }
function pipeOnDone(){ pipeDone=true; pipeWaiting=null; renderPipeline(); }

function pipeState(i,step){
  if(pipeDone) return "done";
  if(pipeWaiting===step.id) return "wait";
  if(i<pipeReached) return "done";
  if(i===pipeReached) return "active";
  return "pending";
}
function renderPipeline(){
  $("pipeline").innerHTML = PIPELINE.map((s,i)=>{
    const st = pipeState(i,s);
    const icon = s.kind==="human" ? "👤" : "⚙";
    return `<li class="pstep ${st} ${s.kind}">
      <span class="pdot"></span>
      <span class="picon">${icon}</span>
      <span class="plabel">${esc(s.label)}</span>
      <span class="pstate">${st==="wait"?"your turn":st==="active"?"running…":st==="done"?"done":""}</span>
    </li>`;
  }).join("");
}
renderPipeline();

// ── Block-division rendering ────────────────────────────────────────────────
function renderDivision(blocks){
  if(!blocks || !blocks.length) return '<div class="muted">No blocks.</div>';
  return blocks.map((b,i)=>`
    <div class="t-h1"><span class="t-step">${i+1}</span>
      <span>${esc(b.title)}<span class="wc">~${b.word_count_estimate||0} words</span></span></div>
    ${(b.h2_sections_included||[]).map(s=>`<div class="t-sub"><span class="t-bullet">•</span><span>${esc(s)}</span></div>`).join("")}
    ${(b.learning_objectives_hint&&b.learning_objectives_hint.length)
        ? `<div class="t-objs">Objectives: ${b.learning_objectives_hint.map(esc).join(" · ")}</div>` : ""}
  `).join("");
}

// ── Eval metrics (shown at every gate) ──────────────────────────────────────
function renderMetrics(m){
  if(!m) return "";
  const score = (m.score!=null) ? Number(m.score).toFixed(1) : "—";
  const cls = m.passed ? "pass" : "fail";
  const dims = (m.dimensions||[]).map(d =>
    `<div class="dim"><span>${esc(d.dimension)}</span>
      <span class="score ${d.passed?'pass':'fail'}">${Number(d.score).toFixed(1)} ${d.passed?'✓':'✗'}</span></div>`).join("");
  return `<div class="metric-head">Eval score
      <span class="score ${cls}">${score} / 10 ${m.passed?'✓':'⚠'}</span></div>
    ${m.summary?`<div class="muted" style="margin:4px 0 8px;">${esc(m.summary)}</div>`:""}${dims}`;
}

// ── Start a build ───────────────────────────────────────────────────────────
$("start-btn").onclick = async () => {
  const f = $("file").files[0];
  if(!f){ alert("Choose a session file first."); return; }
  const course = $("course").value.trim();
  const sessionName = $("session").value.trim();
  if(!course){ alert("Enter a course name."); return; }
  if(!sessionName){ alert("Enter a session name."); return; }
  $("start-btn").disabled = true;
  const meta = {
    course_name: course, session_name: sessionName,
    learning_objectives: $("objectives").value.split(",").map(s=>s.trim()).filter(Boolean),
  };
  const fd = new FormData(); fd.append("deck", f); fd.append("metadata", JSON.stringify(meta));
  let r;
  try { r = await fetch(api("/api/builds"), {method:"POST", body:fd}); }
  catch (err) {
    alert(`Cannot reach the backend at ${API_BASE}.\nIs it running? (start backend.sh)\n\n${err}`);
    $("start-btn").disabled=false; return;
  }
  if(!r.ok){ alert("Start failed: "+await r.text()); $("start-btn").disabled=false; return; }
  const j = await r.json(); RUN_ID = j.run_id;
  resetPipeline();
  show("progress-card"); setProgress("Reading the session…"); setStatus("running");
  hideGates(); hide("done-card");
  listen();
};

function listen(){
  if(ES) ES.close();
  ES = new EventSource(api(`/api/builds/${RUN_ID}/events`));
  ES.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    if(ev.type === "node"){
      pipeOnNode(ev.node);
      if(ev.status === "start" && NODE_LABELS[ev.node]) setProgress(NODE_LABELS[ev.node] + "…");
    } else if(ev.type === "run"){
      ES.close();
      if(ev.status === "needs_review") onReview(ev.stage);
      else if(ev.status === "completed") onDone();
      else if(ev.status === "failed") onFailed(ev.message || "The run failed.");
    }
  };
}

async function onReview(stage){
  setStatus("needs_review"); hide("progress-card"); pipeOnGate(stage);
  const r = await fetch(api(`/api/runs/${RUN_ID}/artifacts`)); const a = await r.json();
  if(stage === "block") renderBlockReview(a);
  else if(stage === "content") renderContentReview(a);
  else if(stage === "animation") renderAnimationReview(a);
  else if(stage === "mcq") renderMcqReview(a);
  else renderFinalReview(a);
}

function onFailed(msg){
  setStatus("failed"); show("progress-card");
  $("progress-card").innerHTML = `<div class="banner err"><strong>Build failed.</strong> ${esc(msg)}</div>`;
  $("start-btn").disabled = false;
}

// ── GATE 1 — block division ─────────────────────────────────────────────────
function renderBlockReview(a){
  hideGates(); show("block-card");
  const d = a.division || {};
  const reason = (d.division_reasoning || "").trim();
  $("reasoning").textContent = (reason && !reason.toLowerCase().startsWith("[mock]")) ? reason : "";
  $("reasoning").style.display = $("reasoning").textContent ? "block" : "none";
  $("tree").innerHTML = renderDivision(d.blocks);
}
$("accept-blocks").onclick = () => resumeBlocks(true, "");
$("feedback-blocks").onclick = () => {
  const fb = $("block-feedback").value.trim();
  if(!fb){ alert("Write feedback, or click Accept."); return; }
  resumeBlocks(false, fb);
};
async function resumeBlocks(accepted, feedback){
  hideGates(); show("progress-card"); setStatus("running");
  setProgress(accepted ? "Division accepted — writing block content…" : "Re-dividing with your feedback…");
  await fetch(api(`/api/reviews/${RUN_ID}/blocks`), {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({accepted, feedback})});
  listen();
}

// ── Generic per-agent gate resume (content | animation | mcq) ────────────────
async function resumeStage(stage, accepted, feedback, msg){
  hideGates(); show("progress-card"); setStatus("running"); setProgress(msg);
  await fetch(api(`/api/reviews/${RUN_ID}/stage/${stage}`), {method:"POST",
    headers:{"Content-Type":"application/json"}, body: JSON.stringify({accepted, feedback})});
  listen();
}

// Render a block's HTML fragment in an isolated iframe so its markup/animation shows faithfully.
function frame(html, h){
  const doc = `<!doctype html><meta charset="utf-8"><style>
    body{font:14px/1.5 Inter,system-ui,sans-serif;color:#1f2937;margin:12px;}
    h2,h3{font-size:1rem;margin:.4em 0;} img{max-width:100%;} svg{max-width:100%;height:auto;}
    .key-takeaway,.takeaway{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:8px 10px;margin-top:8px;}
  </style>${html||""}`;
  return `<iframe class="frag" style="height:${h||220}px" sandbox="allow-scripts" srcdoc="${esc(doc).replace(/"/g,'&quot;')}"></iframe>`;
}

// ── GATE 2 — content ────────────────────────────────────────────────────────
function renderContentReview(a){
  hideGates(); show("content-card");
  $("content-metrics").innerHTML = renderMetrics((a.eval_scores||{}).content);
  const blocks = a.built_blocks || [];
  $("content-blocks").innerHTML = blocks.map(b => {
    const flag = (b.quality_issues||[]).length
      ? `<div class="banner err" style="margin:6px 0;">⚠ ${esc((b.quality_issues||[]).join("; "))}</div>` : "";
    return `<div class="rev-block"><div class="rev-h">Block ${b.block_id} · ${esc(b.title||"")}</div>
      ${flag}${frame(b.content_html, 240)}</div>`;
  }).join("") || '<div class="muted">No content.</div>';
}
$("accept-content").onclick = () => resumeStage("content", true, "", "Content accepted — building animations…");
$("refine-content").onclick = () => {
  const fb = $("content-feedback").value.trim();
  if(!fb){ alert("Write feedback, or click Accept."); return; }
  resumeStage("content", false, fb, "Re-writing block content with your feedback…");
};

// ── GATE 3 — animations ──────────────────────────────────────────────────────
function renderAnimationReview(a){
  hideGates(); show("animation-card");
  $("animation-metrics").innerHTML = renderMetrics((a.eval_scores||{}).visual);
  const anims = [];
  (a.built_blocks||[]).forEach(b => (b.animations||[]).forEach(an =>
    anims.push({block:b.title||("Block "+b.block_id), ...an})));
  $("animation-list").innerHTML = anims.length
    ? anims.map(an => `<div class="rev-block"><div class="rev-h">${esc(an.block)} · ${esc(an.visual_type||"")}
        ${an.reference_template?`<span class="wc">ref: ${esc(an.reference_template)}</span>`:""}</div>
        ${frame(an.html, 260)}</div>`).join("")
    : '<div class="muted">No animations were needed for this session (no concept diagrams).</div>';
}
$("accept-animation").onclick = () => resumeStage("animation", true, "", "Animations accepted — writing quizzes…");
$("refine-animation").onclick = () => {
  const fb = $("animation-feedback").value.trim();
  if(!fb){ alert("Write feedback, or click Accept."); return; }
  resumeStage("animation", false, fb, "Regenerating animations with your feedback…");
};

// ── GATE 4 — MCQs ────────────────────────────────────────────────────────────
function renderMcqReview(a){
  hideGates(); show("mcq-card");
  $("mcq-metrics").innerHTML = renderMetrics((a.eval_scores||{}).mcq);
  const byTitle = {}; (a.built_blocks||[]).forEach(b => byTitle[b.block_id]=b.title);
  const mcqs = a.mcqs || {};
  const idxKeys = Object.keys(mcqs).sort((x,y)=>(+x)-(+y));
  $("mcq-list").innerHTML = idxKeys.map(k => {
    const qs = mcqs[k]||[];
    const head = `<div class="rev-h">Block ${k} · ${esc(byTitle[k]||"")} — ${qs.length} question(s)</div>`;
    const body = qs.map((q,i)=>{
      const opts = (q.options||[]).map((o,j)=>{
        const correct = (q.correctIndexes||q.correct_indexes||[]).includes(j);
        return `<li class="${correct?'opt-correct':''}">${esc(o)}${correct?' ✓':''}</li>`;
      }).join("");
      return `<div class="mcq"><div class="mcq-q">Q${i+1}. ${esc(q.question)}</div>
        <ul class="mcq-opts">${opts}</ul>
        ${q.explanation?`<div class="muted mcq-exp">${esc(q.explanation)}</div>`:""}</div>`;
    }).join("");
    return `<div class="rev-block">${head}${body}</div>`;
  }).join("") || '<div class="muted">No MCQs.</div>';
}
$("accept-mcq").onclick = () => resumeStage("mcq", true, "", "MCQs accepted — building the final assessment…");
$("refine-mcq").onclick = () => {
  const fb = $("mcq-feedback").value.trim();
  if(!fb){ alert("Write feedback, or click Accept."); return; }
  resumeStage("mcq", false, fb, "Regenerating MCQs with your feedback…");
};

// ── GATE 5 — final review + assessment ───────────────────────────────────────
function renderFinalReview(a){
  hideGates(); show("final-card");
  const flagged = (a.built_blocks || []).filter(b => (b.quality_issues || []).length);
  const flagHtml = flagged.length
    ? `<div class="banner err"><strong>⚠ ${flagged.length} block(s) need attention:</strong><ul style="margin:6px 0 0 18px;">`
      + flagged.map(b => `<li>${esc(b.title || ('block '+b.block_id))} — ${esc((b.quality_issues||[]).join('; '))}</li>`).join("")
      + `</ul></div>` : "";
  const q = a.quality_report || {dimensions:[]};
  $("quality").innerHTML = flagHtml +
    `<div class="muted" style="margin-bottom:8px;">${esc(q.summary||"")}</div>` +
    (q.dimensions||[]).map(d => `<div class="dim"><span>${esc(d.dimension)}</span>
      <span class="score ${d.passed?'pass':'fail'}">${d.score.toFixed(1)} ${d.passed?'✓':'✗'}</span></div>`).join("");
  const asmt = a.final_assessment || [];
  $("final-assessment").innerHTML = asmt.length
    ? `<div class="metric-head" style="margin-top:14px;">Assessment questions (${asmt.length})</div>`
      + asmt.map((q,i)=>`<div class="mcq"><div class="mcq-q">Q${i+1}. ${esc(q.question)}
          <span class="wc">${esc(q.question_type||"")}${q.blooms_level?" · "+esc(q.blooms_level):""}</span></div>
          <div class="muted mcq-exp">Model answer: ${esc(q.answer||"")}</div></div>`).join("")
    : "";
  $("preview-link").href = api(`/api/runs/${RUN_ID}/tutorial`);
}
$("approve-final").onclick = () => resumeFinal("approve");
$("reject-final").onclick = () => resumeFinal("reject");
async function resumeFinal(decision){
  hideGates(); show("progress-card"); setStatus("running");
  setProgress(decision==="approve" ? "Publishing the tutorial…" : "Sending back to re-divide…");
  await fetch(api(`/api/reviews/${RUN_ID}`), {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({decision, notes: $("final-notes").value})});
  listen();
}

function onDone(){
  setStatus("completed"); pipeOnDone(); hide("progress-card"); hideGates(); show("done-card");
  $("start-btn").disabled = false;
  $("done-path").textContent = "Saved to your tutorials library: generated_tutorials/<course>/<session>.html (rebuilds are versioned).";
  $("open-tutorial").onclick = () => window.open(api(`/api/runs/${RUN_ID}/tutorial`), "_blank");
  $("download-tutorial").onclick = () => window.open(api(`/api/runs/${RUN_ID}/tutorial?download=true`), "_blank");
}

// ── Cost panel ───────────────────────────────────────────────────────────────
const fmtINR = n => "₹" + Number(n).toLocaleString("en-IN", {maximumFractionDigits: 0});
const fmtUSD = n => "$" + Number(n).toFixed(2);
$("cost-toggle").onclick = async () => {
  const panel = $("cost-panel");
  if(!panel.classList.contains("hidden")){ panel.classList.add("hidden"); return; }
  panel.classList.remove("hidden");
  $("cost-body").innerHTML = '<span class="muted">Loading…</span>'; $("cost-note").textContent = "";
  let d;
  try { const r = await fetch(api("/api/cost")); d = await r.json(); }
  catch (err) { $("cost-body").innerHTML = `<span class="muted">Couldn't reach the backend at ${API_BASE}.</span>`; return; }
  if(!d.key_reachable){ $("cost-body").innerHTML = '<span class="muted">Couldn\'t read cost from OpenRouter.</span>'; return; }
  const row = (label, inr, usd, cls = "") =>
    `<div class="cost-row ${cls}"><span>${label}</span>` +
    `<span><span class="cost-amt">${inr == null ? "—" : fmtINR(inr)}</span>` +
    `<span class="cost-usd">${usd == null ? "" : "(" + fmtUSD(usd) + ")"}</span></span></div>`;
  const lowBalance = d.remaining_credit_usd != null &&
    (d.key_limit_usd ? d.remaining_credit_usd <= 0.10 * d.key_limit_usd : d.remaining_credit_usd < 1);
  $("cost-body").innerHTML =
    row("This app has spent", d.app_spend_inr, d.app_spend_usd) +
    row("All apps on this key", d.key_usage_inr, d.key_usage_usd) +
    `<div class="cost-sep"></div>` +
    row("Balance left", d.remaining_credit_inr, d.remaining_credit_usd, "cost-balance" + (lowBalance ? " cost-low" : "")) +
    (d.key_limit_usd != null
      ? `<div class="cost-row muted"><span>Key credit limit</span><span class="cost-usd">${fmtUSD(d.key_limit_usd)}</span></div>` : "");
  $("cost-note").textContent =
    `${d.calls} LLM call${d.calls===1?"":"s"} by this app · rate ₹${d.usd_to_inr}/$ (${d.usd_to_inr_source})` +
    (lowBalance ? " · ⚠ balance running low" : "");
};
document.addEventListener("click", (e) => {
  const panel = $("cost-panel"), toggle = $("cost-toggle");
  if(panel.classList.contains("hidden")) return;
  if(panel.contains(e.target) || e.target === toggle) return;
  panel.classList.add("hidden");
});
