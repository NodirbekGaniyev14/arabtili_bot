/** Ekran arab klaviaturasi — dictation/harakat/tarjima mashqlari uchun. */

const ROWS: string[][] = [
  ["ض", "ص", "ث", "ق", "ف", "غ", "ع", "ه", "خ", "ح", "ج"],
  ["ش", "س", "ي", "ب", "ل", "ا", "ت", "ن", "م", "ك", "ط"],
  ["ئ", "ء", "ؤ", "ر", "ى", "ة", "و", "ز", "ظ", "د", "ذ"],
];

const HARAKAT: { ch: string; label: string }[] = [
  { ch: "َ", label: "ـَ" },
  { ch: "ِ", label: "ـِ" },
  { ch: "ُ", label: "ـُ" },
  { ch: "ْ", label: "ـْ" },
  { ch: "ّ", label: "ـّ" },
  { ch: "ً", label: "ـً" },
  { ch: "ٍ", label: "ـٍ" },
  { ch: "ٌ", label: "ـٌ" },
];

interface ArabicKeyboardProps {
  onChar: (ch: string) => void;
  onBackspace: () => void;
  showHarakat?: boolean;
}

export default function ArabicKeyboard({
  onChar,
  onBackspace,
  showHarakat = true,
}: ArabicKeyboardProps) {
  const key =
    "min-w-7 h-9 px-1 rounded-lg bg-card border border-cardline font-arabic text-lg leading-none active:bg-gold-soft";
  return (
    <div className="mt-3 select-none">
      {showHarakat && (
        <div className="flex gap-1 justify-center mb-1.5 flex-wrap" dir="rtl">
          {HARAKAT.map((h) => (
            <button
              key={h.ch}
              type="button"
              onClick={() => onChar(h.ch)}
              className="min-w-8 h-8 px-1 rounded-lg bg-gold-soft border border-gold/30 font-arabic text-base leading-none active:scale-95"
            >
              {h.label}
            </button>
          ))}
        </div>
      )}
      {ROWS.map((row, i) => (
        <div key={i} className="flex gap-1 justify-center mb-1.5" dir="rtl">
          {row.map((ch) => (
            <button key={ch} type="button" onClick={() => onChar(ch)} className={key}>
              {ch}
            </button>
          ))}
        </div>
      ))}
      <div className="flex gap-1 justify-center" dir="rtl">
        {["أ", "إ", "آ"].map((ch) => (
          <button key={ch} type="button" onClick={() => onChar(ch)} className={key}>
            {ch}
          </button>
        ))}
        <button
          type="button"
          onClick={() => onChar(" ")}
          className="h-9 px-10 rounded-lg bg-card border border-cardline text-xs font-bold text-ink-soft active:bg-gold-soft"
        >
          bo'shliq
        </button>
        <button
          type="button"
          onClick={onBackspace}
          className="h-9 px-4 rounded-lg bg-terracotta/10 border border-terracotta/40 text-base active:scale-95"
        >
          ⌫
        </button>
      </div>
    </div>
  );
}
