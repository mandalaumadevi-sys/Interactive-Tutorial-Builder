import { pipelineStates } from "../pipeline.js";

const STATE_LABEL = { wait: "your turn", active: "running…", done: "done", pending: "" };
// Loop-back semantics shown on the human gate nodes.
const LOOP = {
  block: "⟲ feedback → re-divide",
  reviewContent: "⟲ refine → re-write",
  reviewAnimation: "⟲ refine → regenerate",
  reviewMcq: "⟲ refine → regenerate",
  final: "⟲ refine → regenerate",
  finalReview: "⟲ improve any element in place",
};

// Tab 3 — the workflow as an animated FLOW GRAPH (nodes + arrows + loop-backs), not a list.
export default function PipelineTab({ pipe, idle }) {
  const steps = pipelineStates(pipe);
  const total = steps.length;
  const doneCount = steps.filter((s) => s.state === "done").length;
  const pct = Math.round((doneCount / total) * 100);
  const current = steps.find((s) => s.state === "wait") || steps.find((s) => s.state === "active");

  return (
    <div className="card">
      <h2>The build workflow</h2>
      <p className="muted" style={{ marginBottom: 12 }}>
        The agentic pipeline as a live flow graph. <span className="leg-auto">⚙</span> nodes run
        automatically; <span className="leg-human">👤</span> nodes are human gates that can loop back.
      </p>

      <div className="pipe-now">
        {idle && !current ? (
          <span className="muted">No build yet — start one from the <strong>Build</strong> tab.</span>
        ) : current ? (
          <>
            <span className="pipe-now-dot" />
            <span>Currently: <strong>{current.label}</strong>
              {current.state === "wait" ? " — waiting for your review" : " — in progress"}</span>
          </>
        ) : (
          <span className="pipe-done-badge">✅ Completed</span>
        )}
      </div>

      <div className="pipe-meter"><div className="pipe-meter-fill" style={{ width: `${pct}%` }} /></div>
      <div className="pipe-meter-label">{doneCount} / {total} nodes complete</div>

      <div className="flow">
        {steps.map((s, i) => (
          <div className="fnode-wrap" key={s.id}>
            <div className={`fnode ${s.state} ${s.kind}`}>
              <span className="ficon">{s.kind === "human" ? "👤" : "⚙"}</span>
              <span className="flabel">{s.label}</span>
              {STATE_LABEL[s.state] && <span className="ftag">{STATE_LABEL[s.state]}</span>}
              {LOOP[s.id] && <span className="floop">{LOOP[s.id]}</span>}
            </div>
            {i < steps.length - 1 && (
              <div className={`fedge ${s.state === "done" ? "done" : ""}`}>
                {steps[i].kind === "human" && <span className="felabel">accept</span>}
              </div>
            )}
          </div>
        ))}
        <div className="fnode-wrap">
          <div className="fedge done-cap"><span className="felabel">publish</span></div>
          <div className={`fnode terminal ${pipe.done ? "done" : ""}`}>
            <span className="ficon">🎓</span><span className="flabel">Interactive tutorial</span>
          </div>
        </div>
      </div>
    </div>
  );
}
