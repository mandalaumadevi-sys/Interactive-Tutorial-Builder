import { useEffect, useState } from "react";
import { getDbStatus } from "../api.js";

// Small header badge: is persistence on Supabase, or the local SQLite fallback?
export default function DbStatus() {
  const [s, setS] = useState(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () => getDbStatus().then((d) => alive && setS(d)).catch(() => alive && setErr(true));
    load();
    const t = setInterval(load, 20000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (err) return <span className="db-badge db-down" title="Backend unreachable">DB: ?</span>;
  if (!s) return <span className="db-badge db-pending">DB…</span>;
  const cls = s.connected ? "db-ok" : "db-fallback";
  const label = s.connected ? "Supabase" : "local fallback";
  return (
    <span className={`db-badge ${cls}`} title={`${s.detail}\n\n${s.note}`}>
      ● DB: {label}
    </span>
  );
}
