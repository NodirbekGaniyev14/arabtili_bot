/** Imtihon savollari (K33): to'g'ri javob mijozga kelmaydi — o'quvchi faqat tanlaydi / yozadi,
 *  baholashni server qiladi. Shuning uchun darsdagidek «to'g'ri/xato» ko'rsatilmaydi (imtihon natijasi
 *  oxirida bo'lim ballari bilan chiqadi). */

import { useEffect, useState } from "react";
import type { ExamQuestion } from "../lib/api";
import { playAudio } from "../lib/audio";
import ArabicKeyboard from "./v2/ArabicKeyboard";
import { isArabic } from "./v2/answerCheck";
import { hasLookalikes } from "./v2/exerciseLogic";

const tg = () => window.Telegram?.WebApp;

export default function ExamQuiz({
  items,
  label,
  onAnswer,
  onFinish,
}: {
  items: ExamQuestion[];
  label: string;
  /** Har savoldan keyin darhol — vaqt tugab qolsa ham javoblar yo'qolmasin */
  onAnswer: (index: number, given: string) => void;
  onFinish: () => void;
}) {
  const [idx, setIdx] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [typed, setTyped] = useState("");

  const item = items[idx];

  useEffect(() => {
    if (item?.audio) playAudio(item.audio);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx]);

  if (!item) return null;

  const hasOptions = item.options.length > 0;
  const value = hasOptions ? selected : typed.trim() || null;
  const last = idx + 1 >= items.length;
  const arabicOptions = item.options.some(isArabic);

  const next = () => {
    onAnswer(idx, value ?? "");
    tg()?.HapticFeedback?.impactOccurred("light");
    setSelected(null);
    setTyped("");
    if (last) onFinish();
    else setIdx(idx + 1);
  };

  const prompt = item.q_uz || item.q_ar;
  const bigArabic = item.q_uz && isArabic(item.q_ar) ? item.q_ar : undefined;

  return (
    <div>
      <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-1">
        {label} · {idx + 1}/{items.length}
      </div>
      <div className="font-bold text-lg">{prompt}</div>
      {bigArabic && (
        <div className="my-5 text-center font-arabic text-5xl leading-snug" dir="rtl">
          {bigArabic}
        </div>
      )}
      {item.audio && (
        <button
          onClick={() => playAudio(item.audio)}
          className="mx-auto my-4 w-14 h-14 rounded-full bg-emerald-deep text-white text-xl flex items-center justify-center active:scale-90 transition-transform"
        >
          🔊
        </button>
      )}

      {hasOptions ? (
        <>
          {arabicOptions && hasLookalikes(item.options) && (
            <div className="mt-3 rounded-xl border border-gold/40 bg-gold-soft px-3 py-2 text-[12px] font-bold text-ink">
              ⚠️ Ba'zi variantlar faqat harakat bilan farq qiladi — harakatlarga diqqat qiling.
            </div>
          )}
          <div className={bigArabic || item.audio ? "" : "mt-5"}>
            {item.options.map((opt) => {
              const ar = isArabic(opt);
              return (
                <button
                  key={opt}
                  onClick={() => {
                    setSelected(opt);
                    tg()?.HapticFeedback?.impactOccurred("light");
                  }}
                  aria-pressed={opt === selected}
                  className={`w-full rounded-2xl border p-4 mb-3 font-bold text-center transition-colors ${
                    opt === selected
                      ? "bg-gold-soft border-gold ring-2 ring-gold/40"
                      : "bg-card border-cardline"
                  } ${ar ? "font-arabic text-2xl" : "text-[15px]"}`}
                  dir={ar ? "rtl" : "ltr"}
                >
                  {opt}
                </button>
              );
            })}
          </div>
        </>
      ) : (
        // Variantsiz savol — diktant: eshitib arabcha yoziladi
        <>
          <div
            dir="rtl"
            className="mt-2 w-full min-h-14 rounded-2xl border-2 border-emerald-deep/50 bg-card px-4 py-3 text-xl font-bold font-arabic flex items-center justify-start"
          >
            {typed || (
              <span className="text-ink-soft text-sm font-semibold" dir="ltr">
                Klaviaturadan tering...
              </span>
            )}
          </div>
          <ArabicKeyboard
            showHarakat={false}
            onChar={(ch) => setTyped((t) => t + ch)}
            onBackspace={() => setTyped((t) => t.slice(0, -1))}
          />
        </>
      )}

      <button
        onClick={next}
        disabled={value === null}
        className="mt-3 w-full rounded-2xl bg-emerald-deep py-3.5 text-white font-extrabold disabled:opacity-40 active:scale-[0.98] transition-transform"
      >
        {last ? "Yakunlash" : "Keyingi"}
      </button>
    </div>
  );
}
