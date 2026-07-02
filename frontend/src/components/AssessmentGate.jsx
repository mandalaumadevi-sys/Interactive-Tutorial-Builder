import { useState } from "react";
import { editAssessment, tutorialUrl } from "../api.js";
import ConfirmModal from "./ConfirmModal.jsx";

export default function AssessmentGate({ runId, artifacts, onAccept }) {
  const [items, setItems] = useState(() => (artifacts.final_assessment || []).slice());
  const [fb, setFb] = useState({});      // index -> feedback
  const [allFb, setAllFb] = useState(""); // overall feedback
  const [busy, setBusy] = useState({});
  const [confirm, setConfirm] = useState(false);
  const pending = allFb.trim() || Object.values(fb).some((t) => (t || "").trim());
  const tryAccept = () => (pending ? setConfirm(true) : onAccept());

  const run = async (key, body, after) => {
    setBusy((s) => ({ ...s, [key]: true }));
    try {
      const res = await editAssessment(runId, body);
      setItems(res.final_assessment || []);
      after && after();
    } catch (e) {
      alert("Update failed: " + e);
    } finally {
      setBusy((s) => ({ ...s, [key]: false }));
    }
  };
  const applyQ = (i) => { const f = (fb[i] || "").trim(); if (f) run(`q${i}`, { action: "question", index: i, feedback: f }, () => setFb((s) => ({ ...s, [i]: "" }))); };
  const rejectQ = (i) => run(`q${i}`, { action: "reject", index: i });
  const applyAll = () => { const f = allFb.trim(); if (f) run("all", { action: "all", feedback: f }, () => setAllFb("")); };
  const anyBusy = Object.values(busy).some(Boolean);

  return (
    <div className="card">
      <h2>🎯 Final Assessment — the wrap-up questions</h2>
      <div className="banner info">
        Review the end-of-session assessment. Per question: feedback + <strong>Apply</strong>
        (regenerates just that one) or <strong>Reject</strong> to drop it. Or give overall feedback
        to regenerate the whole set. Then <strong>Accept &amp; finalize</strong> — the tutorial is
        assembled directly (no extra self-refine).
      </div>

      <div className="block-fb">
        <textarea className="rev-fb" value={allFb} disabled={busy.all}
          placeholder="Overall feedback for the assessment (regenerates all questions)"
          onChange={(e) => setAllFb(e.target.value)} />
        <button className="apply-btn" disabled={busy.all || !allFb.trim()} onClick={applyAll}>
          {busy.all ? "Regenerating…" : "Apply to all"}
        </button>
      </div>

      {items.length ? items.map((q, i) => {
        const b = busy[`q${i}`];
        return (
          <div className={`mcq ${b ? "busy" : ""}`} key={i}>
            <div className="mcq-q">Q{i + 1}. {q.question}
              <span className="wc">{q.question_type || ""}{q.blooms_level ? ` · ${q.blooms_level}` : ""}</span>
            </div>
            <div className="muted mcq-exp">Model answer: {q.answer || ""}</div>
            <textarea className="rev-fb" value={fb[i] || ""} disabled={b}
              placeholder="Feedback for THIS question"
              onChange={(e) => setFb((s) => ({ ...s, [i]: e.target.value }))} />
            <div className="gate-row">
              <button className="apply-btn" disabled={b || !(fb[i] || "").trim()} onClick={() => applyQ(i)}>
                {b ? "Regenerating…" : "Apply"}
              </button>
              <button className="rej-btn" disabled={b} onClick={() => rejectQ(i)}>Reject</button>
            </div>
          </div>
        );
      }) : <div className="muted">No assessment questions.</div>}

      <p style={{ margin: "12px 0" }}>
        <a className="link" href={tutorialUrl(runId)} target="_blank" rel="noreferrer">↗ Open full draft (incl. assessment)</a>
      </p>
      <div className="actions">
        <button className="green" disabled={anyBusy} onClick={tryAccept}>Accept &amp; finalize →</button>
      </div>

      <ConfirmModal open={confirm}
        title="Apply your feedback first?"
        message="You've typed feedback on the assessment but haven't clicked Apply, so it wasn't used. Continuing keeps the questions as-is and discards that note."
        confirmLabel="Discard & continue" cancelLabel="Go back & apply"
        onCancel={() => setConfirm(false)}
        onConfirm={() => { setConfirm(false); onAccept(); }} />
    </div>
  );
}
