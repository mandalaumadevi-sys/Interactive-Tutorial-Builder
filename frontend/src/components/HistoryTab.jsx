import { useEffect, useState } from "react";
import { getRuns, tutorialUrl } from "../api.js";

const STAGE_LABEL = {
  block: "Block division", content: "Content", animation: "Animations",
  mcq: "MCQs", assessment: "Assessment", final: "Final review", quality: "Final review",
};
// status → avatar icon + short pill label (pill colour comes from the shared .pill classes)
const STATUS = {
  completed:    { icon: "🎓", label: "Completed" },
  failed:       { icon: "⚠️", label: "Failed" },
  needs_review: { icon: "👤", label: "Your review" },
  running:      { icon: "⏳", label: "Building" },
};

function where(r) {
  if (r.status === "needs_review") return `Paused for your review · ${STAGE_LABEL[r.review_stage] || r.review_stage}`;
  if (r.status === "completed") return "Ready to open";
  if (r.status === "failed") return "Stopped — retry from the last good step";
  if (r.status === "running") return "In progress…";
  return r.status;
}

// Tab — every run (incl. incomplete), with Continue-from-where-you-stopped.
export default function HistoryTab({ active, refreshKey, onContinue }) {
  const [runs, setRuns] = useState(null);
  const [err, setErr] = useState("");
  const load = () => { setErr(""); getRuns().then(setRuns).catch(() => setErr("Couldn't reach the backend.")); };
  useEffect(() => { if (active) load(); }, [active, refreshKey]);

  const count = (fn) => (runs ? runs.filter(fn).length : 0);
  const stats = [
    { label: "All builds", value: runs ? runs.length : "—", cls: "blue", icon: "🗂️" },
    { label: "In progress", value: count((r) => r.status === "running" || r.status === "needs_review"), cls: "amber", icon: "⏳" },
    { label: "Completed", value: count((r) => r.status === "completed"), cls: "green", icon: "✅" },
  ];

  return (
    <>
      <div className="metrics-row">
        {stats.map((s) => (
          <div className="metric-card" key={s.label}>
            <div><div className="m-label">{s.label}</div><div className="m-value">{s.value}</div></div>
            <div className={`m-icon ${s.cls}`}>{s.icon}</div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="lib-head">
          <h2>All builds</h2>
          <button className="ghost" style={{ marginLeft: "auto", padding: "7px 14px" }} onClick={load}>↻ Refresh</button>
        </div>
        <p className="muted" style={{ margin: "0 0 18px" }}>
          Every build, saved at whatever stage it reached — <strong>continue</strong> an unfinished one where you
          stopped, <strong>retry</strong> a failed one, or <strong>open</strong> a finished one.
        </p>

        {err && <div className="banner err">{err}</div>}
        {!err && runs == null && <div className="muted">Loading…</div>}
        {!err && runs && runs.length === 0 && <div className="muted">No builds yet.</div>}

        {runs && runs.map((r) => {
          const s = STATUS[r.status] || { icon: "•", label: r.status };
          return (
            <div className={`build-row s-${r.status}`} key={r.run_id}>
              <div className={`build-ava s-${r.status}`}>{s.icon}</div>
              <div className="tut-main">
                <div className="tut-title">{r.session_name || "(untitled session)"}</div>
                <div className="tut-sub">
                  {r.course_name || "—"}
                  {r.updated_at ? ` · ${new Date(r.updated_at).toLocaleDateString()}` : ""} · {where(r)}
                </div>
              </div>
              <span className={`pill ${r.status}`}><span className="pill-dot" />{s.label}</span>
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
          );
        })}
      </div>
    </>
  );
}
