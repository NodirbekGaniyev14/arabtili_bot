interface XPRingProps {
  value: number;
  goal: number;
  size?: number;
}

/** Kunlik XP progress halqasi */
export default function XPRing({ value, goal, size = 88 }: XPRingProps) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const pct = goal > 0 ? Math.min(value / goal, 1) : 0;
  const done = pct >= 1;

  return (
    <svg width={size} height={size} viewBox="0 0 88 88">
      <circle
        cx="44"
        cy="44"
        r={r}
        fill="none"
        stroke="var(--color-cardline)"
        strokeWidth="9"
      />
      <circle
        cx="44"
        cy="44"
        r={r}
        fill="none"
        stroke={done ? "var(--color-gold)" : "var(--color-emerald-deep)"}
        strokeWidth="9"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - pct)}
        transform="rotate(-90 44 44)"
        style={{ transition: "stroke-dashoffset 0.6s ease" }}
      />
      <text
        x="44"
        y="42"
        textAnchor="middle"
        fontSize="22"
        fontWeight="800"
        fill="var(--color-ink)"
      >
        {value}
      </text>
      <text
        x="44"
        y="58"
        textAnchor="middle"
        fontSize="11"
        fontWeight="600"
        fill="var(--color-ink-soft)"
      >
        /{goal} XP
      </text>
    </svg>
  );
}
