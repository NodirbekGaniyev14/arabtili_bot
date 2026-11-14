/** Javobsiz test yurgizuvchisi (K33): daraja imtihoni, mini-imtihon, haftalik chellenj.
 *
 *  To'g'ri javob mijozga kelmaydi — o'quvchi faqat tanlaydi / yozadi, baholashni server qiladi. Shuning uchun
 *  darsdagidek «to'g'ri/xato» darhol ko'rsatilmaydi: xatolar natija ekranida (`ReviewList`) to'g'ri javob bilan chiqadi.
 *  (Dars testi — RunQuiz: u har javobni qulflab, to'g'ri javobni darhol ochadi.) */

import { useEffect, useState } from "react";
import type { QuizQuestion } from "../lib/api";
import { playAudio } from "../lib/audio";
import { Harakat, Options, Order, SELF_DONE, Self, Typed, heading, kindOf } from "./quizInputs";

const tg = () => window.Telegram?.WebApp;

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
      {q.audio && kind !== "self" && (
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
      {kind === "self" && <Self key={idx} audio={q.audio} onConfirm={() => setGiven(SELF_DONE)} disabled={given !== null} />}

      <button
        onClick={next}
        disabled={given === null}
        className="mt-3 w-full rounded-2xl bg-emerald-deep py-3.5 text-white font-extrabold disabled:opacity-40 active:scale-[0.98] transition-transform"
      >
        {last ? "Yakunlash" : "Keyingi"}
      </button>
    </div>
  );
}
