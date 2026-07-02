import { useState } from "react";
import Metrics from "./Metrics.jsx";
import ConfirmModal from "./ConfirmModal.jsx";
import { editMcq } from "../api.js";

const clone = (o) => JSON.parse(JSON.stringify(o || {}));

export default function McqGate({ runId, artifacts, onAccept }) {
  const titleByBlock = {};
  (artifacts.built_blocks || []).forEach((b) => { titleByBlock[b.block_id] = b.title; });

  const [mcqs, setMcqs] = useState(() => clone(artifacts.mcqs));
  const [fb, setFb] = useState({});         // "block:idx" -> feedback text
  const [blockFb, setBlockFb] = useState({}); // block_id -> feedback text
  const [busy, setBusy] = useState({});     // key -> bool
  const [confirm, setConfirm] = useState(false);
  const keys = Object.keys(mcqs).sort((a, b) => +a - +b);
  const anyBusy = Object.values(busy).some(Boolean);
  // feedback typed into a box but never "Applied" would be lost on Accept — guard it
  const pending = Object.values(fb).some((t) => (t || "").trim())
    || Object.values(blockFb).some((t) => (t || "").trim());
  const tryAccept = () => (pending ? setConfirm(true) : onAccept());

  const run = async (key, body, after) => {
    setBusy((s) => ({ ...s, [key]: true }));
    try {
      const res = await editMcq(runId, body);
      setMcqs((m) => ({ ...m, [res.block_id]: res.mcqs }));
      after && after();
    } catch (e) {
      alert("Update failed: " + e);
    } finally {
      setBusy((s) => ({ ...s, [key]: false }));
    }
  };

  const applyQuestion = (bid, i) => {
    const key = `${bid}:${i}`, feedback = (fb[key] || "").trim();
    if (feedback) run(key, { block_id: bid, action: "question", index: i, feedback },
                      () => setFb((s) => ({ ...s, [key]: "" })));
  };
  const rejectQuestion = (bid, i) => run(`${bid}:${i}`, { block_id: bid, action: "reject", index: i });
  const applyBlock = (bid) => {
    const feedback = (blockFb[bid] || "").trim();
    if (feedback) run(`block:${bid}`, { block_id: bid, action: "block", feedback },
                      () => setBlockFb((s) => ({ ...s, [bid]: "" })));
  };

  return (
    <div className="card">
      <h2>🧠 Knowledge Checks — the per-block quizzes</h2>
      <div className="banner info">
        Per question: type feedback and click <strong>Apply</strong> (only that question regenerates),
        or <strong>Reject</strong> to drop it. Or give a block <strong>overall feedback</strong> to
        regenerate all of that block's questions. Then <strong>Accept all &amp; continue</strong>.
      </div>
      <Metrics metrics={(artifacts.eval_scores || {}).mcq} />

      {keys.length ? keys.map((bid) => {
        const bkey = `block:${bid}`;
        return (
          <div className="rev-block" key={bid} style={{ marginBottom: 16 }}>
            <div className="rev-h">Block {bid} · {titleByBlock[bid] || ""} — {(mcqs[bid] || []).length} question(s)</div>

            <div className="block-fb">
              <textarea className="rev-fb" value={blockFb[bid] || ""} disabled={busy[bkey]}
                placeholder="Overall feedback for THIS block's MCQs (regenerates all its questions)"
                onChange={(e) => setBlockFb((s) => ({ ...s, [bid]: e.target.value }))} />
              <button type="button" className="apply-btn" disabled={busy[bkey] || !(blockFb[bid] || "").trim()}
                onClick={() => applyBlock(bid)}>{busy[bkey] ? "Regenerating…" : "Apply to block"}</button>
            </div>

            {(mcqs[bid] || []).map((q, i) => {
              const key = `${bid}:${i}`, b = busy[key];
              const correct = q.correctIndexes || q.correct_indexes || [];
              return (
                <div className={`mcq ${b ? "busy" : ""}`} key={i}>
                  <div className="mcq-q">Q{i + 1}. {q.question}</div>
                  <ul className="mcq-opts">
                    {(q.options || []).map((o, j) => (
                      <li key={j} className={correct.includes(j) ? "opt-correct" : ""}>{o}{correct.includes(j) ? " ✓" : ""}</li>
                    ))}
                  </ul>
                  {q.explanation && <div className="muted mcq-exp">{q.explanation}</div>}
                  <textarea className="rev-fb" value={fb[key] || ""} disabled={b}
                    placeholder="Feedback for THIS question"
                    onChange={(e) => setFb((s) => ({ ...s, [key]: e.target.value }))} />
                  <div className="gate-row">
                    <button type="button" className="apply-btn" disabled={b || !(fb[key] || "").trim()}
                      onClick={() => applyQuestion(bid, i)}>{b ? "Regenerating…" : "Apply"}</button>
                    <button type="button" className="rej-btn" disabled={b}
                      onClick={() => rejectQuestion(bid, i)}>Reject</button>
                  </div>
                </div>
              );
            })}
          </div>
        );
      }) : <div className="muted">No MCQs.</div>}

      <div className="actions">
        <button className="green" disabled={anyBusy} onClick={tryAccept}>Accept all &amp; continue →</button>
      </div>

      <ConfirmModal open={confirm}
        title="Apply your feedback first?"
        message="You've typed feedback on a question but haven't clicked Apply, so it wasn't used. Accepting now keeps the MCQs as-is and discards that note."
        confirmLabel="Discard & accept" cancelLabel="Go back & apply"
        onCancel={() => setConfirm(false)}
        onConfirm={() => { setConfirm(false); onAccept(); }} />
    </div>
  );
}
