import { useEffect, useState } from "react";
import { getCourses } from "../api.js";
import TutiBot from "./TutiBot.jsx";

// Persist the typed fields so a page refresh never erases them. (File selections can't be
// restored after a refresh — browser security forbids re-populating <input type=file>.)
const LS_KEY = "tb_upload_form";
const loadSaved = () => {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch { return {}; }
};

// Tuti "speaks" a short guide for whichever field you're on — the mascot is the guide, so we
// don't need static helper paragraphs cluttering the form.
const TIPS = {
  default:      "Hi, I'm Tuti! 👋 Click any field and I'll tell you exactly what goes there.",
  course:       "📚 The course this lesson belongs to. Pick an existing one, or type a new name to start a course.",
  session:      "🏷️ A name for this specific session/lesson — it's how you'll find the tutorial later.",
  file:         "📄 Your source: a .pptx deck or an .html page. This is what I read and convert into the tutorial.",
  objectives:   "🎯 Optional — what should learners be able to do after? Separate a few with commas.",
  material:     "📝 Paste the extra reading or hands-on detail decks usually skip, so the tutorial covers the full lesson.",
  materialFile: "📎 Or upload that reading material as a .md, .txt or .html file instead of pasting.",
  images:       "🖼️ Add diagrams or screenshots (like a workflow diagram) and I'll turn them into clean animations.",
};

