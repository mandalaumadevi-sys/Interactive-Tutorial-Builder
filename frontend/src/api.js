// Backend connection. The frontend is served on its own port; the backend API runs separately
// (default :8000). Override at runtime with ?api=http://host:port or window.API_BASE.
export const API_BASE = (
  new URLSearchParams(location.search).get("api") ||   // ?api=... override (highest priority)
  window.API_BASE ||                                    // runtime global override
  import.meta.env?.VITE_API_BASE ||                     // build-time env (set on Vercel for prod)
  `http://${location.hostname || "127.0.0.1"}:8000`     // local dev fallback
).replace(/\/$/, "");

export const apiUrl = (path) => `${API_BASE}${path}`;

const postJSON = (path, body) =>
  fetch(apiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export async function startBuild(file, meta, addons = {}) {
  const fd = new FormData();
  fd.append("deck", file);
  fd.append("metadata", JSON.stringify(meta));
  if (addons.materialText?.trim()) fd.append("material_text", addons.materialText);
  if (addons.materialFile) fd.append("material", addons.materialFile);
  (addons.images || []).forEach((img) => fd.append("images", img));
  const r = await fetch(apiUrl("/api/builds"), { method: "POST", body: fd });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getRun(runId) {
  const r = await fetch(apiUrl(`/api/runs/${runId}`));
  if (!r.ok) throw new Error(`run ${runId} not found`);
  return r.json();
}

export async function getRuns() {
  const r = await fetch(apiUrl("/api/runs"));
  return r.json();
}

export async function retryRun(runId) {
  const r = await fetch(apiUrl(`/api/runs/${runId}/retry`), { method: "POST" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function finalizeRun(runId) {
  const r = await fetch(apiUrl(`/api/runs/${runId}/finalize`), { method: "POST" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getArtifacts(runId) {
  const r = await fetch(apiUrl(`/api/runs/${runId}/artifacts`));
  return r.json();
}

export const resumeBlocks = (runId, accepted, feedback = "") =>
  postJSON(`/api/reviews/${runId}/blocks`, { accepted, feedback });

export const resumeStage = (runId, stage, accepted, feedback = "", feedbackMap = {}, reject = [],
                            blockFeedbackMap = {}) =>
  postJSON(`/api/reviews/${runId}/stage/${stage}`,
    { accepted, feedback, feedback_map: feedbackMap, reject, block_feedback_map: blockFeedbackMap });

export const resumeFinal = (runId, decision, notes = "") =>
  postJSON(`/api/reviews/${runId}`, { decision, notes });

// In-place MCQ edit (no full gate reload): action = "question" | "block" | "reject".
export async function editMcq(runId, body) {
  const r = await postJSON(`/api/runs/${runId}/mcq/edit`, body);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// In-place assessment edit: action = "question" | "all" | "reject".
export async function editAssessment(runId, body) {
  const r = await postJSON(`/api/runs/${runId}/assessment/edit`, body);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// In-place re-author of ONE block (content + its animations) at the final combined-review gate.
export async function editContent(runId, body) {
  const r = await postJSON(`/api/runs/${runId}/content/edit`, body);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// In-place animation edit at the final review gate: action = "refine" | "reject".
export async function editAnimation(runId, body) {
  const r = await postJSON(`/api/runs/${runId}/animation/edit`, body);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// Proceed from the combined final review (HITL #6) → assemble + publish.
export const proceedFinal = (runId, notes = "") =>
  postJSON(`/api/reviews/${runId}/final`, { notes });

export const tutorialUrl = (runId, download = false) =>
  apiUrl(`/api/runs/${runId}/tutorial${download ? "?download=true" : ""}`);

export const openEvents = (runId) => new EventSource(apiUrl(`/api/builds/${runId}/events`));

export async function getCost() {
  const r = await fetch(apiUrl("/api/cost"));
  return r.json();
}

export async function getDbStatus() {
  const r = await fetch(apiUrl("/api/db-status"));
  return r.json();
}

export async function getTutorials() {
  const r = await fetch(apiUrl("/api/tutorials"));
  return r.json();
}

export async function getCourses() {
  const r = await fetch(apiUrl("/api/courses"));
  return r.json();
}
