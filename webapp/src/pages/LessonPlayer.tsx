import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type CompleteResponse,
  type Exercise,
  type LessonData,
  type Stats,
} from "../lib/api";
import { playAudio } from "../lib/audio";

const isArabic = (s: string) => /[؀-ۿ]/.test(s);
const tg = () => window.Telegram?.WebApp;

interface LessonPlayerProps {
  lessonId: string;
  onClose: () => void;
  onFinish: (stats: Stats) => void;
}

type Phase =
  | { kind: "intro"; idx: number }
  | { kind: "ex"; idx: number }
  | { kind: "result" };

/* ── Umumiy: javob feedback paneli ── */

function Feedback({
  correct,
  correctAnswer,
  onNext,
}: {
  correct: boolean;
  correctAnswer?: string;
  onNext: () => void;
}) {
  return (
    <div
      className={`fixed bottom-0 left-0 right-0 z-40 px-5 pt-4 pb-8 ${
        correct ? "bg-emerald-deep" : "bg-terracotta"
      }`}
    >
      <div className="max-w-md mx-auto">
        <div className="text-white font-extrabold text-lg">
          {correct ? "To'g'ri! 🎉" : "Xato 😔"}
        </div>
        {!correct && correctAnswer && (
          <div
            className={`text-white/90 font-bold mt-1 ${
              isArabic(correctAnswer) ? "font-arabic text-xl" : "text-sm"
            }`}
          >
            To'g'ri javob: {correctAnswer}
          </div>
        )}
        <button
          onClick={onNext}
          className="mt-3 w-full rounded-2xl bg-white py-3.5 font-extrabold text-ink active:scale-[0.98] transition-transform"
        >
          Davom etish
        </button>
      </div>
    </div>
  );
}

/* ── Mashq: tanlash / tinglash ── */

function ChoiceEx({
  ex,
  onDone,
}: {
  ex: Exercise;
  onDone: (ok: boolean) => void;
}) {
  const { options, correctIndex } = useMemo(() => {
    const src = ex.options ?? [];
    const correct = src[0];
    const shuffled = [...src].sort(() => Math.random() - 0.5);
    return { options: shuffled, correctIndex: shuffled.indexOf(correct) };
  }, [ex]);

  const [picked, setPicked] = useState<number | null>(null);

  useEffect(() => {
    if (ex.type === "listen") playAudio(ex.audio);
  }, [ex]);

  const pick = (i: number) => {
    if (picked !== null) return;
    setPicked(i);
    const ok = i === correctIndex;
    tg()?.HapticFeedback?.notificationOccurred(ok ? "success" : "error");
  };

  return (
    <div>
      {ex.arabic && (
        <div className="my-5 text-center font-arabic text-6xl leading-snug">
          {ex.arabic}
        </div>
      )}
      {ex.audio && (
        <button
          onClick={() => playAudio(ex.audio)}
          className="mx-auto my-5 w-16 h-16 rounded-full bg-emerald-deep text-white text-2xl flex items-center justify-center active:scale-90 transition-transform"
        >
          🔊
        </button>
      )}
      <div className={!ex.arabic && !ex.audio ? "mt-6" : ""}>
        {options.map((opt, i) => {
          let cls = "bg-card border-cardline";
          if (picked !== null) {
            if (i === correctIndex)
              cls = "bg-emerald-deep/10 border-emerald-deep";
            else if (i === picked) cls = "bg-terracotta/10 border-terracotta";
          }
          return (
            <button
              key={i}
              onClick={() => pick(i)}
              className={`w-full rounded-2xl border p-4 mb-3 font-bold text-center transition-colors ${cls} ${
                isArabic(opt) ? "font-arabic text-2xl" : "text-[15px]"
              }`}
            >
              {opt}
            </button>
          );
        })}
      </div>
      {picked !== null && (
        <Feedback
          correct={picked === correctIndex}
          correctAnswer={options[correctIndex]}
          onNext={() => onDone(picked === correctIndex)}
        />
      )}
    </div>
  );
}

