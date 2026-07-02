import { useEffect, useRef, useState } from "react";
import { API_BASE, getCost } from "../api.js";

const fmtINR = (n) => "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const fmtUSD = (n) => "$" + Number(n).toFixed(2);

export default function CostPanel() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const panelRef = useRef(null);
  const toggleRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    setData(null);
    setError("");
    getCost()
      .then(setData)
      .catch(() => setError(`Couldn't reach the backend at ${API_BASE}.`));
  }, [open]);

  // Click outside closes the panel.
  useEffect(() => {
    if (!open) return;
    const onClick = (e) => {
      if (panelRef.current?.contains(e.target) || toggleRef.current?.contains(e.target)) return;
      setOpen(false);
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [open]);

  const lowBalance =
    data?.remaining_credit_usd != null &&
    (data.key_limit_usd
      ? data.remaining_credit_usd <= 0.1 * data.key_limit_usd
      : data.remaining_credit_usd < 1);

  const Row = ({ label, inr, usd, cls = "" }) => (
    <div className={`cost-row ${cls}`}>
      <span>{label}</span>
      <span>
        <span className="cost-amt">{inr == null ? "—" : fmtINR(inr)}</span>
        <span className="cost-usd">{usd == null ? "" : `(${fmtUSD(usd)})`}</span>
      </span>
    </div>
  );

  return (
    <>
      <button ref={toggleRef} className="cost-chip" type="button" onClick={() => setOpen((o) => !o)}>
        ₹ Cost ▾
      </button>
      {open && (
        <div ref={panelRef} className="cost-panel">
          <h3>API cost — this app</h3>
          {!data && !error && <div className="muted">Loading…</div>}
          {error && <div className="muted">{error}</div>}
          {data && (
            <>
              <div className="cost-row"><span>Provider</span>
                <span className="cost-amt" style={{ fontSize: "1rem" }}>{data.provider}</span></div>
              <div className="cost-row cost-calls"><span>Total LLM calls (all runs)</span>
                <span className="cost-amt">{data.calls}</span></div>
              <div className="cost-row"><span>Total tokens (all runs)</span>
                <span className="cost-amt" style={{ fontSize: "1rem" }}>{Number(data.tokens_total || 0).toLocaleString()}</span></div>
              {data.model && (
                <div className="cost-row muted"><span>Model</span>
                  <span className="cost-usd">{data.model}</span></div>
              )}
              {data.key_reachable ? (
                <>
                  <div className="cost-sep" />
                  <Row label="This app has spent" inr={data.app_spend_inr} usd={data.app_spend_usd} />
                  <Row label="All apps on this key" inr={data.key_usage_inr} usd={data.key_usage_usd} />
                  <Row label="Balance left" inr={data.remaining_credit_inr} usd={data.remaining_credit_usd}
                       cls={"cost-balance" + (lowBalance ? " cost-low" : "")} />
                  {data.key_limit_usd != null && (
                    <div className="cost-row muted"><span>Key credit limit</span>
                      <span className="cost-usd">{fmtUSD(data.key_limit_usd)}</span></div>
                  )}
                  <div className="cost-note">
                    {`rate ₹${data.usd_to_inr}/$ (${data.usd_to_inr_source})`}{lowBalance ? " · ⚠ balance low" : ""}
                  </div>
                </>
              ) : (
                <div className="cost-note">
                  {data.provider === "mock"
                    ? "Mock mode — no real API calls or cost. The call count shows how many LLM calls a real run would make."
                    : "USD balance is shown only for OpenRouter. Calls above are tracked for this provider."}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </>
  );
}
