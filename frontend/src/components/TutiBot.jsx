// The friendly "Tuti" mascot (same bot used in the presentation deck), rebuilt as a React
// component so we can animate its parts — it floats, blinks and its antenna pulses, which
// makes the New-tutorial screen feel alive rather than like a static form.
export default function TutiBot({ size = 132, className = "" }) {
  return (
    <svg
      className={`tutibot ${className}`}
      width={size}
      height={size * (128 / 120)}
      viewBox="0 0 120 128"
      role="img"
      aria-label="Tuti, your tutorial-building assistant"
    >
      {/* ground shadow — squashes as the bot lifts */}
      <ellipse className="tuti-shadow" cx="60" cy="118" rx="34" ry="6" fill="#c7d2fe" opacity=".55" />
      {/* the whole body floats as one group */}
      <g className="tuti-body">
        {/* antenna */}
        <line x1="60" y1="30" x2="60" y2="16" stroke="#7c3aed" strokeWidth="4" strokeLinecap="round" />
        <circle className="tuti-antenna" cx="60" cy="12" r="6" fill="#10b981" />
        {/* head */}
        <rect x="18" y="28" width="84" height="66" rx="22" fill="#ffffff" stroke="#2563eb" strokeWidth="4" />
        <rect x="30" y="44" width="60" height="34" rx="16" fill="#eaf1ff" />
        {/* eyes (blink) */}
        <g className="tuti-eye"><circle cx="47" cy="61" r="7.5" fill="#2563eb" /><circle cx="49" cy="59" r="2.6" fill="#fff" /></g>
        <g className="tuti-eye"><circle cx="73" cy="61" r="7.5" fill="#2563eb" /><circle cx="75" cy="59" r="2.6" fill="#fff" /></g>
        {/* smile + cheeks */}
        <path d="M50 84 Q60 92 70 84" stroke="#7c3aed" strokeWidth="3.4" fill="none" strokeLinecap="round" />
        <circle cx="34" cy="78" r="4.5" fill="#fbcfe8" /><circle cx="86" cy="78" r="4.5" fill="#fbcfe8" />
        {/* body base */}
        <rect x="40" y="98" width="40" height="20" rx="6" fill="#7c3aed" />
        <rect x="45" y="102" width="30" height="4" rx="2" fill="#c4b5fd" />
      </g>
    </svg>
  );
}
