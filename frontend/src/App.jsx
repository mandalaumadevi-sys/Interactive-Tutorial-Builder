import { useEffect, useRef, useState } from "react";
import {
  startBuild, getRun, getArtifacts, openEvents, tutorialUrl, retryRun, finalizeRun,
  resumeBlocks, resumeStage, proceedFinal,
} from "./api.js";
import { NODE_LABELS, NODE_TO_STEP, STAGE_TO_STEP, STEP_IDX } from "./pipeline.js";
import CostPanel from "./components/CostPanel.jsx";
import UploadCard from "./components/UploadCard.jsx";
import PipelineTab from "./components/PipelineTab.jsx";
import TutorialsTab from "./components/TutorialsTab.jsx";
import HistoryTab from "./components/HistoryTab.jsx";
import BlockGate from "./components/BlockGate.jsx";
import ContentGate from "./components/ContentGate.jsx";
import AnimationGate from "./components/AnimationGate.jsx";
import McqGate from "./components/McqGate.jsx";
import AssessmentGate from "./components/AssessmentGate.jsx";
import FinalReviewGate from "./components/FinalReviewGate.jsx";

const FRESH_PIPE = { reached: -1, waiting: null, done: false };
const RUN_KEY = "tb_active_run"; // remember the in-flight run so a refresh resumes it

