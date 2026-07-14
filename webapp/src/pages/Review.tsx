import { useEffect, useRef, useState } from "react";
import { api, type ReviewCard, type ReviewGrade } from "../lib/api";
import { playAudio } from "../lib/audio";

interface ReviewProps {
  onDone: () => void; // sessiya yakunida statistikani yangilash
}

const KIND_LABEL: Record<string, string> = {
  letter: "HARF",
  word: "SO'Z",
  phrase: "IBORA",
  root: "O'ZAK",
  pattern: "VAZN",
};

const GRADE_BUTTONS: Array<{
  grade: ReviewGrade;
  label: string;
  cls: string;
}> = [
  { grade: "again", label: "Bilmadim", cls: "bg-terracotta" },
  { grade: "hard", label: "Qiyin", cls: "bg-gold" },
  { grade: "good", label: "Bildim", cls: "bg-emerald-deep" },
  { grade: "easy", label: "Oson", cls: "bg-emerald-dark" },
];

const tg = () => window.Telegram?.WebApp;

export default function Review({ onDone }: ReviewProps) {
  const [queue, setQueue] = useState<ReviewCard[] | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [doneCount, setDoneCount] = useState(0);
  const [xp, setXp] = useState(0);
  const [finished, setFinished] = useState(false);
  const [error, setError] = useState(false);
  const busy = useRef(false);

  useEffect(() => {
    api
      .getReview()
      .then((r) => setQueue(r.cards))
      .catch(() => setError(true));
  }, []);

  const current = queue?.[0];

  const reveal = () => {
    setRevealed(true);
    playAudio(current?.audio);
    tg()?.HapticFeedback?.impactOccurred("light");
  };

  const grade = async (g: ReviewGrade) => {
    if (!queue || !current || busy.current) return;
    busy.current = true;
    try {
      const res = await api.answerReview(current.id, g);
      const rest = queue.slice(1);
      if (g === "again") {
        // Bilinmagan karta sessiya oxiriga qaytadi
        setQueue([...rest, current]);
        tg()?.HapticFeedback?.notificationOccurred("error");
      } else {
        setXp((x) => x + res.xp);
        setDoneCount((d) => d + 1);
        tg()?.HapticFeedback?.notificationOccurred("success");
        if (rest.length === 0) {
          setFinished(true);
        }
        setQueue(rest);
      }
      setRevealed(false);
    } catch {
      setError(true);
    } finally {
      busy.current = false;
    }
  };

  /* ── Holatlar ── */

  if (error) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center gap-3 px-8 text-center">
        <div className="text-4xl">😔</div>
        <p className="font-bold">Xatolik yuz berdi. Qayta urinib ko'ring.</p>
      </div>
    );
  }

  if (!queue) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="w-10 h-10 rounded-xl bg-emerald-deep animate-pulse" />
      </div>
    );
  }

  // Sessiya tugadi
  if (finished) {
    return (
      <div className="min-h-[70vh] flex flex-col items-center justify-center gap-3 px-8 text-center">
        <div className="text-6xl">🎉</div>
        <h1 className="text-2xl font-extrabold">Takror tugadi!</h1>
        <p className="text-ink-soft font-semibold">
          {doneCount} ta karta takrorlandi
        </p>
        <div className="mt-2 rounded-2xl bg-gold-soft border border-gold/30 px-8 py-4">
          <span className="text-3xl font-extrabold text-emerald-dark">
            +{xp} XP
          </span>
        </div>
        <button
          onClick={onDone}
          className="mt-6 w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg active:scale-[0.98] transition-transform"
        >
          Yakunlash
        </button>
      </div>
    );
  }

  // Bugunga karta yo'q
  if (!current) {
    return (
      <div className="min-h-[70vh] flex flex-col items-center justify-center gap-3 px-8 text-center">
        <div className="w-20 h-20 rounded-3xl bg-gold-soft flex items-center justify-center">
          <span className="font-arabic text-4xl text-emerald-dark leading-none pt-1">
            كرر
          </span>
        </div>
        <h2 className="text-xl font-extrabold">Bugunga takror yo'q 🎉</h2>
        <p className="text-sm text-ink-soft font-semibold max-w-64">
          Yangi so'zlar darslardan keladi, takrorlash vaqti kelganda shu yerda
          paydo bo'ladi.
        </p>
      </div>
    );
  }

  const total = doneCount + queue.length;
  const progress = total ? doneCount / total : 0;

  return (
    <div className="px-4 pt-4 pb-8 max-w-md mx-auto">
      {/* Progress */}
      <div className="flex items-center gap-3">
        <div className="flex-1 h-2.5 rounded-full bg-cardline overflow-hidden">
          <div
            className="h-full rounded-full bg-emerald-deep transition-all duration-500"
            style={{ width: `${Math.round(progress * 100)}%` }}
          />
        </div>
        <span className="text-xs font-extrabold text-ink-soft">
          {doneCount}/{total}
        </span>
      </div>

      {/* Karta */}
      <div className="mt-6 rounded-3xl bg-card border border-cardline p-8 text-center min-h-72 flex flex-col items-center justify-center">
        <span className="text-[10px] font-extrabold tracking-[0.2em] text-ink-soft">
          {KIND_LABEL[current.kind] ?? "SO'Z"}
        </span>
        <div className="mt-4 font-arabic text-6xl leading-snug" dir="rtl">
          {current.ar}
        </div>

        {revealed && (
          <>
            <div className="mt-5 text-lg font-extrabold text-emerald-deep italic">
              {current.translit}
            </div>
            <div className="mt-1 font-semibold text-ink-soft">{current.uz}</div>
            {current.audio && (
              <button
                onClick={() => playAudio(current.audio)}
                className="mt-4 w-12 h-12 rounded-full bg-emerald-deep text-white text-xl mx-auto flex items-center justify-center active:scale-90 transition-transform"
              >
                🔊
              </button>
            )}
          </>
        )}
      </div>

      {/* Tugmalar */}
      {!revealed ? (
        <button
          onClick={reveal}
          className="mt-6 w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg active:scale-[0.98] transition-transform"
        >
          Javobni ko'rish
        </button>
      ) : (
        <div className="mt-6 grid grid-cols-4 gap-2">
          {GRADE_BUTTONS.map((b) => (
            <button
              key={b.grade}
              onClick={() => grade(b.grade)}
              className={`${b.cls} rounded-xl py-3.5 text-white text-[11px] font-extrabold active:scale-95 transition-transform`}
            >
              {b.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