export default function UploadCard({ disabled, onStart }) {
  const saved = loadSaved();
  const [file, setFile] = useState(null);
  const [course, setCourse] = useState(saved.course || "");
  const [session, setSession] = useState(saved.session || "");
  const [objectives, setObjectives] = useState(saved.objectives || "");
  const [materialText, setMaterialText] = useState(saved.materialText || "");
  const [materialFile, setMaterialFile] = useState(null);
  const [images, setImages] = useState([]);
  // which field Tuti is currently explaining (drives the speech bubble)
  const [tip, setTip] = useState(TIPS.default);
  const g = (k) => ({ onFocus: () => setTip(TIPS[k]), onBlur: () => setTip(TIPS.default) });

  // Save typed fields on every change so they survive a refresh.
  useEffect(() => {
    localStorage.setItem(LS_KEY, JSON.stringify({ course, session, objectives, materialText }));
  }, [course, session, objectives, materialText]);

  // Existing courses/sessions → pick one, or type a new name.
  const [existing, setExisting] = useState([]);
  useEffect(() => { getCourses().then(setExisting).catch(() => setExisting([])); }, []);
  const courseNames = existing.map((c) => c.name);
  const matchedCourse = existing.find((c) => c.name.toLowerCase() === course.trim().toLowerCase());
  const sessionOptions = matchedCourse ? matchedCourse.sessions
                                       : [...new Set(existing.flatMap((c) => c.sessions))];

  const key = (f) => `${f.name}_${f.size}`;
  const addImages = (e) => {
    const picked = Array.from(e.target.files || []);
    e.target.value = "";                 // reset so re-picking the same file fires onChange…
    if (!picked.length) return;          // …and cancelling (no selection) keeps the current set
    setImages((prev) => {
      const map = new Map(prev.map((f) => [key(f), f]));
      picked.forEach((f) => map.set(key(f), f));  // accumulate across multiple picks, de-duped
      return [...map.values()];
    });
  };
  const removeImage = (k) => setImages((prev) => prev.filter((f) => key(f) !== k));

  const start = () => {
    if (!file) return alert("Choose a session file first.");
    if (!course.trim()) return alert("Enter a course name.");
    if (!session.trim()) return alert("Enter a session name.");
    onStart(
      file,
      {
        course_name: course.trim(),
        session_name: session.trim(),
        learning_objectives: objectives.split(",").map((s) => s.trim()).filter(Boolean),
      },
      { materialText, materialFile, images }
    );
  };

  return (
    <div className="upload-wrap">
      {/* Tuti — OUT of the box, floating above the form (no boundary) */}
      <div className="upload-intro">
        <div className="hero-bot"><TutiBot size={108} /></div>
        <div className="hero-copy">
          <span className="hero-eyebrow">Agentic Tutorial Builder</span>
          <h2>New tutorial</h2>
          {/* Tuti's live guidance — updates to explain whichever field you focus */}
          <div className="tuti-bubble" key={tip}>{tip}</div>
        </div>
      </div>

      {/* ── FORM: clean step sections, inside a card ── */}
      <div className="card upload agentic">
      <div className="upload-body">
      <div className="step-card">
      <div className="up-group-head"><span className="up-step">1</span> Where does it belong?</div>
      <div className="up-grid">
        <label className="field">
          <span><span className="fi">📚</span> Course <em>(pick an existing one or type a new name)</em></span>
          <input type="text" value={course} placeholder="e.g. Introduction to Gen AI" list="course-list"
                 autoComplete="off" {...g("course")} onChange={(e) => setCourse(e.target.value)} />
          <datalist id="course-list">
            {courseNames.map((n) => <option key={n} value={n} />)}
          </datalist>
        </label>
        <label className="field">
          <span><span className="fi">🏷️</span> Session name <em>(pick an existing one or type a new name)</em></span>
          <input type="text" value={session} placeholder="e.g. Building Agents with Memory" list="session-list"
                 autoComplete="off" {...g("session")} onChange={(e) => setSession(e.target.value)} />
          <datalist id="session-list">
            {sessionOptions.map((n) => <option key={n} value={n} />)}
          </datalist>
        </label>
      </div>
      {courseNames.length > 0 && (
        <p className="muted" style={{ marginTop: "-8px", marginBottom: "16px", fontSize: ".85rem" }}>
          {courseNames.length} existing course{courseNames.length === 1 ? "" : "s"} — click a field to choose, or type a new one.
        </p>
      )}
      </div>{/* /step-card 1 */}

      <div className="step-card">
      <div className="up-group-head"><span className="up-step">2</span> The source to convert</div>
      <div className="up-grid">
        <div className="field">
          <span><span className="fi">📄</span> Session file <em>(.pptx or .html — required)</em></span>
          <label className="filepick">
            <span className="filepick-btn">Choose file</span>
            <span className={`filepick-name ${file ? "has" : ""}`}>{file ? `✓ ${file.name}` : "No file chosen yet"}</span>
            <input type="file" accept=".html,.htm,.pptx,.ppt" {...g("file")}
                   onChange={(e) => { const f = e.target.files[0]; if (f) setFile(f); e.target.value = ""; }} />
          </label>
        </div>
        <label className="field">
          <span><span className="fi">🎯</span> Learning objectives <em>(optional, comma-separated)</em></span>
          <input type="text" value={objectives} placeholder="e.g. Explain agent memory, Compare short vs long-term"
                 {...g("objectives")} onChange={(e) => setObjectives(e.target.value)} />
        </label>
      </div>
      </div>{/* /step-card 2 */}

      <div className="step-card">
        <div className="up-group-head"><span className="up-step">3</span> Add-on material <em>(optional but recommended)</em></div>

        <label className="field">
          <span><span className="fi">📝</span> Reading material / hands-on — paste text</span>
          <textarea className="material" value={materialText} {...g("material")} onChange={(e) => setMaterialText(e.target.value)}
                    placeholder="Paste extra explanation, step-by-step hands-on, notes… (Markdown supported)" />
        </label>

        <div className="up-grid">
        <div className="field">
          <span><span className="fi">📎</span> …or upload a material file <em>(.md / .txt / .html)</em></span>
          <label className="filepick">
            <span className="filepick-btn">Choose file</span>
            <span className={`filepick-name ${materialFile ? "has" : ""}`}>{materialFile ? `✓ ${materialFile.name}` : "No file chosen yet"}</span>
            <input type="file" accept=".md,.markdown,.txt,.html,.htm" {...g("materialFile")}
                   onChange={(e) => { const f = e.target.files[0]; if (f) setMaterialFile(f); e.target.value = ""; }} />
          </label>
          {materialFile && (
            <button type="button" className="chip-clear" style={{ marginTop: 8 }} onClick={() => setMaterialFile(null)}>Remove file</button>
          )}
        </div>

        <label className="field">
          <span><span className="fi">🖼️</span> Extra images <em>(diagrams, workflow, screenshots)</em></span>
          <input type="file" accept="image/*" multiple {...g("images")} onChange={addImages} />
          {images.length > 0 ? (
            <div className="chips">
              {images.map((f) => (
                <span className="chip removable" key={key(f)}>
                  {f.name}
                  <button type="button" className="chip-x" title="Remove"
                          onClick={() => removeImage(key(f))}>×</button>
                </span>
              ))}
              <button type="button" className="chip-clear" onClick={() => setImages([])}>Clear all</button>
            </div>
          ) : (
            <p className="field-hint">Pick several at once or one by one — they accumulate here. Click × to remove one.</p>
          )}
        </label>
        </div>{/* /up-grid */}
      </div>{/* /step-card 3 */}

      <div className="actions">
        <button className="cta" disabled={disabled} onClick={start}>
          Start build <span className="cta-arrow">→</span>
        </button>
      </div>
      </div>{/* /upload-body */}
      </div>{/* /card */}
    </div>
  );
}