/* ── Mashq: juftlash ── */

function MatchEx({
  ex,
  onDone,
}: {
  ex: Exercise;
  onDone: (ok: boolean) => void;
}) {
  const pairs = ex.pairs ?? [];
  const left = useMemo(
    () => pairs.map((p, i) => ({ text: p[0], pair: i })).sort(() => Math.random() - 0.5),
    [ex] // eslint-disable-line react-hooks/exhaustive-deps
  );
  const right = useMemo(
    () => pairs.map((p, i) => ({ text: p[1], pair: i })).sort(() => Math.random() - 0.5),
    [ex] // eslint-disable-line react-hooks/exhaustive-deps
  );

  const [selLeft, setSelLeft] = useState<number | null>(null);
  const [selRight, setSelRight] = useState<number | null>(null);
  const [matched, setMatched] = useState<Set<number>>(new Set());
  const [mistakes, setMistakes] = useState(0);
  const [shake, setShake] = useState(false);
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    if (selLeft === null || selRight === null) return;
    if (selLeft === selRight) {
      const next = new Set(matched).add(selLeft);
      setMatched(next);
      tg()?.HapticFeedback?.impactOccurred("light");
      setSelLeft(null);
      setSelRight(null);
      if (next.size === pairs.length) {
        setTimeout(() => setFinished(true), 350);
      }
    } else {
      setMistakes((m) => m + 1);
      setShake(true);
      tg()?.HapticFeedback?.notificationOccurred("error");
      setTimeout(() => {
        setShake(false);
        setSelLeft(null);
        setSelRight(null);
      }, 450);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selLeft, selRight]);

  const btnCls = (pair: number, selected: boolean) => {
    if (matched.has(pair)) return "bg-emerald-deep/10 border-emerald-deep opacity-60";
    if (selected) return shake ? "bg-terracotta/10 border-terracotta" : "bg-gold-soft border-gold";
    return "bg-card border-cardline";
  };

  return (
    <div className="mt-6">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-3">
          {left.map((item) => (
            <button
              key={item.pair}
              disabled={matched.has(item.pair)}
              onClick={() => setSelLeft(item.pair)}
              className={`w-full rounded-2xl border p-3 font-bold transition-colors ${btnCls(item.pair, selLeft === item.pair)} ${
                isArabic(item.text) ? "font-arabic text-xl" : "text-sm"
              }`}
            >
              {item.text}
            </button>
          ))}
        </div>
        <div className="space-y-3">
          {right.map((item) => (
            <button
              key={item.pair}
              disabled={matched.has(item.pair)}
              onClick={() => setSelRight(item.pair)}
              className={`w-full rounded-2xl border p-3 font-bold transition-colors ${btnCls(item.pair, selRight === item.pair)} ${
                isArabic(item.text) ? "font-arabic text-xl" : "text-sm"
              }`}
            >
              {item.text}
            </button>
          ))}
        </div>
      </div>
      {finished && (
        <Feedback correct={mistakes === 0} onNext={() => onDone(mistakes === 0)} />
      )}
    </div>
  );
}

/* ── Mashq: jumla yig'ish ── */

