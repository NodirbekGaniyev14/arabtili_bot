/** v2 mashq dvigateli — 10 tur (spec §11) + QuizRunner.
 * Har mashq onDone(ok) chaqiradi; QuizRunner xato so'zlarni yig'adi (SRS reset uchun).
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type { MicroTestItem } from "../../lib/api";
import { playAudio } from "../../lib/audio";
import ArabicKeyboard from "./ArabicKeyboard";
import { stripHarakat } from "./ArabicText";

const tg = () => window.Telegram?.WebApp;
const isArabic = (s: string) => /[؀-ۿ]/.test(s);

/** Alif variantlari (أ إ آ ٱ) → ا: klaviaturada yakka hamzali alif teriladi,
 * hamza imlosi esa yuqori darajalarda o'rgatiladi — shuning uchun tenglashtiramiz. */
const normAr = (s: string) =>
  stripHarakat(s)
    .replace(/ـ/g, "")
    .replace(/[أإآٱ]/g, "ا")
    .replace(/[.,؟!·:؛\s]+/g, " ")
    .trim();

const normLat = (s: string) =>
  s.toLowerCase().replace(/[''ʼ’`\-_.]/g, "").replace(/\s+/g, " ").trim();

/** "qalam / ruchka" yoki "ta'til, ruxsat" kabi javoblarda BITTA variant yetarli. */
const latOk = (answer: string, value: string) => {
  const nv = normLat(value);
  if (!nv) return false;
  const variants = answer
    .replace(/\(.*?\)/g, " ")
    .split(/\s*(?:\/|,|;|\byoki\b)\s*/)
    .map(normLat)
    .filter(Boolean);
  return variants.length ? variants.includes(nv) : nv === normLat(answer);
};

/** harakat mashqi: harakatlar solishtiriladi, lekin alif varianti va bo'shliq farqi kechiriladi. */
const harakatNorm = (s: string) =>
  s.replace(/\s+/g, "").replace(/ـ/g, "").replace(/[أإآٱ]/g, "ا");

/* ── Umumiy feedback paneli ── */

function Feedback({
  correct,
  correctAnswer,
  explain,
  onNext,
}: {
  correct: boolean;
  correctAnswer?: string;
  explain?: string;
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
            className={`text-white/95 font-bold mt-1 ${
              isArabic(correctAnswer) ? "font-arabic text-2xl" : "text-sm"
            }`}
            dir={isArabic(correctAnswer) ? "rtl" : "ltr"}
          >
            To'g'ri javob: {correctAnswer}
          </div>
        )}
        {explain && (
          <div className="text-white/80 text-xs font-semibold mt-1.5 leading-relaxed">
            {explain}
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

/* ── Variantli mashq (mcq / match_root / build_word asosi) ── */

function OptionsEx({
  prompt,
  arabicBig,
  audio,
  options,
  answer,
  explain,
  arabicOptions,
  onDone,
}: {
  prompt: string;
  arabicBig?: string;
  audio?: string;
  options: string[];
  answer: string;
  explain?: string;
  arabicOptions?: boolean;
  onDone: (ok: boolean) => void;
}) {
  const shuffled = useMemo(
    () => [...options].sort(() => Math.random() - 0.5),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [options.join("|")]
  );
  const [picked, setPicked] = useState<string | null>(null);

  const pick = (opt: string) => {
    if (picked !== null) return;
    setPicked(opt);
    tg()?.HapticFeedback?.notificationOccurred(opt === answer ? "success" : "error");
  };

  return (
    <div>
      <div className="font-bold text-lg">{prompt}</div>
      {arabicBig && (
        <div className="my-5 text-center font-arabic text-5xl leading-snug" dir="rtl">
          {arabicBig}
        </div>
      )}
      {audio && (
        <button
          onClick={() => playAudio(audio)}
          className="mx-auto my-4 w-14 h-14 rounded-full bg-emerald-deep text-white text-xl flex items-center justify-center active:scale-90 transition-transform"
        >
          🔊
        </button>
      )}
      <div className={arabicBig || audio ? "" : "mt-5"}>
        {shuffled.map((opt) => {
          let cls = "bg-card border-cardline";
          if (picked !== null) {
            if (opt === answer) cls = "bg-emerald-deep/10 border-emerald-deep";
            else if (opt === picked) cls = "bg-terracotta/10 border-terracotta";
          }
          const ar = arabicOptions ?? isArabic(opt);
          return (
            <button
              key={opt}
              onClick={() => pick(opt)}
              className={`w-full rounded-2xl border p-4 mb-3 font-bold text-center transition-colors ${cls} ${
                ar ? "font-arabic text-2xl" : "text-[15px]"
              }`}
              dir={ar ? "rtl" : "ltr"}
            >
              {opt}
            </button>
          );
        })}
      </div>
      {picked !== null && (
        <Feedback
          correct={picked === answer}
          correctAnswer={answer}
          explain={explain}
          onNext={() => onDone(picked === answer)}
        />
      )}
    </div>
  );
}

/* ── Yozib javob berish (fill_blank / translate / dictation / harakat) ── */

function InputEx({
  prompt,
  arabicBig,
  audio,
  autoplay,
  arabicInput,
  showHarakatKeys,
  check,
  correctAnswer,
  explain,
  onDone,
}: {
  prompt: string;
  arabicBig?: string;
  audio?: string;
  autoplay?: boolean;
  arabicInput: boolean;
  showHarakatKeys?: boolean;
  check: (value: string) => boolean;
  correctAnswer: string;
  explain?: string;
  onDone: (ok: boolean) => void;
}) {
  const [value, setValue] = useState("");
  const [checked, setChecked] = useState<boolean | null>(null);

  useEffect(() => {
    if (autoplay) playAudio(audio);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = () => {
    const ok = check(value);
    setChecked(ok);
    tg()?.HapticFeedback?.notificationOccurred(ok ? "success" : "error");
  };

  return (
    <div>
      <div className="font-bold text-lg">{prompt}</div>
      {arabicBig && (
        <div className="my-4 text-center font-arabic text-5xl leading-snug" dir="rtl">
          {arabicBig}
        </div>
      )}
      {audio && (
        <button
          onClick={() => playAudio(audio)}
          className="mx-auto my-3 w-12 h-12 rounded-full bg-emerald-deep text-white text-lg flex items-center justify-center active:scale-90 transition-transform"
        >
          🔊
        </button>
      )}
      <div
        dir={arabicInput ? "rtl" : "ltr"}
        className={`mt-2 w-full min-h-14 rounded-2xl border-2 border-emerald-deep/50 bg-card px-4 py-3 text-xl font-bold flex items-center ${
          arabicInput ? "font-arabic justify-start" : ""
        }`}
      >
        {value || (
          <span className="text-ink-soft text-sm font-semibold" dir="ltr">
            {arabicInput ? "Klaviaturadan tering..." : "Javobingiz..."}
          </span>
        )}
      </div>

      {arabicInput ? (
        <ArabicKeyboard
          onChar={(ch) => checked === null && setValue((v) => v + ch)}
          onBackspace={() => checked === null && setValue((v) => v.slice(0, -1))}
          showHarakat={showHarakatKeys}
        />
      ) : (
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={checked !== null}
          autoCapitalize="none"
          autoCorrect="off"
          className="mt-2 w-full rounded-2xl border border-cardline bg-card px-4 py-3 font-bold outline-none focus:border-emerald-deep"
          placeholder="Lotin harflarida yozing"
        />
      )}

      {checked === null && (
        <button
          onClick={submit}
          disabled={!value.trim()}
          className="mt-4 w-full rounded-2xl bg-emerald-deep py-3.5 text-white font-extrabold disabled:opacity-40 active:scale-[0.98] transition-transform"
        >
          Tekshirish
        </button>
      )}
      {checked !== null && (
        <Feedback
          correct={checked}
          correctAnswer={correctAnswer}
          explain={explain}
          onNext={() => onDone(checked)}
        />
      )}
    </div>
  );
}

/* ── order_words ── */

function OrderWordsEx({
  item,
  onDone,
}: {
  item: MicroTestItem;
  onDone: (ok: boolean) => void;
}) {
  const bank = useMemo(
    () => item.words.map((w, i) => ({ w, i })).sort(() => Math.random() - 0.5),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );
  const [chosen, setChosen] = useState<number[]>([]);
  const [checked, setChecked] = useState<boolean | null>(null);

  const answerText = item.answer;
  const built = chosen.map((i) => bank.find((b) => b.i === i)!.w).join(" ");

  const submit = () => {
    const ok = normAr(built) === normAr(answerText);
    setChecked(ok);
    tg()?.HapticFeedback?.notificationOccurred(ok ? "success" : "error");
  };

  return (
    <div>
      <div className="font-bold text-lg">{item.q_uz || "So'zlarni tartiblang"}</div>
      <div
        className="mt-4 min-h-16 rounded-2xl border-2 border-dashed border-cardline bg-card/50 p-3 flex flex-wrap gap-2 items-center justify-center"
        dir="rtl"
      >
        {chosen.map((i) => (
          <button
            key={i}
            onClick={() => checked === null && setChosen((c) => c.filter((x) => x !== i))}
            className="rounded-xl bg-emerald-deep text-white px-3 py-2 font-arabic text-xl"
          >
            {bank.find((b) => b.i === i)!.w}
          </button>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-2 justify-center" dir="rtl">
        {bank.map((b) => (
          <button
            key={b.i}
            disabled={chosen.includes(b.i) || checked !== null}
            onClick={() => setChosen((c) => [...c, b.i])}
            className={`rounded-xl border px-3 py-2 font-arabic text-xl ${
              chosen.includes(b.i)
                ? "opacity-25 bg-cardline border-cardline"
                : "bg-card border-cardline"
            }`}
          >
            {b.w}
          </button>
        ))}
      </div>
      {checked === null && (
        <button
          onClick={submit}
          disabled={!chosen.length}
          className="mt-5 w-full rounded-2xl bg-emerald-deep py-3.5 text-white font-extrabold disabled:opacity-40"
        >
          Tekshirish
        </button>
      )}
      {checked !== null && (
        <Feedback
          correct={checked}
          correctAnswer={answerText}
          explain={item.explain_uz}
          onNext={() => onDone(checked)}
        />
      )}
    </div>
  );
}

/* ── shadowing (o'z-o'zini baholash) ── */

function ShadowingEx({
  item,
  onDone,
}: {
  item: MicroTestItem;
  onDone: (ok: boolean) => void;
}) {
  useEffect(() => {
    playAudio(item.audio);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className="text-center">
      <div className="font-bold text-lg text-left">
        {item.q_uz || "Eshiting va ovoz chiqarib takrorlang"}
      </div>
      {item.q_ar && (
        <div className="my-6 font-arabic text-5xl leading-snug" dir="rtl">
          {item.q_ar}
        </div>
      )}
      <button
        onClick={() => playAudio(item.audio)}
        className="mx-auto w-16 h-16 rounded-full bg-emerald-deep text-white text-2xl flex items-center justify-center active:scale-90 transition-transform"
      >
        🔊
      </button>
      <div className="mt-6 grid grid-cols-2 gap-3">
        <button
          onClick={() => playAudio(item.audio)}
          className="rounded-2xl bg-card border border-cardline py-3.5 font-extrabold"
        >
          🔁 Yana eshitish
        </button>
        <button
          onClick={() => {
            tg()?.HapticFeedback?.notificationOccurred("success");
            onDone(true);
          }}
          className="rounded-2xl bg-emerald-deep text-white py-3.5 font-extrabold"
        >
          ✓ Aytdim
        </button>
      </div>
    </div>
  );
}

/* ── Vazn qo'llash (build_word distraktorlari uchun) ── */

const FALLBACK_PATTERNS = ["فاعِل", "مَفْعول", "مَفْعَل", "فِعال", "تَفْعيل", "مُفَعِّل"];
const FALLBACK_ROOTS = ["ك ت ب", "د ر س", "ع ل م", "س ف ر", "ن ظ ر", "ق ب ل", "ح ك م"];

export function applyPattern(pattern: string, root: string): string {
  const letters = root.split(/[\s\-]+/).filter(Boolean);
  if (letters.length < 3) return pattern;
  let out = "";
  for (const ch of pattern) {
    if (ch === "ف") out += letters[0];
    else if (ch === "ع") out += letters[1];
    else if (ch === "ل") out += letters[2];
    else out += ch;
  }
  return out;
}

/* ── QuizRunner — mikro-test / nazorat testi yurgizuvchisi ── */

export function QuizRunner({
  items,
  rootPool = [],
  label,
  onFinish,
}: {
  items: MicroTestItem[];
  rootPool?: string[];
  label: string;
  onFinish: (correct: number, total: number, wrongWords: string[]) => void;
}) {
  const [idx, setIdx] = useState(0);
  const results = useRef<boolean[]>([]);
  const wrong = useRef<string[]>([]);

  const item = items[idx];
  if (!item) return null;

  const done = (ok: boolean) => {
    results.current.push(ok);
    if (!ok) {
      const w = isArabic(item.answer) ? item.answer : isArabic(item.q_ar) ? item.q_ar : "";
      if (w) wrong.current.push(w);
    }
    if (idx + 1 < items.length) setIdx(idx + 1);
    else
      onFinish(
        results.current.filter(Boolean).length,
        items.length,
        wrong.current
      );
  };

  const key = `${idx}-${item.type}`;

  return (
    <div>
      <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-1">
        {label} · {idx + 1}/{items.length}
      </div>
      {renderExercise(item, key, done, rootPool)}
    </div>
  );
}

function renderExercise(
  item: MicroTestItem,
  key: string,
  onDone: (ok: boolean) => void,
  rootPool: string[]
) {
  switch (item.type) {
    case "mcq":
      return (
        <OptionsEx
          key={key}
          prompt={item.q_uz || item.q_ar}
          arabicBig={item.q_uz && isArabic(item.q_ar) ? item.q_ar : undefined}
          audio={item.audio || undefined}
          options={item.options}
          answer={item.answer}
          explain={item.explain_uz}
          onDone={onDone}
        />
      );
    case "match_root": {
      const pool = [...new Set([...rootPool, ...FALLBACK_ROOTS])]
        .filter((r) => r !== item.root && r !== item.answer)
        .slice(0, 3);
      return (
        <OptionsEx
          key={key}
          prompt={item.q_uz || "Bu so'zning o'zagini toping"}
          arabicBig={item.q_ar}
          options={[item.answer, ...pool]}
          answer={item.answer}
          explain={item.explain_uz}
          arabicOptions
          onDone={onDone}
        />
      );
    }
    case "build_word": {
      const distract = FALLBACK_PATTERNS.filter((p) => p !== item.pattern)
        .slice(0, 3)
        .map((p) => applyPattern(p, item.root));
      return (
        <OptionsEx
          key={key}
          prompt={item.q_uz || "O'zak va vazndan so'z yasang"}
          arabicBig={`${item.root}  +  ${item.pattern}`}
          options={[item.answer, ...distract]}
          answer={item.answer}
          explain={item.explain_uz}
          arabicOptions
          onDone={onDone}
        />
      );
    }
    case "fill_blank":
      return (
        <InputEx
          key={key}
          prompt={item.q_uz || "Bo'sh joyni to'ldiring"}
          arabicBig={item.q_ar}
          arabicInput
          showHarakatKeys={false}
          check={(v) => normAr(v) === normAr(item.answer)}
          correctAnswer={item.answer}
          explain={item.explain_uz}
          onDone={onDone}
        />
      );
    case "translate_uz_ar":
      return (
        <InputEx
          key={key}
          prompt={`Arabchaga tarjima qiling: «${item.q_uz}»`}
          arabicInput
          showHarakatKeys={false}
          check={(v) => normAr(v) === normAr(item.answer)}
          correctAnswer={item.answer}
          explain={item.explain_uz}
          onDone={onDone}
        />
      );
    case "translate_ar_uz":
      return (
        <InputEx
          key={key}
          prompt={item.q_uz || "O'zbekchaga tarjima qiling"}
          arabicBig={item.q_ar}
          audio={item.audio || undefined}
          arabicInput={false}
          check={(v) => latOk(item.answer, v)}
          correctAnswer={item.answer}
          explain={item.explain_uz}
          onDone={onDone}
        />
      );
    case "dictation":
      return (
        <InputEx
          key={key}
          prompt={item.q_uz || "Eshiting va yozing"}
          audio={item.audio}
          autoplay
          arabicInput
          showHarakatKeys={false}
          check={(v) => normAr(v) === normAr(item.answer)}
          correctAnswer={item.answer}
          explain={item.explain_uz}
          onDone={onDone}
        />
      );
    case "harakat":
      return (
        <InputEx
          key={key}
          prompt={item.q_uz || "Harakatlarni qo'yib yozing"}
          arabicBig={stripHarakat(item.answer)}
          audio={item.audio || undefined}
          arabicInput
          showHarakatKeys
          check={(v) => harakatNorm(v) === harakatNorm(item.answer)}
          correctAnswer={item.answer}
          explain={item.explain_uz}
          onDone={onDone}
        />
      );
    case "order_words":
      return <OrderWordsEx key={key} item={item} onDone={onDone} />;
    case "shadowing":
      return <ShadowingEx key={key} item={item} onDone={onDone} />;
    default:
      return null;
  }
}
