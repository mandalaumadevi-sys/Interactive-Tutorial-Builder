import { useState } from "react";
import { tutorialUrl } from "../api.js";

export default function FinalGate({ runId, artifacts, onApprove, onReject }) {
  const [notes, setNotes] = useState("");
  const flagged = (artifacts.built_blocks || []).filter((b) => (b.quality_issues || []).length);
  const q = artifacts.quality_report || { dimensions: [] };
  const assessment = artifacts.final_assessment || [];

  return (
    <div className="card">
      <h2>👤 Gate 5 · Final review &amp; assessment</h2>
      <div className="banner info">
        Review the quality metrics, the assembled draft, and the end-of-session assessment questions.
        Approve to publish, or send back to re-divide.
      </div>

      {flagged.length > 0 && (
        <div className="banner err">
          <strong>⚠ {flagged.length} block(s) need attention:</strong>
          <ul style={{ margin: "6px 0 0 18px" }}>
            {flagged.map((b) => (
              <li key={b.block_id}>{b.title || `block ${b.block_id}`} — {(b.quality_issues || []).join("; ")}</li>
            ))}
          </ul>
        </div>
      )}

      {q.summary && <div className="muted" style={{ marginBottom: 8 }}>{q.summary}</div>}
      {(q.dimensions || []).map((d, i) => (
        <div className="dim" key={i}>
          <span>{d.dimension}</span>
          <span className={`score ${d.passed ? "pass" : "fail"}`}>{d.score.toFixed(1)} {d.passed ? "✓" : "✗"}</span>
        </div>
      ))}

      {assessment.length > 0 && (
        <>
          <div className="metric-head" style={{ marginTop: 14 }}>Assessment questions ({assessment.length})</div>
          {assessment.map((a, i) => (
            <div className="mcq" key={i}>
              <div className="mcq-q">
                Q{i + 1}. {a.question}
                <span className="wc">{a.question_type || ""}{a.blooms_level ? ` · ${a.blooms_level}` : ""}</span>
              </div>
              <div className="muted mcq-exp">Model answer: {a.answer || ""}</div>
            </div>
          ))}
        </>
      )}

      <p style={{ margin: "10px 0" }}>
        <a className="link" href={tutorialUrl(runId)} target="_blank" rel="noreferrer">
          ↗ Open rendered draft in a new tab
        </a>
      </p>
      <label>Reviewer notes (saved to memory)</label>
      <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes / corrections…" />
      <div className="actions">
        <button className="green" onClick={() => onApprove(notes)}>Approve &amp; publish</button>
        <button className="red" onClick={() => onReject(notes)}>Reject → re-divide</button>
      </div>
    </div>
  );
}