function AssembleEx({
  ex,
  onDone,
}: {
  ex: Exercise;
  onDone: (ok: boolean) => void;
}) {
  const bank = useMemo(
    () =>
      [...(ex.words ?? []), ...(ex.extra ?? [])]
        .map((w, i) => ({ w, i }))
        .sort(() => Math.random() - 0.5),
    [ex]
  );
  const [chosen, setChosen] = useState<number[]>([]);
  const [checked, setChecked] = useState<boolean | null>(null);

  useEffect(() => {
    playAudio(ex.audio);
  }, [ex]);

  const answer = chosen.map((i) => bank.find((b) => b.i === i)!.w);
  const correctText = (ex.words ?? []).join(" ");

  const check = () => {
    const ok = answer.join(" ") === correctText;
    setChecked(ok);
    tg()?.HapticFeedback?.notificationOccurred(ok ? "success" : "error");
  };

  return (
    <div className="mt-4">
      {/* Javob chizig'i */}
      <div className="min-h-16 rounded-2xl border-2 border-dashed border-cardline bg-card/50 p-3 flex flex-wrap gap-2 items-center justify-center" dir="rtl">
        {answer.length === 0 && (
          <span className="text-ink-soft text-sm font-semibold" dir="ltr">
            So'zlarni tartib bilan tanlang
          </span>
        )}
        {chosen.map((bankIdx) => {
          const item = bank.find((b) => b.i === bankIdx)!;
          return (
            <button
              key={bankIdx}
              onClick={() =>
                checked === null &&
                setChosen((c) => c.filter((x) => x !== bankIdx))
              }
              className="rounded-xl bg-emerald-deep text-white px-3 py-2 font-arabic text-xl"
            >
              {item.w}
            </button>
          );
        })}
      </div>

      {/* So'zlar banki */}
      <div className="mt-4 flex flex-wrap gap-2 justify-center" dir="rtl">
        {bank.map((item) => {
          const used = chosen.includes(item.i);
          return (
            <button
              key={item.i}
              disabled={used || checked !== null}
              onClick={() => setChosen((c) => [...c, item.i])}
              className={`rounded-xl border px-3 py-2 font-arabic text-xl transition-opacity ${
                used
                  ? "opacity-25 bg-cardline border-cardline"
                  : "bg-card border-cardline"
              }`}
            >
              {item.w}
            </button>
          );
        })}
      </div>

      {checked === null && (
        <button
          onClick={check}
          disabled={chosen.length === 0}
          className="mt-6 w-full rounded-2xl bg-emerald-deep py-3.5 text-white font-extrabold disabled:opacity-40 active:scale-[0.98] transition-transform"
        >
          Tekshirish
        </button>
      )}

      {checked !== null && (
        <Feedback
          correct={checked}
          correctAnswer={correctText}
          onNext={() => onDone(checked)}
        />
      )}
    </div>
  );
}

/* ── Mashq: yozish (lotin translit) ── */

