/** Javobsiz test savollarining kiritish qismlari (K33): variant, arabcha/lotincha yozish, harakat, so'z tartibi,
 *  «Aytdim». BlindQuiz (imtihon, mini-imtihon, chellenj — natija oxirida) va RunQuiz (dars — javob qulflanib,
 *  to'g'ri javob darhol ochiladi) ikkalasi shularni ishlatadi. Hech biri javobni TEKSHIRMAYDI. */

import { useMemo, useState } from "react";
import type { QuizInput, QuizQuestion } from "../lib/api";
import { playAudio } from "../lib/audio";
import ArabicKeyboard from "./v2/ArabicKeyboard";
import { isArabic } from "./v2/answerCheck";
import { HARAKAT_KEYS, applyMark, hasLookalikes, joinHarakat, splitHarakat, type HarakatSlot } from "./v2/exerciseLogic";

const tg = () => window.Telegram?.WebApp;

export const kindOf = (q: QuizQuestion): QuizInput => q.input ?? (q.options.length ? "options" : "ar");

/* ── Savol turi bo'yicha sarlavha va katta arabcha matn (exercises.tsx renderExercise bilan bir xil) ── */

export function heading(q: QuizQuestion): { prompt: string; big?: string } {
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
  if (q.type === "shadowing") return { prompt: q.q_uz || "Eshiting va ovoz chiqarib takrorlang", big: q.q_ar || undefined };
  return { prompt: q.q_uz || q.q_ar };
}

/* ── Variant tanlash. `reveal` — javob qulflangach to'g'ri/xato variant bo'yaladi ── */

export function Options({
  q,
  onGiven,
  reveal,
}: {
  q: QuizQuestion;
  onGiven: (v: string | null) => void;
  reveal?: { answer: string; given: string };
}) {
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
          let cls = "bg-card border-cardline";
          if (reveal) {
            if (opt === reveal.answer) cls = "bg-emerald-deep/10 border-emerald-deep";
            else if (opt === reveal.given) cls = "bg-terracotta/10 border-terracotta";
          } else if (opt === selected) {
            cls = "bg-gold-soft border-gold ring-2 ring-gold/40";
          }
          return (
            <button
              key={opt}
              disabled={!!reveal}
              onClick={() => {
                setSelected(opt);
                onGiven(opt);
                tg()?.HapticFeedback?.impactOccurred("light");
              }}
              aria-pressed={opt === selected}
              className={`w-full rounded-2xl border p-4 mb-3 font-bold text-center transition-colors disabled:opacity-100 ${cls} ${
                ar ? "font-arabic text-2xl" : "text-[15px]"
              }`}
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

/* ── Yozib javob berish: arab klaviaturasi yoki lotin kiritish ── */

export function Typed({
  arabic,
  onGiven,
  disabled,
}: {
  arabic: boolean;
  onGiven: (v: string | null) => void;
  disabled?: boolean;
}) {
  const [value, setValue] = useState("");
  const set = (v: string) => {
    if (disabled) return;
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
      disabled={disabled}
      autoCapitalize="none"
      autoCorrect="off"
      className="mt-2 w-full min-h-14 rounded-2xl border-2 border-emerald-deep/50 bg-card px-4 py-3 text-xl font-bold outline-none focus:border-emerald-deep disabled:opacity-100"
      placeholder="Javobingiz..."
    />
  );
}

/* ── Harakat qo'yish: harflar tayyor (server `base` beradi), faqat harakat ── */

export function Harakat({
  base,
  onGiven,
  disabled,
}: {
  base: string;
  onGiven: (v: string | null) => void;
  disabled?: boolean;
}) {
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
    if (disabled) return;
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
              onClick={() => !disabled && setSel(i)}
              className={`min-w-12 h-14 px-2 rounded-xl border-2 font-arabic text-3xl leading-none transition-colors ${
                i === sel && !disabled
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
      {!disabled && (
        <>
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
        </>
      )}
    </div>
  );
}

/* ── So'zlarni tartiblash ── */

export function Order({
  words,
  onGiven,
  disabled,
}: {
  words: string[];
  onGiven: (v: string | null) => void;
  disabled?: boolean;
}) {
  const bank = useMemo(() => words.map((w, i) => ({ w, i })), [words]);
  const [chosen, setChosen] = useState<number[]>([]);
  const update = (next: number[]) => {
    if (disabled) return;
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
            disabled={chosen.includes(b.i) || disabled}
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

/* ── «Aytdim» (shadowing): ovoz yozilmaydi — o'quvchining o'zi tasdiqlaydi ── */

export const SELF_DONE = "done";

export function Self({ audio, onConfirm, disabled }: { audio: string; onConfirm: () => void; disabled?: boolean }) {
  return (
    <div className="text-center">
      <button
        onClick={() => playAudio(audio)}
        className="mx-auto mt-4 w-16 h-16 rounded-full bg-emerald-deep text-white text-2xl flex items-center justify-center active:scale-90 transition-transform"
      >
        🔊
      </button>
      <div className="mt-6 grid grid-cols-2 gap-3">
        <button
          onClick={() => playAudio(audio)}
          className="rounded-2xl bg-card border border-cardline py-3.5 font-extrabold"
        >
          🔁 Yana eshitish
        </button>
        <button
          disabled={disabled}
          onClick={() => {
            tg()?.HapticFeedback?.notificationOccurred("success");
            onConfirm();
          }}
          className="rounded-2xl bg-emerald-deep text-white py-3.5 font-extrabold disabled:opacity-40"
        >
          ✓ Aytdim
        </button>
      </div>
    </div>
  );
}
