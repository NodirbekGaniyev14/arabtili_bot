import { useEffect, useMemo, useState } from "react";
import { api, type OnboardingPayload, type PlanData } from "../../lib/api";
import {
  DURATIONS,
  FOCUS,
  GOALS,
  LEVELS,
  MINUTES,
  TARGETS,
  formatTargetDate,
  prepareTest,
  type Option,
  type PreparedQuestion,
} from "./data";

type Step =
  | "welcome"
  | "name"
  | "goal"
  | "level"
  | "target"
  | "duration"
  | "focus"
  | "minutes"
  | "test"
  | "loading"
  | "result";

const QUESTION_STEPS: Step[] = [
  "name",
  "goal",
  "level",
  "target",
  "duration",
  "focus",
  "minutes",
];

const LOADING_MESSAGES = [
  "Javoblaringiz tahlil qilinmoqda...",
  "Darajangiz aniqlanmoqda...",
  "Modullar tanlanmoqda...",
  "Jamal rejani yozmoqda... 🐪",
];

interface OnboardingProps {
  initialName: string;
  onDone: (plan: PlanData, name: string) => void;
}

const isArabic = (s: string) => /[؀-ۿ]/.test(s);

/* ── Umumiy kichik komponentlar ── */

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="h-2 rounded-full bg-cardline overflow-hidden">
      <div
        className="h-full rounded-full bg-emerald-deep transition-all duration-500"
        style={{ width: `${Math.round(value * 100)}%` }}
      />
    </div>
  );
}

function TopBar({
  progress,
  onBack,
}: {
  progress: number;
  onBack?: () => void;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-emerald-deep flex items-center justify-center">
            <span className="font-arabic text-lg text-sand leading-none pt-0.5">
              ع
            </span>
          </div>
          <span className="font-extrabold">Arabiy</span>
        </div>
        {onBack && (
          <button
            onClick={onBack}
            className="text-sm font-bold text-ink-soft active:opacity-60"
          >
            ‹ Orqaga
          </button>
        )}
      </div>
      <ProgressBar value={progress} />
    </div>
  );
}

function JamalBubble({ text, hint }: { text: string; hint?: string }) {
  return (
    <div className="mt-6 mb-5">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 shrink-0 rounded-full bg-gold-soft border border-gold/30 flex items-center justify-center text-xl">
          🐪
        </div>
        <div className="rounded-2xl rounded-tl-sm bg-card border border-cardline px-4 py-3 font-bold">
          {text}
        </div>
      </div>
      {hint && (
        <div className="mt-2 pl-[52px] text-sm text-ink-soft font-semibold">
          {hint}
        </div>
      )}
    </div>
  );
}