export default function App() {
  const [tab, setTab] = useState("workflow");
  const [tutorialsKey, setTutorialsKey] = useState(0); // bump → refresh tutorials list
  const [runId, setRunId] = useState(null);
  const [status, setStatus] = useState("idle"); // idle|running|needs_review|completed|failed
  const [stage, setStage] = useState(null);
  const [artifacts, setArtifacts] = useState(null);
  const [progressMsg, setProgressMsg] = useState("Building your tutorial…");
  const [errorMsg, setErrorMsg] = useState("");
  const [calls, setCalls] = useState(0);   // LLM calls this run (from SSE)
  const [tokens, setTokens] = useState(0); // tokens this run (from SSE)
  const [pipe, setPipe] = useState(FRESH_PIPE);
  const esRef = useRef(null);

  // ── pipeline progress helpers ──
  const pipeNode = (node) => {
    const id = NODE_TO_STEP[node];
    if (id == null) return;
    setPipe((p) => ({ ...p, reached: Math.max(p.reached, STEP_IDX[id]), waiting: null }));
  };
  const pipeGate = (s) => {
    const id = STAGE_TO_STEP[s];
    if (id == null) return;
    setPipe((p) => ({ reached: Math.max(p.reached, STEP_IDX[id]), waiting: id, done: false }));
  };
  const pipeDone = () => setPipe((p) => ({ ...p, waiting: null, done: true }));

  // ── SSE lifecycle ──
  const listen = (rid) => {
    if (esRef.current) esRef.current.close();
    const es = openEvents(rid);
    esRef.current = es;
    es.onmessage = (e) => {
      const ev = JSON.parse(e.data);
      if (ev.type === "node") {
        pipeNode(ev.node);
        if (ev.status === "start" && NODE_LABELS[ev.node]) setProgressMsg(NODE_LABELS[ev.node] + "…");
      } else if (ev.type === "run") {
        es.close();
        if (ev.calls != null) setCalls(ev.calls);
        if (ev.tokens != null) setTokens(ev.tokens);
        if (ev.status === "needs_review") onReview(rid, ev.stage);
        else if (ev.status === "completed") { setStatus("completed"); pipeDone(); setTutorialsKey((k) => k + 1); }
        else if (ev.status === "failed") { setStatus("failed"); setErrorMsg(ev.message || "The run failed."); }
      }
    };
  };

  const onReview = async (rid, s) => {
    setStatus("needs_review");
    setStage(s);
    pipeGate(s);
    setArtifacts(await getArtifacts(rid));
  };

  const start = async (file, meta, addons) => {
    setErrorMsg("");
    let res;
    try {
      res = await startBuild(file, meta, addons);
    } catch (err) {
      setErrorMsg(`Could not start the build. Is the backend running? ${err}`);
      setStatus("failed");
      return;
    }
    setRunId(res.run_id);
    localStorage.setItem(RUN_KEY, res.run_id); // remember it so a refresh resumes this run
    setPipe(FRESH_PIPE);
    setCalls(0);
    setTokens(0);
    setStatus("running");
    setProgressMsg("Reading the session…");
    setStage(null);
    setArtifacts(null);
    listen(res.run_id);
  };

  // Load a run by id and restore the UI to exactly where it stopped (used on refresh AND from the
  // History tab's "Continue").
  const restoreRun = async (rid) => {
    let info;
    try { info = await getRun(rid); }
    catch { localStorage.removeItem(RUN_KEY); return; }
    localStorage.setItem(RUN_KEY, rid);
    setRunId(rid);
    setCalls(info.llm_calls || 0);
    setTokens(info.llm_tokens || 0);
    setErrorMsg("");
    const stepId = NODE_TO_STEP[info.current_node];
    setPipe(stepId != null ? { reached: STEP_IDX[stepId], waiting: null, done: false } : FRESH_PIPE);
    if (info.status === "running") {
      setStatus("running"); setProgressMsg("Resuming your run…"); setStage(null); setArtifacts(null); listen(rid);
    } else if (info.status === "needs_review") {
      onReview(rid, info.review_stage);
    } else if (info.status === "completed") {
      setStatus("completed"); pipeDone();
    } else if (info.status === "failed") {
      setStatus("failed"); setErrorMsg(info.message || "The run failed.");
    }
  };

  // On load: resume the last run instead of dropping the user back to step 1.
  useEffect(() => {
    const rid = localStorage.getItem(RUN_KEY);
    if (rid) restoreRun(rid);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const continueFromHistory = async (rid, status) => {
    setTab("workflow");
    if (status === "failed") {
      // re-run from the last good checkpoint, then follow it live
      setRunId(rid);
      localStorage.setItem(RUN_KEY, rid);
      setStatus("running");
      setProgressMsg("Retrying from where it stopped…");
      setStage(null); setArtifacts(null); setErrorMsg("");
      try { await retryRun(rid); listen(rid); }
      catch (err) { setStatus("failed"); setErrorMsg(`Retry failed: ${err}`); }
    } else {
      restoreRun(rid);
    }
  };

  // resume → show progress, fire the API call, reopen the event stream
  const doResume = (apiCall, msg) => {
    setStatus("running");
    setProgressMsg(msg);
    setStage(null);
    setArtifacts(null);
    apiCall().then(() => listen(runId));
  };

  // Final "Accept & finalize": assemble the tutorial directly from the run's current state.
  // This is deterministic (no graph resume), so it completes reliably — and also rescues runs
  // created under an earlier flow version that can't advance through the graph.
  const finalize = async () => {
    setStatus("running");
    setProgressMsg("Finalizing & assembling the tutorial…");
    setStage(null);
    setArtifacts(null);
    if (esRef.current) esRef.current.close();
    try {
      await finalizeRun(runId);
      setStatus("completed");
      pipeDone();
      setTutorialsKey((k) => k + 1);
    } catch (err) {
      setStatus("failed");
      setErrorMsg(`Finalize failed: ${err}`);
    }
  };

  const busy = status === "running" || status === "needs_review";

  // sidebar navigation (icon = inline SVG path drawn in NavIcon)
  // "Builds" = every run, saved at whatever stage (resumable). "Tutorials" = only end-to-end
  // published ones. The new-tutorial FORM is reached via the "+ New Tutorial" button (below).
  const NAV = [
    { id: "builds", label: "Builds", icon: "builds" },
    { id: "tutorials", label: "Tutorials", icon: "library" },
    { id: "pipeline", label: "Workflow", icon: "flow" },
  ];
  const PAGE_TITLE = {
    workflow: "New tutorial", builds: "Builds", tutorials: "Tutorials", pipeline: "Workflow",
  };
  // "+ New Tutorial" → go to the Build page AND start fresh (clear any finished/in-flight run),
  // so the user always lands on a clean New-tutorial form.
  const newTutorial = () => {
    if (esRef.current) esRef.current.close();
    localStorage.removeItem(RUN_KEY);
    setRunId(null); setStatus("idle"); setStage(null); setArtifacts(null);
    setErrorMsg(""); setPipe(FRESH_PIPE); setCalls(0); setTokens(0);
    setTab("workflow");
  };

  const renderGate = () => {
    if (status !== "needs_review" || !artifacts) return null;
    switch (stage) {
      case "block":
        return <BlockGate artifacts={artifacts}
          onAccept={() => doResume(() => resumeBlocks(runId, true), "Division accepted — writing block content…")}
          onRefine={(fb) => doResume(() => resumeBlocks(runId, false, fb), "Re-dividing with your feedback…")} />;
      case "content":
        return <ContentGate artifacts={artifacts}
          onAccept={() => doResume(() => resumeStage(runId, "content", true), "Content accepted — building animations…")}
          onRefine={(map) => doResume(() => resumeStage(runId, "content", false, "", map), "Re-writing the flagged block(s)…")} />;
      case "animation":
        return <AnimationGate runId={runId} artifacts={artifacts}
          onAccept={() => doResume(() => resumeStage(runId, "animation", true), "Animations accepted — writing quizzes…")} />;
      case "mcq":
        return <McqGate runId={runId} artifacts={artifacts}
          onAccept={() => doResume(() => resumeStage(runId, "mcq", true), "MCQs accepted — building the final assessment…")} />;
      case "assessment":
        return <AssessmentGate runId={runId} artifacts={artifacts}
          onAccept={() => doResume(() => resumeStage(runId, "assessment", true), "Assembling the full tutorial for final review…")} />;
      default: // "final" — combined review of the whole assembled tutorial
        return <FinalReviewGate runId={runId} artifacts={artifacts}
          onPublish={(notes) => doResume(() => proceedFinal(runId, notes), "Publishing the tutorial…")} />;
    }
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <h1>Tuti</h1>
          <div className="brand-name">Your Interactive Tutorial Builder</div>
          <div className="brand-sub">Agentic Engine</div>
        </div>
        <nav className="nav">
          {NAV.map((n) => (
            <button key={n.id} className={`navitem ${tab === n.id ? "active" : ""}`} onClick={() => setTab(n.id)}>
              <NavIcon name={n.icon} /> {n.label}
            </button>
          ))}
        </nav>
        <div className="nav-spacer" />
        <button className={`newflow ${tab === "workflow" ? "active" : ""}`} onClick={newTutorial}>+ New Tutorial</button>
      </aside>

      <div className="appmain">
        <header className="topbar">
          <span className="page-title">{PAGE_TITLE[tab] || "Interactive Tutorial Builder"}</span>
          <div className="spacer" />
          {tab === "workflow" && status !== "idle" && (
            <span className={`pill ${status}`}><span className="pill-dot" />{status.replace("_", " ")}</span>
          )}
          <CostPanel />
        </header>

        <main className="content">
          <section className={tab === "workflow" ? "" : "hidden"}>
            {/* Only show the New-tutorial form when idle. While a build is running / paused at a gate
                / done, hide it so "Continue" lands directly on the gate (not below the upload form).
                Use "+ New Tutorial" in the sidebar to start fresh. */}
            {status === "idle" && <UploadCard onStart={start} />}

            {status === "running" && (
              <div className="card run-card">
                <div className="spin-wrap"><div className="spinner" /><span>{progressMsg}</span></div>
              </div>
            )}

            {status === "failed" && (
              <div className="card"><div className="banner err"><strong>Build failed.</strong> {errorMsg}</div></div>
            )}

            {renderGate()}

            {status === "completed" && (
              <div className="card completed-card">
                <h2>✅ Tutorial ready 🎉</h2>
                <p className="muted">Saved to your tutorials library: generated_tutorials/&lt;course&gt;/&lt;session&gt;.html (rebuilds are versioned).</p>
                <p className="muted">This build made <strong>{calls}</strong> LLM call{calls === 1 ? "" : "s"} using <strong>{tokens.toLocaleString()}</strong> tokens.</p>
                <div className="actions">
                  <button onClick={() => window.open(tutorialUrl(runId), "_blank")}>Open tutorial</button>
                  <button className="ghost" onClick={() => window.open(tutorialUrl(runId, true), "_blank")}>Download .html</button>
                  <button className="ghost" onClick={newTutorial}>+ Build another</button>
                </div>
              </div>
            )}

            {status === "failed" && (
              <div className="actions"><button className="ghost" onClick={newTutorial}>+ Start a new tutorial</button></div>
            )}

          </section>

          <section className={tab === "builds" ? "" : "hidden"}>
            <HistoryTab active={tab === "builds"} refreshKey={tutorialsKey} onContinue={continueFromHistory} />
          </section>

          <section className={tab === "tutorials" ? "" : "hidden"}>
            <TutorialsTab active={tab === "tutorials"} refreshKey={tutorialsKey} />
          </section>

          <section className={tab === "pipeline" ? "" : "hidden"}>
            <PipelineTab pipe={pipe} idle={status === "idle"} />
          </section>
        </main>
      </div>
    </div>
  );
}

// Minimal line icons for the sidebar nav.
function NavIcon({ name }) {
  const common = { className: "ico", width: 20, height: 20, viewBox: "0 0 24 24", fill: "none",
    stroke: "currentColor", strokeWidth: 1.9, strokeLinecap: "round", strokeLinejoin: "round" };
  const paths = {
    dashboard: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    library: <><path d="M4 5a2 2 0 0 1 2-2h6v18H6a2 2 0 0 1-2-2z" /><path d="M12 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6" /></>,
    builds: <><rect x="3" y="3" width="6" height="6" rx="1" /><rect x="15" y="15" width="6" height="6" rx="1" /><path d="M6 9v3a3 3 0 0 0 3 3h6" /></>,
    analytics: <><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></>,
    flow: <><circle cx="6" cy="6" r="2.2" /><circle cx="18" cy="18" r="2.2" /><path d="M8.2 6H15a3 3 0 0 1 3 3v6.8" /></>,
  };
  return <svg {...common}>{paths[name] || null}</svg>;
}
