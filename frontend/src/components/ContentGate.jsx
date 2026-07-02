import { useState } from "react";
import Frame from "./Frame.jsx";
import ConfirmModal from "./ConfirmModal.jsx";

export default function ContentGate({ artifacts, onAccept, onRefine }) {
  const blocks = artifacts.built_blocks || [];
  const [fb, setFb] = useState({}); // { block_id: feedback }
  const [overall, setOverall] = useState(""); // one note applied to ALL blocks
  const [confirm, setConfirm] = useState(false);

  // per-block note wins for that block; otherwise the "all blocks" note applies.
  const allFb = overall.trim();
  const map = {};
  blocks.forEach((b) => { const t = (fb[b.block_id] || "").trim() || allFb; if (t) map[b.block_id] = t; });
  const n = Object.keys(map).length;

  return (
    <div className="card">
      <h2>✍️ Content Studio — the written lesson blocks</h2>
      <div className="banner info">
        Review each block. Use <strong>Improve all blocks</strong> to apply one note to every block,
        or leave feedback on specific blocks below (a per-block note overrides the all-blocks note).
        Leave everything empty to accept as-is.
      </div>

      <label style={{ fontWeight: 700, color: "var(--ink)" }}>Improve all blocks <em style={{ fontWeight: 500, color: "var(--muted)", fontStyle: "normal" }}>(applies to every block)</em></label>
      <div className="block-fb">
        <textarea className="rev-fb" value={overall}
          placeholder="One note for the whole tutorial — e.g. 'tighten the prose', 'use only PPT facts, drop anything extra', 'add a short intro line per block'"
          onChange={(e) => setOverall(e.target.value)} />
      </div>

      {blocks.length ? (
        <div className="rev-row">
          {blocks.map((b) => (
            <div className="rev-block" key={b.block_id}>
              <div className="rev-h">Block {b.block_id} · {b.title || ""}</div>
              {(b.quality_issues || []).length > 0 && (
                <div className="banner err" style={{ margin: "6px 0" }}>⚠ {(b.quality_issues || []).join("; ")}</div>
              )}
              <Frame html={b.content_html} height={280} />
              <textarea className="rev-fb" value={fb[b.block_id] || ""}
                placeholder="Feedback for THIS block (leave empty to accept)"
                onChange={(e) => setFb((s) => ({ ...s, [b.block_id]: e.target.value }))} />
            </div>
          ))}
        </div>
      ) : <div className="muted">No content.</div>}
      <p className="muted" style={{ marginTop: "-4px", fontSize: ".85rem" }}>← scroll sideways to see all blocks →</p>

      <div className="actions">
        {n > 0 ? (
          <>
            <button className="green" onClick={() => onRefine(map)}>
              {allFb ? `Improve all ${n} block${n > 1 ? "s" : ""} →` : `Refine ${n} block${n > 1 ? "s" : ""} →`}
            </button>
            <button className="ghost" onClick={() => setConfirm(true)}>Accept all (ignore feedback)</button>
          </>
        ) : (
          <button className="green" onClick={onAccept}>Accept all &amp; continue →</button>
        )}
      </div>

      <ConfirmModal open={confirm}
        title="Discard your feedback?"
        message={`You've written feedback on ${n} block${n > 1 ? "s" : ""} but are about to accept without applying it. Those blocks will be kept as-is and your feedback discarded.`}
        confirmLabel="Discard & accept" cancelLabel="Go back & refine"
        onCancel={() => setConfirm(false)}
        onConfirm={() => { setConfirm(false); onAccept(); }} />
    </div>
  );
}
