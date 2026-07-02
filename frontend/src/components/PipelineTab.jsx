import { useLayoutEffect, useRef, useState } from "react";
import { PIPELINE, pipelineStates } from "../pipeline.js";
import TutiBot from "./TutiBot.jsx";

// ── flowchart geometry ──
const VB_W = 1000, VB_H = 1540;
const NODE_W = 300, NODE_H = 62, X = 350, CX = 500, Y0 = 152, STEP = 92;
const topY = (i) => Y0 + i * STEP;
const midY = (i) => Y0 + i * STEP + NODE_H / 2;

// the spine, in flow order (ids match the pipeline model so we can colour by live state)
const SPINE = [
  { id: "ingest",          t: "Ingest + normalize",     s: "read deck / page · describe images" },
  { id: "divide",          t: "Block Divider",          s: "group into teaching blocks" },
  { id: "block",           t: "Review block division",  s: "accept ✓ · or re-divide" },
  { id: "content",         t: "Agent 1 · Content",      s: "rewrite → source-only HTML" },
  { id: "reviewContent",   t: "Review content",         s: "tweak a block · or accept all" },
  { id: "animation",       t: "Agent 2 · Animation",    s: "vision → clean visuals" },
  { id: "reviewAnimation", t: "Review animations",      s: "accept · reject · improve" },
  { id: "mcq",             t: "Agent 3 · MCQs",         s: "per-block quizzes" },
  { id: "reviewMcq",       t: "Review MCQs",            s: "accept per block" },
  { id: "assessment",      t: "Agent 4 · Assessment",   s: "session-wide Q&A" },
  { id: "final",           t: "Review assessment",      s: "accept · or refine" },
  { id: "finalReview",     t: "Final review",           s: "whole tutorial, in place" },
  { id: "assemble",        t: "Publish",                s: "assemble one .html" },
  { id: "terminal",        t: "Interactive tutorial",   s: "generated .html", type: "output" },
];
const IDX = Object.fromEntries(SPINE.map((n, i) => [n.id, i]));
const KIND = Object.fromEntries(PIPELINE.map((s) => [s.id, s.kind]));       // auto | human
const ICON = Object.fromEntries(PIPELINE.map((s) => [s.id, s.icon]));
// human gate → the generator directly above it that a "refine" loops back to
const LOOPS = { block: "divide", reviewContent: "content", reviewAnimation: "animation", reviewMcq: "mcq", final: "assessment" };
const LOOP_LABEL = { block: "↺ re-divide", reviewContent: "↺ re-write", reviewAnimation: "↺ regenerate", reviewMcq: "↺ regenerate", final: "↺ regenerate" };

const GUIDE = {
  ingest: "📖 Reading your session and describing every image.",
  divide: "🧩 Splitting the material into clean teaching blocks.",
  block: "It’s your turn — check how I divided the blocks. Accept, or ask me to re-divide.",
  content: "✍️ Writing each block from your source only — nothing invented.",
  reviewContent: "Review the content — tweak any block, or accept them all.",
  animation: "🎬 Turning your diagrams into clean, labelled animations.",
  reviewAnimation: "Check the animations — accept, reject, or ask me to improve one.",
  mcq: "🧠 Writing quizzes that test each block directly.",
  reviewMcq: "Review the quizzes, block by block.",
  assessment: "🎯 Building the session-wide final assessment.",
  final: "Review the assessment questions before we wrap up.",
  finalReview: "One last look at the whole tutorial before we publish.",
  assemble: "🚀 Assembling everything into one interactive tutorial!",
  terminal: "🎉 All done — your interactive tutorial is ready!",
  idle: "👋 Hi, I’m Tuti! Start a build and I’ll guide you through every step.",
};

