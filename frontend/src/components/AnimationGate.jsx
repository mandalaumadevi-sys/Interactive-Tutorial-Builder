import { useState } from "react";
import Frame from "./Frame.jsx";
import Metrics from "./Metrics.jsx";
import ConfirmModal from "./ConfirmModal.jsx";
import { editAnimation, getArtifacts } from "../api.js";

// Per-ANIMATION review. Accept = keep. Reject = stage removal (NO regeneration — just paused/removed
// on continue). Improve = the ONLY action that regenerates, and only that one animation; the others
// stay untouched. Edits apply in place (like the MCQ gate); "Accept all & continue" then advances.
export default function AnimationGate({ runId, artifacts, onAccept }) {
  const [art, setArt] = useState(artifacts);
  const [fb, setFb] = useState({});         // "block:image" -> feedback text
  const [rejected, setRejected] = useState({}); // "block:image" -> true (staged, client-side only)
  const [overall, setOverall] = useState("");   // one note for every animation (Improve all)
  const [busy, setBusy] = useState({});     // key -> bool
  const [finishing, setFinishing] = useState(false);
  const [confirm, setConfirm] = useState(false);

  const blocks = (art.built_blocks || []).filter((b) => (b.animations || []).length);
  const anyBusy = Object.values(busy).some(Boolean) || finishing;
  const pendingFb = overall.trim() || Object.values(fb).some((t) => (t || "").trim());
  const total = blocks.reduce((n, b) => n + (b.animations || []).length, 0);
  const rejectCount = Object.values(rejected).filter(Boolean).length;

  const kkey = (bid, iid) => `${bid}:${iid}`;
  const isRej = (bid, iid) => !!rejected[kkey(bid, iid)];
  const setRej = (bid, iid, v) => setRejected((s) => ({ ...s, [kkey(bid, iid)]: v }));

  // Improve = generate (in place). This is the ONLY action that calls Agent 2.
  const run = async (key, body, after) => {
    setBusy((s) => ({ ...s, [key]: true }));
    try {
      await editAnimation(runId, body);
      setArt(await getArtifacts(runId));   // refresh so the changed animation re-renders
      after && after();
    } catch (e) {
      alert("Update failed: " + e);
    } finally {
      setBusy((s) => ({ ...s, [key]: false }));
    }
  };
  const improve = (bid, iid) => {
    const key = kkey(bid, iid), f = (fb[key] || "").trim();
    if (f) run(key, { block_id: String(bid), image_id: iid, action: "refine", feedback: f },
               () => setFb((s) => ({ ...s, [key]: "" })));
  };
  const improveAll = async () => {
    const f = overall.trim();
    if (!f) return;
    for (const b of blocks) {
      for (const an of (b.animations || [])) {
        if (isRej(b.block_id, an.image_id)) continue;   // don't regenerate ones you're removing
        // eslint-disable-next-line no-await-in-loop
        await run(kkey(b.block_id, an.image_id),
                  { block_id: String(b.block_id), image_id: an.image_id, action: "refine", feedback: f });
      }
    }
    setOverall("");
  };

  // Continue: apply staged rejects in place (NO generation), then advance.
  const proceed = async () => {
    setFinishing(true);
    try {
      for (const b of blocks) {
        for (const an of (b.animations || [])) {
          if (!isRej(b.block_id, an.image_id)) continue;
          // eslint-disable-next-line no-await-in-loop
          await editAnimation(runId, { block_id: String(b.block_id), image_id: an.image_id, action: "reject" });
        }
      }
    } catch (e) {
      alert("Failed to remove rejected animations: " + e);
      setFinishing(false);
      return;
    }
    onAccept();
  };
  const tryProceed = () => (pendingFb ? setConfirm(true) : proceed());

  return (
    <div className="card">
      <h2>🎬 Motion Studio — the generated animations</h2>
      <div className="banner info">
        Per animation: <strong>Accept</strong> keeps it · <strong>Reject</strong> removes it (nothing
        is regenerated — it's just dropped when you continue) · type feedback and <strong>Improve</strong>
        to regenerate ONLY that one. Use <strong>Improve all</strong> to apply one note to every kept
        animation. Then <strong>Accept all &amp; continue</strong>.
      </div>
      <Metrics metrics={(art.eval_scores || {}).visual} />

      {blocks.length ? (
        <>
          <label style={{ fontWeight: 700, color: "var(--ink)" }}>Improve all animations <em style={{ fontWeight: 500, color: "var(--muted)", fontStyle: "normal" }}>({total} in total{rejectCount ? `, ${rejectCount} to remove` : ""})</em></label>
          <div className="block-fb">
            <textarea className="rev-fb" value={overall} disabled={anyBusy}
              placeholder="One note for every kept animation — e.g. 'slower, clearer reveal', 'use the diagram's exact labels'"
              onChange={(e) => setOverall(e.target.value)} />
            <button type="button" className="apply-btn" disabled={anyBusy || !overall.trim()} onClick={improveAll}>
              {anyBusy ? "Working…" : "Improve all"}
            </button>
          </div>

          <div className="rev-row">
            {blocks.map((b) => (
              <div className="rev-block" key={b.block_id}>
                <div className="rev-h">Block {b.block_id} · {b.title || ""}</div>
                {(b.animations || []).map((an) => {
                  const key = kkey(b.block_id, an.image_id), busyK = busy[key], rej = isRej(b.block_id, an.image_id);
                  return (
                    <div key={an.image_id} className={`anim-item ${rej ? "rejected" : ""} ${busyK ? "busy" : ""}`}>
                      <div className="muted" style={{ fontSize: ".8rem", marginBottom: 4 }}>
                        {rej ? <span className="anim-rej">✗ rejected — removed on continue</span>
                             : <span className="anim-keep">✓ kept</span>} · {an.visual_type || "concept"}
                        {an.reference_template ? ` · ref: ${an.reference_template}` : ""}
                      </div>
                      <Frame html={an.html} height={240} />
                      <div className="gate-row">
                        <button type="button" className={`acc-btn ${!rej ? "on" : ""}`}
                          onClick={() => setRej(b.block_id, an.image_id, false)}>✓ Accept</button>
                        <button type="button" className={`rej-btn ${rej ? "on" : ""}`}
                          onClick={() => setRej(b.block_id, an.image_id, true)}>✗ Reject</button>
                      </div>
                      {!rej && (
                        <>
                          <textarea className="rev-fb" value={fb[key] || ""} disabled={busyK}
                            placeholder="Feedback to regenerate THIS animation"
                            onChange={(e) => setFb((s) => ({ ...s, [key]: e.target.value }))} />
                          <div className="gate-row">
                            <button type="button" className="apply-btn" disabled={busyK || !(fb[key] || "").trim()}
                              onClick={() => improve(b.block_id, an.image_id)}>{busyK ? "Regenerating…" : "Improve"}</button>
                          </div>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
          <p className="muted" style={{ marginTop: "-4px", fontSize: ".85rem" }}>← scroll sideways →</p>

          <div className="actions">
            <button className="green" disabled={anyBusy} onClick={tryProceed}>
              {finishing ? "Finishing…" : "Accept all & continue →"}
            </button>
          </div>

          <ConfirmModal open={confirm}
            title="Apply your feedback first?"
            message="You've typed animation feedback but haven't clicked Improve, so it wasn't used. Continuing keeps those animations as shown (rejected ones are still removed)."
            confirmLabel="Discard feedback & continue" cancelLabel="Go back & apply"
            onCancel={() => setConfirm(false)}
            onConfirm={() => { setConfirm(false); proceed(); }} />
        </>
      ) : (
        <>
          <div className="muted">No animations were needed for this session (no concept diagrams).</div>
          <div className="actions"><button className="green" onClick={onAccept}>Continue →</button></div>
        </>
      )}
    </div>
  );
}
