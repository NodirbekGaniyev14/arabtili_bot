/** Javobsiz test yurgizuvchisi (K33): daraja imtihoni, mini-imtihon, haftalik chellenj.
 *
 *  To'g'ri javob mijozga kelmaydi — o'quvchi faqat tanlaydi / yozadi, baholashni server qiladi. Shuning uchun
 *  darsdagidek «to'g'ri/xato» darhol ko'rsatilmaydi: xatolar natija ekranida (`ReviewList`) to'g'ri javob bilan chiqadi.
 *  Har savol turi — exercises.tsx dagi mashq bilan bir xil ko'rinishda, lekin javobni TEKSHIRMAYDI. */

import { useEffect, useMemo, useState } from "react";
import type { QuizInput, QuizQuestion } from "../lib/api";
import { playAudio } from "../lib/audio";
import ArabicKeyboard from "./v2/ArabicKeyboard";
import { isArabic } from "./v2/answerCheck";
import { HARAKAT_KEYS, applyMark, hasLookalikes, joinHarakat, splitHarakat, type HarakatSlot } from "./v2/exerciseLogic";

const tg = () => window.Telegram?.WebApp;

const kindOf = (q: QuizQuestion): QuizInput => q.input ?? (q.options.length ? "options" : "ar");

const NEXT_BTN =
  "mt-3 w-full rounded-2xl bg-emerald-deep py-3.5 text-white font-extrabold disabled:opacity-40 active:scale-[0.98] transition-transform";

/* ── Savol turi bo'yicha sarlavha va katta arabcha matn (exercises.tsx renderExercise bilan bir xil) ── */

function heading(q: QuizQuestion): { prompt: string; big?: string } {
  const kind = kindOf(q);
  if (kind === "options") {
    if (q.type === "match_root") return { prompt: q.q_uz || "Bu so'zning o'zagini toping", big: q.q_ar || undefined };
    if (q.type === "build_word")
      return { prompt: q.q_uz || "O'zak va vazndan so'z yasang", big: `${q.root ?? ""}  +  ${q.pattern ?? ""}` };
    return { prompt: q.q_uz || q.q_ar, big: q.q_uz && isArabic(q.q_ar) ? q.q_ar : undefined };
  }
  if (q.type === "translate_uz_ar") return { prompt: `Arabchaga tarjima qiling: «${q.q_uz}»` };
  if (q.type === "translate_ar_uz") return { prompt: q.q_uz || "O'zbekchaga tarjima qiling", big: q.q_ar || undefined };
  if (q.type === "fill_blank") return { prompt: q.q_uz || "Bo'sh joyni to'ldiring", big: q.q_ar || undefined };
  if (q.type === "dictation") return { prompt: q.q_uz || "Eshiting va yozing" };
  if (q.type === "harakat") return { prompt: q.q_uz || "Harakatlarni qo'ying" };
  if (q.type === "order_words") return { prompt: q.q_uz || "So'zlarni tartiblang" };
  return { prompt: q.q_uz || q.q_ar };
}

/* ── Turlar ── */