// node fill/stroke/text by live state (kept close to the reference palette)
function paint(state, type) {
  if (type === "output") return state === "done"
    ? { fill: "#dcfce7", stroke: "#16a34a", ink: "#166534", sub: "#15803d" }
    : { fill: "#f8fafc", stroke: "#cbd5e1", ink: "#64748b", sub: "#94a3b8" };
  switch (state) {
    case "done":   return { fill: "#ecfdf5", stroke: "#10b981", ink: "#065f46", sub: "#15803d" };
    case "active": return { fill: "#eff6ff", stroke: "#2563eb", ink: "#1e3a8a", sub: "#1d4ed8" };
    case "wait":   return { fill: "#fffbeb", stroke: "#f59e0b", ink: "#92400e", sub: "#b45309" };
    default:       return { fill: "#ffffff", stroke: "#e2e8f0", ink: "#94a3b8", sub: "#b8c2d4" };
  }
}
const STATE_TAG = { wait: "your turn", active: "running…", done: "done", pending: "" };

export default function PipelineTab({ pipe, idle }) {
  const steps = pipelineStates(pipe);
  const stateOf = Object.fromEntries(steps.map((s) => [s.id, s.state]));
  stateOf.terminal = pipe.done ? "done" : "pending";
  const doneCount = steps.filter((s) => s.state === "done").length;
  const pct = Math.round((doneCount / steps.length) * 100);
  const current = steps.find((s) => s.state === "wait") || steps.find((s) => s.state === "active");
  const activeId = pipe.done ? "terminal" : current?.id ?? "ingest";
  const guideText = pipe.done ? GUIDE.terminal : current ? GUIDE[current.id] : GUIDE.idle;

  // slide the Tuti guide so it lines up (by height) with the active node in the scaled SVG
  const svgRef = useRef(null);
  const [botTop, setBotTop] = useState(0);
  useLayoutEffect(() => {
    const place = () => {
      const svg = svgRef.current;
      if (!svg) return;
      setBotTop((svg.clientHeight / VB_H) * midY(IDX[activeId]));
    };
    place();
    const ro = new ResizeObserver(place);
    if (svgRef.current) ro.observe(svgRef.current);
    return () => ro.disconnect();
  }, [activeId, pipe.done]);

  const Marker = ({ id, color }) => (
    <marker id={id} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill={color} />
    </marker>
  );

  return (
    <div className="card">
      <h2>The build workflow</h2>
      <p className="muted" style={{ marginBottom: 14 }}>
        Tuti’s agentic pipeline as a flow graph — <span className="leg-auto">⚙ automatic</span> steps run on
        their own; <span className="leg-human">👤 human gates</span> pause for your review and can loop back.
      </p>
      <div className="pipe-meter"><div className="pipe-meter-fill" style={{ width: `${pct}%` }} /></div>
      <div className="pipe-meter-label">{doneCount} / {steps.length} steps complete</div>

      <div className="wf">
        {/* travelling guide */}
        <div className="wf-guide" style={{ top: botTop }}>
          <div className="wf-bot"><TutiBot size={70} /></div>
          <div className="wf-bubble" key={guideText}>{guideText}</div>
        </div>

        <svg ref={svgRef} className="wf-svg" viewBox={`0 0 ${VB_W} ${VB_H}`} preserveAspectRatio="xMidYMin meet"
             fontFamily="Inter,system-ui,sans-serif">
          <defs>
            <Marker id="mk-grey" color="#94a3b8" /><Marker id="mk-green" color="#16a34a" />
            <Marker id="mk-amber" color="#d97706" /><Marker id="mk-purple" color="#8b5cf6" />
            <Marker id="mk-teal" color="#0891b2" />
          </defs>

          {/* ── side rail: course memory ── */}
          <g>
            <rect x="16" y="176" width="214" height="250" rx="14" fill="#f5f3ff" stroke="#8b5cf6" strokeWidth="1.5" />
            <text x="123" y="206" textAnchor="middle" fontSize="15" fontWeight="800" fill="#6d28d9">🧠 Course memory</text>
            <text x="34" y="238" fontSize="11.5" fill="#7c3aed">• Feedback (applied once)</text>
            <text x="34" y="262" fontSize="11.5" fill="#7c3aed">• Concepts + MCQ topics</text>
            <text x="34" y="286" fontSize="11.5" fill="#7c3aed">• Eval-score history</text>
            <text x="34" y="310" fontSize="11.5" fill="#7c3aed">• Run checkpoints (resume)</text>
            <text x="123" y="348" textAnchor="middle" fontSize="11" fill="#8b5cf6">read at ingest ·</text>
            <text x="123" y="366" textAnchor="middle" fontSize="11" fill="#8b5cf6">written at the end</text>
            {/* read → ingest */}
            <path d={`M230 250 L${X} ${midY(0)}`} fill="none" stroke="#c4b5fd" strokeWidth="1.4" strokeDasharray="4 4" markerEnd="url(#mk-purple)" />
            <text x="250" y="150" fontSize="10.5" fill="#8b5cf6">load memory</text>
            {/* write back (hugs the left margin) */}
            <path d={`M${X} ${midY(12)} H 120 V 430`} fill="none" stroke="#c4b5fd" strokeWidth="1.4" strokeDasharray="4 4" markerEnd="url(#mk-purple)" />
            <text x="128" y="880" fontSize="10.5" fill="#8b5cf6">write back</text>
          </g>

          {/* ── side rail: eval-sets ── */}
          <g>
            <rect x="770" y="402" width="214" height="612" rx="14" fill="#ecfeff" stroke="#0891b2" strokeWidth="1.5" />
            <text x="877" y="432" textAnchor="middle" fontSize="15" fontWeight="800" fill="#0e7490">⚖️ Eval-sets</text>
            <text x="877" y="452" textAnchor="middle" fontSize="11" fill="#0891b2">rubric + good / bad</text>
            <text x="788" y="486" fontSize="11.5" fill="#155e75">Each stage scored by an</text>
            <text x="788" y="506" fontSize="11.5" fill="#155e75">LLM judge vs a threshold.</text>
            <text x="788" y="536" fontSize="11.5" fill="#155e75">Below the bar → the stage</text>
            <text x="788" y="556" fontSize="11.5" fill="#155e75">auto-regenerates before</text>
            <text x="788" y="576" fontSize="11.5" fill="#155e75">you ever see it.</text>
            {["content", "animation", "mcq", "assessment"].map((id) => (
              <path key={id} d={`M770 ${midY(IDX[id])} L650 ${midY(IDX[id])}`} fill="none"
                    stroke="#67e8f9" strokeWidth="1.4" strokeDasharray="4 4" markerEnd="url(#mk-teal)" />
            ))}
            <text x="700" y="392" fontSize="10.5" fill="#0891b2" textAnchor="middle">scores each</text>
          </g>

          {/* ── per-block container ── */}
          <rect x="322" y={topY(3) - 14} width="356" height={topY(8) + NODE_H + 12 - (topY(3) - 14)}
                rx="16" fill="#faf5ff" stroke="#a78bfa" strokeWidth="1.5" strokeDasharray="7 5" />
          <text x={CX} y={topY(3) - 22} textAnchor="middle" fontSize="12" fontWeight="800" fill="#7c3aed">
            PER BLOCK · runs for every block
          </text>

          {/* ── forward spine arrows (green once the source step is done) ── */}
          {SPINE.slice(0, -1).map((n, i) => {
            const done = stateOf[n.id] === "done";
            return (
              <path key={`e${i}`} d={`M${CX} ${topY(i) + NODE_H} L${CX} ${topY(i + 1)}`} fill="none"
                    stroke={done ? "#16a34a" : "#94a3b8"} strokeWidth={done ? 2.4 : 1.8}
                    markerEnd={`url(#${done ? "mk-green" : "mk-grey"})`} />
            );
          })}

          {/* ── loop-backs on human gates (dashed amber, curving left) ── */}
          {Object.entries(LOOPS).map(([gate, gen]) => {
            const yg = midY(IDX[gate]), yn = midY(IDX[gen]);
            return (
              <g key={`l${gate}`}>
                <path d={`M${X} ${yg} C 300 ${yg}, 300 ${yn}, ${X} ${yn}`} fill="none"
                      stroke="#d97706" strokeWidth="1.6" strokeDasharray="5 4" markerEnd="url(#mk-amber)" />
                <text x="296" y={(yg + yn) / 2 + 4} textAnchor="end" fontSize="10.5" fontWeight="700" fill="#b45309">
                  {LOOP_LABEL[gate]}
                </text>
              </g>
            );
          })}
          {/* final-review in-place refine (small self loop) */}
          <text x="296" y={midY(IDX.finalReview) + 4} textAnchor="end" fontSize="10.5" fontWeight="700" fill="#b45309">↺ improve in place</text>

          {/* ── inputs ── */}
          <g>
            <rect x="300" y="44" width="168" height="54" rx="10" fill="#dbeafe" stroke="#3b82f6" strokeWidth="1.4" />
            <text x="384" y="66" textAnchor="middle" fontSize="13" fontWeight="700" fill="#1e3a8a">Flow A · HTML</text>
            <text x="384" y="84" textAnchor="middle" fontSize="10.5" fill="#1d4ed8">session page</text>
            <rect x="532" y="44" width="168" height="54" rx="10" fill="#dbeafe" stroke="#3b82f6" strokeWidth="1.4" />
            <text x="616" y="66" textAnchor="middle" fontSize="13" fontWeight="700" fill="#1e3a8a">Flow B · PPTX</text>
            <text x="616" y="84" textAnchor="middle" fontSize="10.5" fill="#1d4ed8">text + images</text>
            <path d={`M384 98 L${CX - 12} ${Y0 - 2}`} fill="none" stroke="#94a3b8" strokeWidth="1.6" markerEnd="url(#mk-grey)" />
            <path d={`M616 98 L${CX + 12} ${Y0 - 2}`} fill="none" stroke="#94a3b8" strokeWidth="1.6" markerEnd="url(#mk-grey)" />
          </g>

          {/* ── spine nodes ── */}
          {SPINE.map((n, i) => {
            const st = stateOf[n.id];
            const kind = n.type || KIND[n.id];
            const c = paint(st, n.type);
            const dashed = kind === "human";
            const icon = n.type === "output" ? "🎓" : ICON[n.id];
            return (
              <g key={n.id}>
                <rect x={X} y={topY(i)} width={NODE_W} height={NODE_H} rx="14"
                      fill={c.fill} stroke={c.stroke} strokeWidth={st === "active" || st === "wait" ? 2.6 : 1.8}
                      strokeDasharray={dashed ? "6 5" : "0"} />
                <text x={X + 34} y={midY(i)} textAnchor="middle" dominantBaseline="central" fontSize="22">{icon}</text>
                <text x={X + 62} y={midY(i) - 5} fontSize="15.5" fontWeight="700" fill={c.ink}>{n.t}</text>
                <text x={X + 62} y={midY(i) + 14} fontSize="11.5" fill={c.sub}>{n.s}</text>
                {STATE_TAG[st] && (
                  <text x={X + NODE_W - 14} y={midY(i) - 5} textAnchor="end" fontSize="10" fontWeight="800"
                        letterSpacing="0.5" fill={c.stroke} style={{ textTransform: "uppercase" }}>
                    {STATE_TAG[st]}
                  </text>
                )}
              </g>
            );
          })}

          {/* ── legend ── */}
          <g transform={`translate(40 ${VB_H - 96})`} fontSize="11.5" fill="#475569">
            <rect x="0" y="-12" width="16" height="12" rx="3" fill="#eff6ff" stroke="#2563eb" /><text x="24" y="-2">Automatic step (running)</text>
            <rect x="240" y="-12" width="16" height="12" rx="3" fill="#fffbeb" stroke="#f59e0b" /><text x="264" y="-2">Human gate (your turn)</text>
            <rect x="470" y="-12" width="16" height="12" rx="3" fill="#ecfdf5" stroke="#10b981" /><text x="494" y="-2">Done</text>
            <rect x="590" y="-12" width="16" height="12" rx="3" fill="#dcfce7" stroke="#16a34a" /><text x="614" y="-2">Output</text>
            <line x1="0" y1="20" x2="20" y2="20" stroke="#d97706" strokeWidth="1.7" strokeDasharray="5 4" /><text x="28" y="24">Loop-back (refine)</text>
            <line x1="240" y1="20" x2="260" y2="20" stroke="#c4b5fd" strokeWidth="1.5" strokeDasharray="4 4" /><text x="268" y="24">Memory read / write</text>
            <line x1="470" y1="20" x2="490" y2="20" stroke="#67e8f9" strokeWidth="1.5" strokeDasharray="4 4" /><text x="498" y="24">Eval scoring</text>
          </g>
        </svg>
      </div>
    </div>
  );
}
