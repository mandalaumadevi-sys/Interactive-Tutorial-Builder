// Advisory per-stage eval metrics shown at each gate. `m` = {score, passed, summary, dimensions[]}.
export default function Metrics({ metrics }) {
  if (!metrics) return null;
  const score = metrics.score != null ? Number(metrics.score).toFixed(1) : "—";
  return (
    <div className="metrics">
      <div className="metric-head">
        Eval score
        <span className={`score ${metrics.passed ? "pass" : "fail"}`}>
          {score} / 10 {metrics.passed ? "✓" : "⚠"}
        </span>
      </div>
      {metrics.summary && (
        <div className="muted" style={{ margin: "4px 0 8px" }}>{metrics.summary}</div>
      )}
      {(metrics.dimensions || []).map((d, i) => (
        <div className="dim" key={i}>
          <span>{d.dimension}</span>
          <span className={`score ${d.passed ? "pass" : "fail"}`}>
            {Number(d.score).toFixed(1)} {d.passed ? "✓" : "✗"}
          </span>
        </div>
      ))}
    </div>
  );
}
