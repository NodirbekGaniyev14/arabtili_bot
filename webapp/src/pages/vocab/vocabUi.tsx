/** Lug'at 2.0 (K24) — umumiy UI: daraja ranglari, audio tugmasi, misolda so'zni ajratish, progress. */

import { useEffect, useState } from "react";
import { playAudioWatch, speakText } from "../../lib/audio";

/** Daraja kartalari — brend yashil tuslari (ikkala mavzuda ham oq matn o'qiladi). */
export const LEVEL_STYLE: Record<string, { from: string; to: string }> = {
  A0: { from: "#3b9b75", to: "#1f7a57" },
  A1: { from: "#228060", to: "#0e6b4e" },
  A2: { from: "#10694d", to: "#0a543e" },
  B1: { from: "#0b5942", to: "#084332" },
  B2: { from: "#083f2f", to: "#052a1f" },
};

export const levelBg = (level: string) => {
  const s = LEVEL_STYLE[level] ?? LEVEL_STYLE.A1;
  return { backgroundImage: `linear-gradient(135deg, ${s.from}, ${s.to})` };
};

export function ProgressBar({
  value,
  max,
  className = "h-1.5 bg-cardline",
  fill = "bg-emerald-deep",
}: {
  value: number;
  max: number;
  className?: string;
  fill?: string;
}) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div className={`w-full rounded-full overflow-hidden ${className}`}>
      <div className={`h-full rounded-full transition-[width] duration-500 ${fill}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

/** So'zni o'qib beradi: mp3 bo'lsa — u, bo'lmasa brauzer TTS. `onEnd` — tugaganda. */
export function playWord(word: { audio?: string; ar: string }, onEnd?: () => void) {
  if (!playAudioWatch(word.audio, () => onEnd?.())) {
    speakText(word.ar);
    if (onEnd) window.setTimeout(onEnd, 1200);
  }
}

/** «🔊 Tinglash» / «🎵 Chalinmoqda» — `auto` bo'lsa karta ochilganda o'zi o'qiydi. */
export function AudioPill({
  word,
  auto = false,
  variant = "solid",
}: {
  word: { audio?: string; ar: string };
  auto?: boolean;
  variant?: "solid" | "soft";
}) {
  const [playing, setPlaying] = useState(false);
  const play = () => {
    setPlaying(true);
    playWord(word, () => setPlaying(false));
  };
  useEffect(() => {
    if (!auto) return;
    const t = window.setTimeout(play, 250);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [word.ar, auto]);
  const cls =
    variant === "solid"
      ? playing
        ? "bg-emerald-deep text-white"
        : "bg-emerald-deep/10 text-emerald-deep"
      : "bg-gold-soft text-ink";
  return (
    <button
      type="button"
      onClick={play}
      className={`inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12px] font-extrabold transition-colors active:scale-95 ${cls}`}
    >
      {playing ? (
        <>
          <span className="inline-flex items-end gap-[2px] h-3">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="loading-bar w-[3px] h-3 rounded-full bg-current"
                style={{ animationDelay: `${i * 0.15}s` }}
              />
            ))}
          </span>
          Chalinmoqda
        </>
      ) : (
        <>🔊 Tinglash</>
      )}
    </button>
  );
}

// ── Misol gapda o'rganilayotgan so'zni ajratish ──

const HARAKAT = /[ً-ْٰـ]/g;
const PUNCT_AR = /[.,،؛:!?؟«»"'()\-—]/g;

const normAr = (s: string) =>
  s.replace(HARAKAT, "").replace(/[أإآٱ]/g, "ا").replace(/ى/g, "ي").replace(/ة/g, "ه").replace(PUNCT_AR, "");

function arStems(word: string): string[] {
  let w = normAr(word).split(" ")[0];
  if (w.startsWith("ال") && w.length > 4) w = w.slice(2);
  const out = [w];
  if (w.endsWith("ه") && w.length > 2) out.push(w.slice(0, -1) + "ت"); // عمه → عمتي
  return out;
}

function arTokenMatches(token: string, stems: string[]): boolean {
  let t = normAr(token);
  if (!t) return false;
  const cands = [t];
  if (t.startsWith("ال")) cands.push(t.slice(2));
  if ("وفبكل".includes(t[0]) && t.length > 3) {
    const rest = t.slice(1);
    cands.push(rest);
    if (rest.startsWith("ال")) cands.push(rest.slice(2));
  }
  return cands.some((c) =>
    stems.some((s) => (s.length <= 2 ? c === s : c === s || (c.startsWith(s) && c.length - s.length <= 3)))
  );
}

export function HighlightAr({ text, word, className = "" }: { text: string; word: string; className?: string }) {
  const stems = arStems(word);
  const parts = text.split(/(\s+)/);
  return (
    <span dir="rtl" className={className}>
      {parts.map((p, i) =>
        /\s+/.test(p) || !arTokenMatches(p, stems) ? (
          <span key={i}>{p}</span>
        ) : (
          <span key={i} className="text-emerald-deep font-bold">
            {p}
          </span>
        )
      )}
    </span>
  );
}

const normUz = (s: string) => s.toLowerCase().replace(/[ʻʼ’‘`]/g, "'").replace(/[.,!?;:«»"()]/g, "");

export function HighlightUz({ text, gloss, className = "" }: { text: string; gloss: string; className?: string }) {
  const first = normUz(gloss.split(/[,;/(]/)[0].trim().split(/\s+/)[0] || "");
  const prefix = first.length >= 3 ? first.slice(0, Math.max(3, first.length - 1)) : "";
  const parts = text.split(/(\s+)/);
  return (
    <span className={className}>
      {parts.map((p, i) =>
        prefix && !/\s+/.test(p) && normUz(p).startsWith(prefix) ? (
          <span key={i} className="text-emerald-deep font-extrabold">
            {p}
          </span>
        ) : (
          <span key={i}>{p}</span>
        )
      )}
    </span>
  );
}

// ── «Davom etish» — oxirgi mavzu (faqat qulaylik, localStorage) ──

const LAST_KEY = "arabiy_vocab_last";

export interface VocabLast {
  level: string;
  topic: string;
  title: string;
}

export function saveLast(v: VocabLast) {
  try {
    localStorage.setItem(LAST_KEY, JSON.stringify(v));
  } catch {
    /* maxfiy rejim — muhim emas */
  }
}

export function loadLast(): VocabLast | null {
  try {
    const raw = localStorage.getItem(LAST_KEY);
    return raw ? (JSON.parse(raw) as VocabLast) : null;
  } catch {
    return null;
  }
}

export const haptic = {
  tap: () => window.Telegram?.WebApp?.HapticFeedback?.impactOccurred("light"),
  ok: () => window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred("success"),
  bad: () => window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred("error"),
};
