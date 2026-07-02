import { useState, Fragment } from "react";
import ConfirmModal from "./ConfirmModal.jsx";

function Division({ blocks }) {
  if (!blocks?.length) return <div className="muted">No blocks.</div>;
  return (
    <div className="div-flow-h">
      {blocks.map((b, i) => {
        const secs = b.h2_sections_included || [];
        return (
          <Fragment key={i}>
            <div className="div-card">
              <div className="div-card-head">
                <span className="div-num">{i + 1}</span>
                <span className="div-card-title">{b.title}</span>
              </div>
              <div className="div-card-wc">~{b.word_count_estimate || 0} words · {secs.length} section{secs.length === 1 ? "" : "s"}</div>
              <div className="div-card-topics">
                {secs.map((s, j) => (
                  <div className="div-card-topic" key={j}><span className="t-bullet">•</span><span>{s}</span></div>
                ))}
              </div>
              {b.learning_objectives_hint?.length > 0 && (
                <div className="div-card-objs">Objectives: {b.learning_objectives_hint.join(" · ")}</div>
              )}
            </div>
            {i < blocks.length - 1 && <div className="div-arrow" aria-hidden="true">→</div>}
          </Fragment>
        );
      })}
    </div>
  );
}

export default function BlockGate({ artifacts, onAccept, onRefine }) {
  const [feedback, setFeedback] = useState("");
  const [confirm, setConfirm] = useState(false);
  const d = artifacts.division || {};
  // guard: if feedback was typed, clicking Accept would discard it — confirm first
  const tryAccept = () => (feedback.trim() ? setConfirm(true) : onAccept());

  return (
    <div className="card">
      <h2>🧩 Lesson Blueprint — how the session is split</h2>
      <div className="banner info">
        Approve the division, or write feedback (e.g. “merge blocks 2 &amp; 3”, “split Agile”) to re-divide.
      </div>
      <div className="s-cap">Blocks &amp; topics — in order</div>
      <Division blocks={d.blocks} />
      <label>Feedback for re-division (leave empty to accept)</label>
      <textarea value={feedback} onChange={(e) => setFeedback(e.target.value)}
                placeholder="e.g. Merge blocks 2 and 3; split the Agile block into Scrum and Kanban" />
      <div className="actions">
        <button className="green" onClick={tryAccept}>Accept division</button>
        <button className="ghost" onClick={() => {
          if (!feedback.trim()) return alert("Write feedback, or click Accept.");
          onRefine(feedback.trim());
        }}>Send feedback &amp; re-divide</button>
      </div>

      <ConfirmModal open={confirm}
        title="Apply your feedback first?"
        message="You've written feedback but are about to Accept without using it. Accepting will keep the current division and discard your note."
        confirmLabel="Discard & accept" cancelLabel="Go back"
        onCancel={() => setConfirm(false)}
        onConfirm={() => { setConfirm(false); onAccept(); }} />
    </div>
  );
}