const normalize = (s: string) =>
  s
    .toLowerCase()
    .replace(/[''ʼ’`\-_.]/g, "")
    .replace(/\s+/g, " ")
    .trim();

function TypeEx({
  ex,
  onDone,
}: {
  ex: Exercise;
  onDone: (ok: boolean) => void;
}) {
  const [value, setValue] = useState("");
  const [checked, setChecked] = useState<boolean | null>(null);

  useEffect(() => {
    playAudio(ex.audio);
  }, [ex]);

  const check = () => {
    const ok = (ex.answers ?? []).some(
      (a) => normalize(a) === normalize(value)
    );
    setChecked(ok);
    tg()?.HapticFeedback?.notificationOccurred(ok ? "success" : "error");
  };

  return (
    <div>
      {ex.arabic && (
        <div className="my-5 text-center font-arabic text-6xl leading-snug">
          {ex.arabic}
        </div>
      )}
      {ex.audio && (
        <button
          onClick={() => playAudio(ex.audio)}
          className="mx-auto mb-4 w-12 h-12 rounded-full bg-emerald-deep text-white text-xl flex items-center justify-center active:scale-90 transition-transform"
        >
          🔊
        </button>
      )}
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={checked !== null}
        placeholder="Javobingiz..."
        autoCapitalize="none"
        autoCorrect="off"
        className="w-full rounded-2xl border-2 border-emerald-deep/50 bg-card px-4 py-4 text-lg font-bold outline-none focus:border-emerald-deep"
      />
      {checked === null && (
        <button
          onClick={check}
          disabled={!value.trim()}
          className="mt-4 w-full rounded-2xl bg-emerald-deep py-3.5 text-white font-extrabold disabled:opacity-40 active:scale-[0.98] transition-transform"
        >
          Tekshirish
        </button>
      )}
      {checked !== null && (
        <Feedback
          correct={checked}
          correctAnswer={(ex.answers ?? [])[0]}
          onNext={() => onDone(checked)}
        />
      )}
    </div>
  );
}

/* ── Asosiy player ── */

const KIND_LABEL = { letter: "YANGI HARF", word: "YANGI SO'Z", phrase: "YANGI IBORA" };

export default function LessonPlayer({
  lessonId,
  onClose,
  onFinish,
}: LessonPlayerProps) {
  const [lesson, setLesson] = useState<LessonData | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "intro", idx: 0 });
  const [results, setResults] = useState<boolean[]>([]);
  const [reward, setReward] = useState<CompleteResponse | null>(null);
  const [error, setError] = useState(false);
  const submitted = useRef(false);

  useEffect(() => {
    api.getLesson(lessonId).then(setLesson).catch(() => setError(true));
  }, [lessonId]);

  // Intro kartada audio avtomatik
  useEffect(() => {
    if (lesson && phase.kind === "intro") {
      playAudio(lesson.new_items[phase.idx]?.audio);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lesson, phase]);

  // Natijani serverga yuborish (submitted ref — StrictMode'da ikki marta ketmasin)
  useEffect(() => {
    if (phase.kind !== "result" || !lesson || reward || submitted.current) return;
    submitted.current = true;
    const correct = results.filter(Boolean).length;
    api
      .completeLesson(lesson.id, correct, lesson.exercises.length)
      .then(setReward)
      .catch(() => setError(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase]);

  if (error) {
    return (
      <Overlay>
        <div className="min-h-screen flex flex-col items-center justify-center gap-4 px-8 text-center">
          <div className="text-4xl">😔</div>
          <p className="font-bold">Xatolik yuz berdi. Qayta urinib ko'ring.</p>
          <button
            onClick={onClose}
            className="rounded-2xl bg-emerald-deep px-8 py-3 text-white font-extrabold"
          >
            Yopish
          </button>
        </div>
      </Overlay>
    );
  }

  if (!lesson) {
    return (
      <Overlay>
        <div className="min-h-screen flex items-center justify-center">
          <div className="w-10 h-10 rounded-xl bg-emerald-deep animate-pulse" />
        </div>
      </Overlay>
    );
  }

  const introCount = lesson.new_items.length;
  const exCount = lesson.exercises.length;
  const stepsDone =
    phase.kind === "intro"
      ? phase.idx
      : phase.kind === "ex"
        ? introCount + phase.idx
        : introCount + exCount;
  const progress = stepsDone / (introCount + exCount);

  const nextFromIntro = () => {
    if (phase.kind !== "intro") return;
    if (phase.idx + 1 < introCount) setPhase({ kind: "intro", idx: phase.idx + 1 });
    else setPhase({ kind: "ex", idx: 0 });
  };

  const exDone = (ok: boolean) => {
    if (phase.kind !== "ex") return;
    setResults((r) => [...r, ok]);
    if (phase.idx + 1 < exCount) setPhase({ kind: "ex", idx: phase.idx + 1 });
    else setPhase({ kind: "result" });
  };

  return (
    <Overlay>
      <div className="max-w-md mx-auto px-5 pt-5 pb-32">
        {/* Yuqori panel */}
        {phase.kind !== "result" && (
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="text-2xl text-ink-soft font-bold leading-none active:opacity-60"
            >
              ✕
            </button>
            <div className="flex-1">
              <div className="h-2.5 rounded-full bg-cardline overflow-hidden">
                <div
                  className="h-full rounded-full bg-emerald-deep transition-all duration-500"
                  style={{ width: `${Math.round(progress * 100)}%` }}
                />
              </div>
            </div>
          </div>
        )}

        {/* Yangi element kartasi */}
        {phase.kind === "intro" && (
          <div className="mt-8 text-center">
            <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
              {KIND_LABEL[lesson.new_items[phase.idx].kind]} · {phase.idx + 1}/
              {introCount}
            </div>
            <div className="mt-6 rounded-3xl bg-card border border-cardline p-8">
              <div className="font-arabic text-7xl leading-tight">
                {lesson.new_items[phase.idx].ar}
              </div>
              <div className="mt-4 text-lg font-extrabold text-emerald-deep italic">
                {lesson.new_items[phase.idx].translit}
              </div>
              <div className="mt-1 font-semibold text-ink-soft">
                {lesson.new_items[phase.idx].uz}
              </div>
              {lesson.new_items[phase.idx].audio && (
                <button
                  onClick={() => playAudio(lesson.new_items[phase.idx].audio)}
                  className="mt-5 w-14 h-14 rounded-full bg-emerald-deep text-white text-xl mx-auto flex items-center justify-center active:scale-90 transition-transform"
                >
                  🔊
                </button>
              )}
            </div>
            <button
              onClick={nextFromIntro}
              className="mt-6 w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg active:scale-[0.98] transition-transform"
            >
              {phase.idx + 1 < introCount ? "Keyingi" : "Mashqlarga o'tish"}
            </button>
          </div>
        )}

        {/* Mashqlar */}
        {phase.kind === "ex" && (
          <div className="mt-6">
            <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
              MASHQ · {phase.idx + 1}/{exCount}
            </div>
            <div className="mt-1 font-bold text-lg">
              {lesson.exercises[phase.idx].prompt}
            </div>
            {(() => {
              const ex = lesson.exercises[phase.idx];
              const key = `${lesson.id}-${phase.idx}`;
              switch (ex.type) {
                case "choice":
                case "listen":
                  return <ChoiceEx key={key} ex={ex} onDone={exDone} />;
                case "match":
                  return <MatchEx key={key} ex={ex} onDone={exDone} />;
                case "assemble":
                  return <AssembleEx key={key} ex={ex} onDone={exDone} />;
                case "type":
                  return <TypeEx key={key} ex={ex} onDone={exDone} />;
                default:
                  return null;
              }
            })()}
          </div>
        )}

        {/* Natija */}
        {phase.kind === "result" && (
          <div className="min-h-[80vh] flex flex-col items-center justify-center text-center gap-3">
            <div className="text-6xl">
              {reward?.perfect ? "🌟" : "🎉"}
            </div>
            <h1 className="text-2xl font-extrabold">
              {reward?.perfect ? "Mukammal!" : "Dars tugadi!"}
            </h1>
            <p className="text-ink-soft font-semibold">
              {results.filter(Boolean).length}/{exCount} to'g'ri javob
            </p>
            {reward ? (
              <>
                <div className="mt-2 rounded-2xl bg-gold-soft border border-gold/30 px-8 py-4">
                  <span className="text-3xl font-extrabold text-emerald-dark">
                    +{reward.xp_earned} XP
                  </span>
                </div>

                {reward.new_badges.length > 0 && (
                  <div className="mt-4 w-full space-y-2">
                    <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
                      YANGI YUTUQ!
                    </div>
                    {reward.new_badges.map((b) => (
                      <div
                        key={b.id}
                        className="flex items-center gap-3 rounded-2xl bg-card border border-gold/40 p-3 text-left animate-pulse"
                      >
                        <span className="text-3xl">{b.icon}</span>
                        <div>
                          <div className="font-extrabold text-[15px]">
                            {b.title}
                          </div>
                          <div className="text-xs text-ink-soft font-semibold">
                            {b.desc}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <button
                  onClick={() => onFinish(reward.stats)}
                  className="mt-6 w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg active:scale-[0.98] transition-transform"
                >
                  Davom etish
                </button>
              </>
            ) : (
              <div className="mt-4 w-8 h-8 rounded-lg bg-emerald-deep animate-pulse" />
            )}
          </div>
        )}
      </div>
    </Overlay>
  );
}

function Overlay({ children }: { children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-30 bg-sand overflow-y-auto">{children}</div>
  );
}