function Options({ q, onGiven }: { q: QuizQuestion; onGiven: (v: string | null) => void }) {
  const [selected, setSelected] = useState<string | null>(null);
  const arabicOptions = q.options.some(isArabic);
  return (
    <div>
      {arabicOptions && hasLookalikes(q.options) && (
        <div className="mt-3 rounded-xl border border-gold/40 bg-gold-soft px-3 py-2 text-[12px] font-bold text-ink">
          ⚠️ Ba'zi variantlar faqat harakat bilan farq qiladi — harakatlarga diqqat qiling.
        </div>
      )}
      <div className="mt-3">
        {q.options.map((opt) => {
          const ar = isArabic(opt);
          return (
            <button
              key={opt}
              onClick={() => {
                setSelected(opt);
                onGiven(opt);
                tg()?.HapticFeedback?.impactOccurred("light");
              }}
              aria-pressed={opt === selected}
              className={`w-full rounded-2xl border p-4 mb-3 font-bold text-center transition-colors ${
                opt === selected ? "bg-gold-soft border-gold ring-2 ring-gold/40" : "bg-card border-cardline"
              } ${ar ? "font-arabic text-2xl" : "text-[15px]"}`}
              dir={ar ? "rtl" : "ltr"}
            >
              {opt}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Typed({ arabic, onGiven }: { arabic: boolean; onGiven: (v: string | null) => void }) {
  const [value, setValue] = useState("");
  const set = (v: string) => {
    setValue(v);
    onGiven(v.trim() ? v : null);
  };
  return arabic ? (
    <>
      <div
        dir="rtl"
        className="mt-2 w-full min-h-14 rounded-2xl border-2 border-emerald-deep/50 bg-card px-4 py-3 text-xl font-bold font-arabic flex items-center justify-start"
      >
        {value || (
          <span className="text-ink-soft text-sm font-semibold" dir="ltr">
            Klaviaturadan tering...
          </span>
        )}
      </div>
      <ArabicKeyboard showHarakat={false} onChar={(ch) => set(value + ch)} onBackspace={() => set(value.slice(0, -1))} />
    </>
  ) : (
    <input
      value={value}
      onChange={(e) => set(e.target.value)}
      autoCapitalize="none"
      autoCorrect="off"
      className="mt-2 w-full min-h-14 rounded-2xl border-2 border-emerald-deep/50 bg-card px-4 py-3 text-xl font-bold outline-none focus:border-emerald-deep"
      placeholder="Javobingiz..."
    />
  );
}

function Harakat({ base, onGiven }: { base: string; onGiven: (v: string | null) => void }) {
  const [slots, setSlots] = useState<HarakatSlot[]>(() => splitHarakat(base));
  const isLetter = (i: number) => /[؀-ۿ]/.test(slots[i]?.base ?? "");
  const first = slots.findIndex((_, i) => isLetter(i));
  const [sel, setSel] = useState(first < 0 ? 0 : first);
  const nextLetter = (from: number) => {
    for (let i = from + 1; i < slots.length; i++) if (isLetter(i)) return i;
    return from;
  };
  const update = (next: HarakatSlot[]) => {
    setSlots(next);
    onGiven(next.some((s) => s.marks) ? joinHarakat(next) : null);
  };
  const put = (ch: string) => {
    tg()?.HapticFeedback?.impactOccurred("light");
    update(slots.map((s, i) => (i === sel ? { ...s, marks: applyMark(s.marks, ch) } : s)));
    if (ch !== "ّ") setSel(nextLetter(sel)); // unli qo'yilgach keyingi harfga (shadda — shu harfda qoladi)
  };
  return (
    <div>
      <p className="mt-1 text-[12px] text-ink-soft font-semibold">
        Harfni bosing, keyin harakatni tanlang — harflar tayyor, faqat harakat qo'yiladi.
      </p>
      <div className="my-3 text-center font-arabic text-5xl leading-snug min-h-16" dir="rtl">
        {joinHarakat(slots)}
      </div>
      <div className="flex flex-wrap justify-center gap-1.5" dir="rtl">
        {slots.map((s, i) =>
          isLetter(i) ? (
            <button
              key={i}
              type="button"
              onClick={() => setSel(i)}
              className={`min-w-12 h-14 px-2 rounded-xl border-2 font-arabic text-3xl leading-none transition-colors ${
                i === sel
                  ? "border-emerald-deep bg-emerald-deep/10"
                  : s.marks
                    ? "border-cardline bg-card"
                    : "border-dashed border-cardline bg-card"
              }`}
            >
              {s.base + s.marks}
            </button>
          ) : (
            <span key={i} className="w-4" />
          )
        )}
      </div>
      <div className="mt-3 grid grid-cols-8 gap-1" dir="rtl">
        {HARAKAT_KEYS.map((h) => (
          <button
            key={h.ch}
            type="button"
            title={h.title}
            onClick={() => put(h.ch)}
            className="h-12 rounded-xl bg-gold-soft border border-gold/30 font-arabic text-2xl leading-none active:scale-95"
          >
            {h.label}
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={() => update(slots.map((s, i) => (i === sel ? { ...s, marks: "" } : s)))}
        className="mt-1.5 w-full h-9 rounded-xl bg-terracotta/10 border border-terracotta/40 text-xs font-extrabold text-ink-soft active:scale-95"
      >
        ✕ Tanlangan harfdan harakatni olib tashlash
      </button>
    </div>
  );
}

function Order({ words, onGiven }: { words: string[]; onGiven: (v: string | null) => void }) {
  const bank = useMemo(() => words.map((w, i) => ({ w, i })), [words]);
  const [chosen, setChosen] = useState<number[]>([]);
  const update = (next: number[]) => {
    setChosen(next);
    onGiven(next.length ? next.map((i) => bank[i].w).join(" ") : null);
  };
  return (
    <div>
      <div
        className="mt-4 min-h-16 rounded-2xl border-2 border-dashed border-cardline bg-card/50 p-3 flex flex-wrap gap-2 items-center justify-center"
        dir="rtl"
      >
        {chosen.map((i) => (
          <button
            key={i}
            onClick={() => update(chosen.filter((x) => x !== i))}
            className="rounded-xl bg-emerald-deep text-white px-3 py-2 font-arabic text-xl"
          >
            {bank[i].w}
          </button>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-2 justify-center" dir="rtl">
        {bank.map((b) => (
          <button
            key={b.i}
            disabled={chosen.includes(b.i)}
            onClick={() => update([...chosen, b.i])}
            className={`rounded-xl border px-3 py-2 font-arabic text-xl ${
              chosen.includes(b.i) ? "opacity-25 bg-cardline border-cardline" : "bg-card border-cardline"
            }`}
          >
            {b.w}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── Yurgizuvchi ── */

export default function BlindQuiz({
  items,
  label,
  autoplayAudio = false,
  onAnswer,
  onFinish,
}: {
  items: QuizQuestion[];
  label: string;
  /** Tinglash bo'limi: audio savol ko'ringanda o'zi chalinadi (diktant doim shunday) */
  autoplayAudio?: boolean;
  /** Har savoldan keyin darhol — vaqt tugab qolsa ham javoblar yo'qolmasin */
  onAnswer: (index: number, given: string) => void;
  onFinish: () => void;
}) {
  const [idx, setIdx] = useState(0);
  const [given, setGiven] = useState<string | null>(null);
  const q = items[idx];

  useEffect(() => {
    if (q?.audio && (autoplayAudio || q.type === "dictation")) playAudio(q.audio);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx]);

  if (!q) return null;
  const kind = kindOf(q);
  const { prompt, big } = heading(q);
  const last = idx + 1 >= items.length;

  const next = () => {
    onAnswer(idx, given ?? "");
    tg()?.HapticFeedback?.impactOccurred("light");
    setGiven(null);
    if (last) onFinish();
    else setIdx(idx + 1);
  };

  return (
    <div>
      <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-1">
        {label} · {idx + 1}/{items.length}
      </div>
      <div className="font-bold text-lg">{prompt}</div>
      {big && (
        <div className="my-5 text-center font-arabic text-5xl leading-snug" dir="rtl">
          {big}
        </div>
      )}
      {q.audio && (
        <button
          onClick={() => playAudio(q.audio)}
          className="mx-auto my-4 w-14 h-14 rounded-full bg-emerald-deep text-white text-xl flex items-center justify-center active:scale-90 transition-transform"
        >
          🔊
        </button>
      )}

      {/* key — har savolda holat (tanlov, terilgan matn) yangidan boshlanadi */}
      {kind === "options" && <Options key={idx} q={q} onGiven={setGiven} />}
      {(kind === "ar" || kind === "lat") && <Typed key={idx} arabic={kind === "ar"} onGiven={setGiven} />}
      {kind === "harakat" && <Harakat key={idx} base={q.base ?? ""} onGiven={setGiven} />}
      {kind === "order" && <Order key={idx} words={q.words ?? []} onGiven={setGiven} />}

      <button onClick={next} disabled={given === null} className={NEXT_BTN}>
        {last ? "Yakunlash" : "Keyingi"}
      </button>
    </div>
  );
}
