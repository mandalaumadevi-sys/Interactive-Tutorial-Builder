import { useEffect, useState } from "react";
import { getTutorials, getCost, apiUrl } from "../api.js";

const GRAD = ["g1", "g2", "g3", "g4", "g5"];
const monogram = (s) => (s || "?").trim().charAt(0).toUpperCase();

// Tutorial Library — metric cards + a grid of generated-tutorial cards.
export default function TutorialsTab({ active, refreshKey }) {
  const [items, setItems] = useState(null);
  const [cost, setCost] = useState(null);
  const [err, setErr] = useState("");

  const load = () => {
    setErr("");
    getTutorials().then(setItems).catch(() => setErr("Couldn't reach the backend."));
    getCost().then(setCost).catch(() => setCost(null));
  };
  useEffect(() => { if (active) load(); }, [active, refreshKey]);

  const courses = items ? new Set(items.map((t) => t.course_name).filter(Boolean)).size : 0;
  const spend = cost?.app_spend_usd != null ? `$${Number(cost.app_spend_usd).toFixed(2)}`
    : cost?.tokens_total != null ? `${Number(cost.tokens_total).toLocaleString()} tok` : "—";

  return (
    <>
      <div className="metrics-row">
        <div className="metric-card">
          <div><div className="m-label">Total tutorials</div><div className="m-value">{items ? items.length : "—"}</div></div>
          <div className="m-icon blue">📚</div>
        </div>
        <div className="metric-card">
          <div><div className="m-label">Courses</div><div className="m-value">{items ? courses : "—"}</div></div>
          <div className="m-icon purple">🎓</div>
        </div>
        <div className="metric-card">
          <div><div className="m-label">Cumulative cost</div><div className="m-value">{spend}</div></div>
          <div className="m-icon green">$</div>
        </div>
      </div>

      <div className="card">
        <div className="lib-head">
          <h2>Generated tutorials</h2>
          <button className="ghost" style={{ marginLeft: "auto", padding: "7px 14px" }} onClick={load}>↻ Refresh</button>
        </div>
        <p className="muted" style={{ margin: "0 0 18px" }}>
          Every completed build, newest first. Saved under <code>generated_tutorials/&lt;course&gt;/&lt;session&gt;.html</code>.
        </p>

        {err && <div className="banner err">{err}</div>}
        {!err && items == null && <div className="muted">Loading…</div>}
        {!err && items && items.length === 0 && (
          <div className="muted">No tutorials yet — create one from the <strong>Build</strong> tab.</div>
        )}

        {items && items.length > 0 && (
          <div className="tut-grid">
            {items.map((t, i) => (
              <div className="tut-card" key={t.run_id || `${t.rel_path}-${i}`}>
                <div className={`thumb ${GRAD[i % GRAD.length]}`}>
                  <span className="thumb-emoji">{monogram(t.session_name)}</span>
                  <span className="tbadge">Interactive</span>
                </div>
                <div className="tbody">
                  <div className="tname">{t.session_name || "(untitled session)"}</div>
                  <div className="tmeta">
                    {t.course_name || "—"}{t.updated_at ? ` · ${new Date(t.updated_at).toLocaleDateString()}` : ""}
                  </div>
                  <div className="tfoot">
                    <a className="view" href={apiUrl(t.tutorial_url)} target="_blank" rel="noreferrer">View Tutorial →</a>
                    <a className="dl" href={apiUrl(t.download_url)} target="_blank" rel="noreferrer">Download</a>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