function OptionCard({
  option,
  selected,
  onClick,
}: {
  option: Option;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 rounded-2xl border p-3.5 mb-3 text-left transition-all active:scale-[0.98] ${
        selected
          ? "bg-emerald-deep/5 border-emerald-deep"
          : "bg-card border-cardline"
      }`}
    >
      <div className="w-10 h-10 shrink-0 rounded-xl bg-gold-soft flex items-center justify-center">
        <span className="font-arabic text-base text-emerald-dark leading-none pt-0.5">
          {option.icon}
        </span>
      </div>
      <span className="flex-1 font-bold text-[15px]">{option.label}</span>
      <span
        className={`w-5 h-5 rounded-full border-2 ${
          selected
            ? "border-emerald-deep bg-emerald-deep"
            : "border-cardline"
        }`}
      />
    </button>
  );
}

/* ── Asosiy oqim ── */

export default function Onboarding({ initialName, onDone }: OnboardingProps) {
  const [step, setStep] = useState<Step>("welcome");
  const [name, setName] = useState(initialName);
  const [goal, setGoal] = useState("");
  const [selfLevel, setSelfLevel] = useState("");
  const [target, setTarget] = useState("");
  const [duration, setDuration] = useState("");
  const [focus, setFocus] = useState<string[]>([]);
  const [minutes, setMinutes] = useState("");

  const [testQs, setTestQs] = useState<PreparedQuestion[]>([]);
  const [testIdx, setTestIdx] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);
  const [testResults, setTestResults] = useState<
    { id: string; tier: string; correct: boolean }[]
  >([]);

  const [plan, setPlan] = useState<PlanData | null>(null);
  const [failed, setFailed] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState(0);

  const tg = window.Telegram?.WebApp;

  const progress = useMemo(() => {
    const total = QUESTION_STEPS.length + 1; // +1 test bosqichi
    const idx = QUESTION_STEPS.indexOf(step as (typeof QUESTION_STEPS)[number]);
    if (step === "welcome") return 0.04;
    if (idx >= 0) return (idx + 1) / (total + 1);
    if (step === "test") {
      const inner = testQs.length ? testIdx / testQs.length : 0;
      return (QUESTION_STEPS.length + inner) / (total + 1);
    }
    return 1;
  }, [step, testIdx, testQs.length]);

  const goBack = () => {
    const idx = QUESTION_STEPS.indexOf(step as (typeof QUESTION_STEPS)[number]);
    if (idx > 0) setStep(QUESTION_STEPS[idx - 1]);
    else if (idx === 0) setStep("welcome");
  };

  const pick = (setter: (v: string) => void, value: string, next: Step) => {
    tg?.HapticFeedback?.impactOccurred("light");
    setter(value);
    setTimeout(() => setStep(next), 180);
  };

  const startTestOrLoading = () => {
    if (selfLevel === "zero") {
      setStep("loading");
    } else {
      setTestQs(prepareTest(selfLevel));
      setTestIdx(0);
      setTestResults([]);
      setStep("test");
    }
  };

  const answerTest = (optionIdx: number) => {
    if (picked !== null) return;
    const q = testQs[testIdx];
    const correct = optionIdx === q.correctIndex;
    setPicked(optionIdx);
    tg?.HapticFeedback?.notificationOccurred(correct ? "success" : "error");
    setTestResults((r) => [...r, { id: q.id, tier: q.tier, correct }]);
    setTimeout(() => {
      setPicked(null);
      if (testIdx + 1 < testQs.length) setTestIdx(testIdx + 1);
      else setStep("loading");
    }, 700);
  };

  // Loading bosqichi: API chaqiruvi + aylanuvchi xabarlar
  useEffect(() => {
    if (step !== "loading") return;

    const msgTimer = setInterval(
      () => setLoadingMsg((m) => (m + 1) % LOADING_MESSAGES.length),
      4000
    );

    const byTier = (tier: string) => {
      const qs = testResults.filter((r) => r.tier === tier);
      return `${qs.filter((r) => r.correct).length}/${qs.length}`;
    };
    const payload: OnboardingPayload = {
      name: name.trim(),
      goal,
      self_level: selfLevel,
      target,
      duration,
      focus,
      daily_minutes: Number(minutes) || 20,
      test:
        selfLevel === "zero"
          ? {}
          : {
              total: testResults.length,
              correct: testResults.filter((r) => r.correct).length,
              by_tier: {
                letters: byTier("letters"),
                words: byTier("words"),
                sentences: byTier("sentences"),
              },
              details: testResults,
            },
    };

    setFailed(false);
    api
      .submitOnboarding(payload)
      .then((res) => {
        setPlan(res.plan);
        setStep("result");
      })
      .catch(() => setFailed(true));

    return () => clearInterval(msgTimer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  /* ── Ekranlar ── */

  if (step === "welcome") {
    return (
      <div className="min-h-screen flex flex-col px-5 pt-5 pb-8 relative z-10">
        <TopBar progress={progress} />
        <div className="flex-1 flex flex-col justify-center gap-5">
          <div className="font-arabic text-[52px] leading-tight text-emerald-deep">
            السَّلامُ عَلَيْكُم
          </div>
          <h1 className="text-2xl font-extrabold leading-snug">
            Salom! Men <span className="text-terracotta">Jamal</span>man.
          </h1>
          <p className="text-ink-soft font-semibold leading-relaxed">
            Shaxsiy arab tili murabbiyingiz. Avval qisqa suhbat — darajangiz,
            maqsadingiz va kuchsiz tomonlaringiz. Keyin sizga aniq reja tuzaman
            va birinchi darsdan boshlaymiz.
          </p>
          <div className="mx-auto w-24 h-24 rounded-full bg-gold-soft border border-gold/30 flex items-center justify-center text-5xl">
            🐪
          </div>
        </div>
        <button
          onClick={() => setStep("name")}
          className="w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg active:scale-[0.98] transition-transform"
        >
          Boshlash
        </button>
      </div>
    );
  }

  if (step === "name") {
    return (
      <div className="min-h-screen flex flex-col px-5 pt-5 pb-8 relative z-10">
        <TopBar progress={progress} onBack={goBack} />
        <JamalBubble text="Sizga qanday murojaat qilay?" />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={32}
          placeholder="Ismingiz"
          className="w-full rounded-2xl border-2 border-emerald-deep/50 bg-card px-4 py-4 text-lg font-bold outline-none focus:border-emerald-deep"
        />
        <button
          onClick={() => name.trim() && setStep("goal")}
          disabled={!name.trim()}
          className="mt-4 w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold disabled:opacity-40 active:scale-[0.98] transition-transform"
        >
          Davom etish
        </button>
      </div>
    );
  }

  const questionScreen = (
    question: string,
    hint: string,
    options: Option[],
    value: string,
    setter: (v: string) => void,
    next: Step
  ) => (
    <div className="min-h-screen px-5 pt-5 pb-8 relative z-10">
      <TopBar progress={progress} onBack={goBack} />
      <JamalBubble text={question} hint={hint} />
      {options.map((o) => (
        <OptionCard
          key={o.id}
          option={o}
          selected={value === o.id}
          onClick={() => pick(setter, o.id, next)}
        />
      ))}
    </div>
  );

  if (step === "goal")
    return questionScreen(
      `${name.trim()}, nima uchun o'rganmoqchisiz?`,
      "Darslar mavzusini belgilaydi.",
      GOALS,
      goal,
      setGoal,
      "level"
    );

  if (step === "level")
    return questionScreen(
      "Hozirgi darajangiz qanday?",
      "Rostini ayting — testda tekshiramiz 😉",
      LEVELS,
      selfLevel,
      setSelfLevel,
      "target"
    );

  if (step === "target")
    return questionScreen(
      "Qaysi darajaga yetmoqchisiz?",
      "Maqsadli nuqtangiz.",
      TARGETS,
      target,
      setTarget,
      "duration"
    );

  if (step === "duration")
    return questionScreen(
      "Qancha muddatda?",
      "Reja tezligini moslayman.",
      DURATIONS,
      duration,
      setDuration,
      "focus"
    );

  if (step === "focus") {
    const toggle = (id: string) => {
      tg?.HapticFeedback?.impactOccurred("light");
      setFocus((f) =>
        f.includes(id) ? f.filter((x) => x !== id) : [...f, id]
      );
    };
    return (
      <div className="min-h-screen px-5 pt-5 pb-8 relative z-10">
        <TopBar progress={progress} onBack={goBack} />
        <JamalBubble
          text="Qaysi tomonlarni kuchaytiramiz?"
          hint="Bir nechtasini tanlang."
        />
        {FOCUS.map((o) => (
          <OptionCard
            key={o.id}
            option={o}
            selected={focus.includes(o.id)}
            onClick={() => toggle(o.id)}
          />
        ))}
        <button
          onClick={() => focus.length && setStep("minutes")}
          disabled={!focus.length}
          className="mt-2 w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold disabled:opacity-40 active:scale-[0.98] transition-transform"
        >
          Davom etish
        </button>
      </div>
    );
  }

  if (step === "minutes")
    return (
      <div className="min-h-screen px-5 pt-5 pb-8 relative z-10">
        <TopBar progress={progress} onBack={goBack} />
        <JamalBubble
          text={`${name.trim()}, kuniga qancha vaqt?`}
          hint="Kam, lekin har kuni — eng yaxshisi."
        />
        {MINUTES.map((o) => (
          <OptionCard
            key={o.id}
            option={o}
            selected={minutes === o.id}
            onClick={() => {
              tg?.HapticFeedback?.impactOccurred("light");
              setMinutes(o.id);
              setTimeout(startTestOrLoading, 180);
            }}
          />
        ))}
      </div>
    );

  if (step === "test") {
    const q = testQs[testIdx];
    if (!q) return null;
    return (
      <div className="min-h-screen px-5 pt-5 pb-8 relative z-10">
        <TopBar progress={progress} />
        <div className="mt-5 text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
          BILIM TESTI · {testIdx + 1}/{testQs.length}
        </div>
        <div className="mt-1 font-bold text-lg">{q.prompt}</div>
        {q.arabic && (
          <div className="my-6 text-center font-arabic text-6xl leading-snug">
            {q.arabic}
          </div>
        )}
        <div className={q.arabic ? "" : "mt-6"}>
          {q.options.map((opt, i) => {
            let cls = "bg-card border-cardline";
            if (picked !== null) {
              if (i === q.correctIndex)
                cls = "bg-emerald-deep/10 border-emerald-deep";
              else if (i === picked)
                cls = "bg-terracotta/10 border-terracotta";
            }
            return (
              <button
                key={i}
                onClick={() => answerTest(i)}
                className={`w-full rounded-2xl border p-4 mb-3 font-bold text-center transition-colors ${cls} ${
                  isArabic(opt) ? "font-arabic text-2xl" : "text-[15px]"
                }`}
              >
                {opt}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  if (step === "loading") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center px-8 text-center relative z-10">
        {failed ? (
          <>
            <div className="text-4xl mb-3">😔</div>
            <h2 className="text-xl font-extrabold mb-2">
              Reja tuzishda xatolik
            </h2>
            <p className="text-sm text-ink-soft font-semibold mb-6">
              Internet aloqasini tekshirib, qayta urinib ko'ring.
            </p>
            <button
              onClick={() => {
                setFailed(false);
                setStep("minutes");
                setTimeout(() => setStep("loading"), 50);
              }}
              className="rounded-2xl bg-emerald-deep px-8 py-3.5 text-white font-extrabold"
            >
              Qayta urinish
            </button>
          </>
        ) : (
          <>
            <div className="flex items-end gap-1.5 h-12 mb-8">
              {["#0E6B4E", "#C9A227", "#C0603D", "#0A4D38"].map((c, i) => (
                <div
                  key={i}
                  className="loading-bar w-2.5 h-full rounded-full"
                  style={{ background: c, animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </div>
            <h2 className="font-arabic text-2xl font-bold mb-2">
              {name.trim()}, reja tuzilmoqda...
            </h2>
            <p className="text-sm text-ink-soft font-semibold">
              {LOADING_MESSAGES[loadingMsg]}
            </p>
          </>
        )}
      </div>
    );
  }

  if (step === "result" && plan) {
    const durationLabel =
      DURATIONS.find((d) => d.id === duration)?.label ?? duration;
    const goalLabel = GOALS.find((g) => g.id === goal)?.label ?? goal;
    return (
      <div className="min-h-screen px-5 pt-5 pb-8 relative z-10">
        <ProgressBar value={1} />
        <h1 className="mt-8 text-center font-arabic text-[26px] font-bold">
          {name.trim()}, rejangiz tayyor 🎉
        </h1>

        {/* Daraja muhri */}
        <div className="mx-auto mt-6 w-44 h-44 -rotate-3 rounded-[28px] bg-gradient-to-br from-emerald-deep to-emerald-dark shadow-xl flex items-center justify-center">
          <div className="w-[164px] h-[164px] rounded-[22px] border-2 border-dashed border-white/30 flex flex-col items-center justify-center gap-1">
            <span className="font-arabic text-xl text-gold-soft">عَرَبِيّ</span>
            <span className="text-5xl font-extrabold text-white">
              {plan.level}
            </span>
            <span className="text-[10px] font-extrabold tracking-[0.2em] text-white/70">
              DARAJA
            </span>
          </div>
        </div>

        <div className="mt-6 text-center font-arabic text-xl font-bold">
          <span className="text-terracotta">{formatTargetDate(plan.target_date)}</span>
          {" gacha "}
          <span className="text-emerald-deep">{plan.target_level}</span>
        </div>
        <div className="mt-1 text-center text-sm text-ink-soft font-semibold">
          {goalLabel} · kuniga {plan.daily_minutes} daqiqa · {durationLabel}
        </div>

        <div className="mt-5 rounded-2xl bg-card border border-cardline p-4">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2">
            NIMA UCHUN {plan.level}?
          </div>
          <p className="text-sm font-semibold leading-relaxed">
            {plan.level_reason}
          </p>
        </div>

        {plan.focus_areas.length > 0 && (
          <div className="mt-4 rounded-2xl bg-card border border-cardline p-4">
            <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2.5">
              KUCHAYTIRADIGAN TOMONLARINGIZ
            </div>
            <div className="flex flex-wrap gap-2">
              {plan.focus_areas.map((f) => (
                <span
                  key={f}
                  className="rounded-full bg-emerald-deep/10 text-emerald-dark px-3 py-1.5 text-xs font-bold"
                >
                  {f}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="mt-4 rounded-2xl bg-gold-soft/60 border border-gold/30 p-4">
          <p className="text-sm font-semibold leading-relaxed">
            🐪 {plan.motivation}
          </p>
        </div>

        <button
          onClick={() => onDone(plan, name.trim())}
          className="mt-6 w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg active:scale-[0.98] transition-transform"
        >
          Birinchi darsni boshlash
        </button>
      </div>
    );
  }

  return null;
}
