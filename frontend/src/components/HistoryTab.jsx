import { useEffect, useState } from "react";
import { getRuns, tutorialUrl } from "../api.js";

const STAGE_LABEL = {
  block: "Block division", content: "Content", animation: "Animations",
  mcq: "MCQs", assessment: "Assessment", final: "Final review", quality: "Final review",
};

function where(r) {
  if (r.status === "completed") return "Completed";
  if (r.status === "failed") return "Failed";
  if (r.status === "needs_review") return `Paused — your review: ${STAGE_LABEL[r.review_stage] || r.review_stage}`;
  if (r.status === "running") return "Building…";
  return r.status;
}

// Tab — every run (incl. incomplete), with Continue-from-where-you-stopped.
export default function HistoryTab({ active, refreshKey, onContinue }) {
  const [runs, setRuns] = useState(null);
  const [err, setErr] = useState("");
  const load = () => { setErr(""); getRuns().then(setRuns).catch(() => setErr("Couldn't reach the backend.")); };
  useEffect(() => { if (active) load(); }, [active, refreshKey]);


  return (
    <div className="card">
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <h2 style={{ margin: 0 }}>All builds</h2>
        <button className="ghost" style={{ marginLeft: "auto", padding: "6px 12px" }} onClick={load}>↻ Refresh</button>
      </div>
      <p className="muted" style={{ margin: "8px 0 14px" }}>
        Every build, saved at whatever stage it reached. <strong>Continue</strong> an unfinished one
        exactly where you stopped, <strong>retry</strong> a failed one, or <strong>open</strong> a
        finished one. (Finished tutorials also appear in the <strong>Tutorials</strong> tab.)
      </p>

      {err && <div className="banner err">{err}</div>}
      {!err && runs == null && <div className="muted">Loading…</div>}
      {!err && runs && runs.length === 0 && <div className="muted">No builds yet.</div>}

      {runs && runs.map((r) => (
        <div className="tut-row" key={r.run_id}>
          <div className="tut-main">
            <div className="tut-title">{r.session_name || "(untitled session)"}</div>
            <div className="tut-sub">
              {r.course_name || "—"} · <span className={`hist-status s-${r.status}`}>{where(r)}</span>
              {r.updated_at ? ` · ${new Date(r.updated_at).toLocaleString()}` : ""}
            </div>
          </div>
          <div className="tut-actions">
            {(r.status === "needs_review" || r.status === "running") && (
              <button className="btn-link" onClick={() => onContinue(r.run_id, r.status)}>Continue →</button>
            )}
            {r.status === "failed" && (
              <button className="btn-link" onClick={() => onContinue(r.run_id, r.status)}>Retry →</button>
            )}
            {r.status === "completed" && (
              <a className="btn-link" href={tutorialUrl(r.run_id)} target="_blank" rel="noreferrer">Open</a>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
