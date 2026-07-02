// Renders a block's HTML fragment (or an inline animation) in an isolated, sandboxed iframe so
// its markup/SVG/JS shows faithfully without leaking styles into the app.
export default function Frame({ html, height = 220 }) {
  const doc = `<!doctype html><meta charset="utf-8"><style>
    body{font:14px/1.5 Inter,system-ui,sans-serif;color:#1f2937;margin:12px;}
    h2,h3{font-size:1rem;margin:.4em 0;} img{max-width:100%;} svg{max-width:100%;height:auto;}
    .key-takeaway,.takeaway{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:8px 10px;margin-top:8px;}
  </style>${html || ""}`;
  return (
    <iframe className="frag" style={{ height: `${height}px` }} sandbox="allow-scripts" srcDoc={doc} />
  );
}
