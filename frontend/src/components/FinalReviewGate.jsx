import { useState } from "react";
import { editContent, editAnimation, editMcq, editAssessment, getArtifacts, tutorialUrl } from "../api.js";
import ConfirmModal from "./ConfirmModal.jsx";

// HITL #6 — the whole assembled tutorial is previewed; per-element improvements are applied in
// place (each re-renders the draft server-side), then "Publish" proceeds to assemble + memory.
export default function FinalReviewGate({ runId, artifacts, onPublish }) {
  const [art, setArt] = useState(artifacts);
  const [previewKey, setPreviewKey] = useState(0);   // bump → reload the iframe after an edit
  const [busy, setBusy] = useState({});              // key -> bool
  const [cfb, setCfb] = useState({});                // content: block_id -> feedback
  const [afb, setAfb] = useState({});                // animation: block_id -> feedback
  const [mfb, setMfb] = useState({});                // mcq: "block:idx" -> feedback
  const [aqfb, setAqfb] = useState({});              // assessment: idx -> feedback
  const [notes, setNotes] = useState("");
  const [publishing, setPublishing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  // per-element feedback typed but not "Applied" would be lost on Publish (notes ARE saved, so
  // they don't count as pending).
  const pendingMaps = [cfb, afb, mfb, aqfb];

  const blocks = art.built_blocks || [];
  const mcqs = art.mcqs || {};
  const assessment = art.final_assessment || [];
  const anyBusy = Object.values(busy).some(Boolean);

  // run an in-place edit, then refresh artifacts + reload the preview
  const run = async (key, fn, after) => {
    setBusy((s) => ({ ...s, [key]: true }));
    try {
      await fn();
      setArt(await getArtifacts(runId));
      setPreviewKey((k) => k + 1);
      after && after();
    } catch (e) {
      alert("Update failed: " + e);
    } finally {
      setBusy((s) => ({ ...s, [key]: false }));
    }
  };

  const improveContent = (bid) => {
    const f = (cfb[bid] || "").trim();
    if (f) run(`c${bid}`, () => editContent(runId, { block_id: String(bid), feedback: f }),
              () => setCfb((s) => ({ ...s, [bid]: "" })));
  };
  const refineAnim = (bid) => {
    const f = (afb[bid] || "").trim();
    if (f) run(`a${bid}`, () => editAnimation(runId, { block_id: String(bid), action: "refine", feedback: f }),
              () => setAfb((s) => ({ ...s, [bid]: "" })));
  };
  const rejectAnim = (bid) => run(`a${bid}`, () => editAnimation(runId, { block_id: String(bid), action: "reject" }));
  const applyMcq = (bid, i) => {
    const key = `${bid}:${i}`, f = (mfb[key] || "").trim();
    if (f) run(`m${key}`, () => editMcq(runId, { block_id: String(bid), action: "question", index: i, feedback: f }),
              () => setMfb((s) => ({ ...s, [key]: "" })));
  };
  const rejectMcq = (bid, i) => run(`m${bid}:${i}`, () => editMcq(runId, { block_id: String(bid), action: "reject", index: i }));
  const applyAssess = (i) => {
    const f = (aqfb[i] || "").trim();
    if (f) run(`q${i}`, () => editAssessment(runId, { action: "question", index: i, feedback: f }),
              () => setAqfb((s) => ({ ...s, [i]: "" })));
  };
  const rejectAssess = (i) => run(`q${i}`, () => editAssessment(runId, { action: "reject", index: i }));

  const publish = async () => {
    setPublishing(true);
    try { await onPublish(notes.trim()); } finally { setPublishing(false); }
  };
  const pending = pendingMaps.some((m) => Object.values(m).some((t) => (t || "").trim()));
  const tryPublish = () => (pending ? setConfirm(true) : publish());

  const animBlocks = blocks.filter((b) => (b.animations || []).length);
  const mcqKeys = Object.keys(mcqs).sort((a, b) => +a - +b);

  return (
    <div className="card">
      <h2>🚀 Launch Review — the complete tutorial</h2>
      <div className="banner info">
        This is the fully assembled tutorial. Skim it below. Need a change? Use the panels to refine
        any block, animation, MCQ, or assessment question — each updates the preview instantly. When
        it looks right, <strong>Publish</strong>. Anything you note here is saved to course memory,
        so the next session starts already corrected.
      </div>

      <iframe key={previewKey} title="Final tutorial preview" src={tutorialUrl(runId)}
        style={{ width: "100%", height: 560, border: "1px solid #e5e7eb", borderRadius: 10, background: "#fff" }} />
      <p style={{ margin: "8px 0 18px" }}>
        <a className="link" href={tutorialUrl(runId)} target="_blank" rel="noreferrer">↗ Open the full preview in a new tab</a>
      </p>

      <details className="rev-acc">
        <summary>Refine content blocks ({blocks.length})</summary>
        {blocks.map((b) => {
          const k = `c${b.block_id}`;
          return (
            <div className="rev-block" key={b.block_id}>
              <div className="rev-h">Block {b.block_id} · {b.title || ""}</div>
              <textarea className="rev-fb" value={cfb[b.block_id] || ""} disabled={busy[k]}
                placeholder="What should change about this block's content?"
                onChange={(e) => setCfb((s) => ({ ...s, [b.block_id]: e.target.value }))} />
              <div className="gate-row">
                <button className="apply-btn" disabled={busy[k] || !(cfb[b.block_id] || "").trim()}
                  onClick={() => improveContent(b.block_id)}>{busy[k] ? "Rewriting…" : "Improve"}</button>
              </div>
            </div>
          );
        })}
      </details>

      <details className="rev-acc">
        <summary>Refine animations ({animBlocks.length})</summary>
        {animBlocks.length ? animBlocks.map((b) => {
          const k = `a${b.block_id}`;
          return (
            <div className="rev-block" key={b.block_id}>
              <div className="rev-h">Block {b.block_id} · {b.title || ""}</div>
              <textarea className="rev-fb" value={afb[b.block_id] || ""} disabled={busy[k]}
                placeholder="How should this animation change?"
                onChange={(e) => setAfb((s) => ({ ...s, [b.block_id]: e.target.value }))} />
              <div className="gate-row">
                <button className="apply-btn" disabled={busy[k] || !(afb[b.block_id] || "").trim()}
                  onClick={() => refineAnim(b.block_id)}>{busy[k] ? "Regenerating…" : "Regenerate"}</button>
                <button className="rej-btn" disabled={busy[k]} onClick={() => rejectAnim(b.block_id)}>Reject</button>
              </div>
            </div>
          );
        }) : <div className="muted">No animations in this tutorial.</div>}
      </details>

      <details className="rev-acc">
        <summary>Refine MCQs</summary>
        {mcqKeys.length ? mcqKeys.map((bid) => (
          <div className="rev-block" key={bid}>
            <div className="rev-h">Block {bid} — {(mcqs[bid] || []).length} question(s)</div>
            {(mcqs[bid] || []).map((q, i) => {
              const key = `${bid}:${i}`, k = `m${key}`;
              const correct = q.correctIndexes || q.correct_indexes || [];
              return (
                <div className={`mcq ${busy[k] ? "busy" : ""}`} key={i}>
                  <div className="mcq-q">Q{i + 1}. {q.question}</div>
                  <ul className="mcq-opts">
                    {(q.options || []).map((o, j) => (
                      <li key={j} className={correct.includes(j) ? "opt-correct" : ""}>{o}{correct.includes(j) ? " ✓" : ""}</li>
                    ))}
                  </ul>
                  <textarea className="rev-fb" value={mfb[key] || ""} disabled={busy[k]}
                    placeholder="Feedback for THIS question"
                    onChange={(e) => setMfb((s) => ({ ...s, [key]: e.target.value }))} />
                  <div className="gate-row">
                    <button className="apply-btn" disabled={busy[k] || !(mfb[key] || "").trim()}
                      onClick={() => applyMcq(bid, i)}>{busy[k] ? "Regenerating…" : "Apply"}</button>
                    <button className="rej-btn" disabled={busy[k]} onClick={() => rejectMcq(bid, i)}>Reject</button>
                  </div>
                </div>
              );
            })}
          </div>
        )) : <div className="muted">No MCQs.</div>}
      </details>

      <details className="rev-acc">
        <summary>Refine assessment ({assessment.length})</summary>
        {assessment.length ? assessment.map((q, i) => {
          const k = `q${i}`;
          return (
            <div className={`mcq ${busy[k] ? "busy" : ""}`} key={i}>
              <div className="mcq-q">Q{i + 1}. {q.question}
                <span className="wc">{q.question_type || ""}{q.blooms_level ? ` · ${q.blooms_level}` : ""}</span>
              </div>
              <div className="muted mcq-exp">Model answer: {q.answer || ""}</div>
              <textarea className="rev-fb" value={aqfb[i] || ""} disabled={busy[k]}
                placeholder="Feedback for THIS question"
                onChange={(e) => setAqfb((s) => ({ ...s, [i]: e.target.value }))} />
              <div className="gate-row">
                <button className="apply-btn" disabled={busy[k] || !(aqfb[i] || "").trim()}
                  onClick={() => applyAssess(i)}>{busy[k] ? "Regenerating…" : "Apply"}</button>
                <button className="rej-btn" disabled={busy[k]} onClick={() => rejectAssess(i)}>Reject</button>
              </div>
            </div>
          );
        }) : <div className="muted">No assessment questions.</div>}
      </details>

      <div className="block-fb" style={{ marginTop: 16 }}>
        <textarea className="rev-fb" value={notes} disabled={publishing}
          placeholder="Optional overall note for this course (saved to memory, auto-applied next time)"
          onChange={(e) => setNotes(e.target.value)} />
      </div>

      <div className="actions">
        <button className="green" disabled={anyBusy || publishing} onClick={tryPublish}>
          {publishing ? "Publishing…" : "Publish tutorial →"}
        </button>
      </div>

      <ConfirmModal open={confirm}
        title="Apply your changes first?"
        message="You've typed an improvement on an element but haven't clicked its Improve/Apply button, so it wasn't used. Publishing now uses the tutorial as shown and discards that note."
        confirmLabel="Discard & publish" cancelLabel="Go back & apply"
        onCancel={() => setConfirm(false)}
        onConfirm={() => { setConfirm(false); publish(); }} />
    </div>
  );
}
