/** v2 mashq dvigateli — 10 tur (spec §11) + QuizRunner.
 * Har mashq onDone(ok) chaqiradi; QuizRunner xato so'zlarni yig'adi (SRS reset uchun).
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { api, type MicroTestItem } from "../../lib/api";
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

/** Tekshiruv natijasi: `exact=false` — yumshoq qabul (namuna ko'rsatiladi), `note` — imlo izohi. */
type Verdict = { ok: boolean; exact?: boolean; note?: string };
const asVerdict = (r: boolean | Verdict): Verdict => (typeof r === "boolean" ? { ok: r, exact: r } : r);

/** ى/ي va ة/ه — klaviaturada eng ko'p adashadigan juftliklar: kechiriladi, lekin izoh beriladi. */
const normArLoose = (s: string) => normAr(s).replace(/ى/g, "ي").replace(/ة/g, "ه");
const AR_NOTES: Record<string, string> = {
  "ىي": "so'z oxirida ى (alif maqsura, nuqtasiz) bo'lishi kerak, ي emas",
  "يى": "bu yerda ي (ikki nuqtali) bo'lishi kerak, ى emas",
  "ةه": "so'z oxirida ة (ta marbuta, ikki nuqtali) bo'lishi kerak, ه emas",
  "هة": "bu yerda ه (nuqtasiz) bo'lishi kerak, ة emas",
};

const arOk = (answer: string, value: string): Verdict => {
  const a = normAr(answer);
  const v = normAr(value);
  if (a === v) return { ok: true, exact: true };
  if (!v || normArLoose(a) !== normArLoose(v)) return { ok: false };
  // Uzunlik teng — farq faqat ى/ي, ة/ه o'rinlarida
  const notes = new Set<string>();
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== v[i]) notes.add(AR_NOTES[a[i] + v[i]] ?? "");
  }
  notes.delete("");
  return { ok: true, exact: false, note: notes.size ? "Imlo: " + [...notes].join("; ") : undefined };
};

const normLat = (s: string) =>
  s.toLowerCase().replace(/[''ʼ’‘ʻ`\-_.?!:;«»"]/g, "").replace(/\s+/g, " ").trim();

/** "qalam / ruchka" yoki "ta'til, ruxsat" kabi javoblarda BITTA variant yetarli. */
const latVariants = (answer: string): string[] => {
  const out: string[] = [];
  const push = (s: string) =>
    s
      .split(/\s*(?:\/|,|;|\byoki\b)\s*/)
      .map(normLat)
      .filter(Boolean)
      .forEach((v) => out.push(v));

  // Oxirgi qavs — sinonim izohi ("maktab (madrasa)"), u ham TO'G'RI javob.
  // O'rtadagi qavs esa gapning bo'lagi ("sen (ayol) yozasan") — yakka
  // o'zi javob emas, shuning uchun faqat oxirgisi variantga aylanadi.
  const tail = answer.match(/\(([^)]*)\)\s*$/);
  if (tail) push(tail[1]);
  push(answer.replace(/\([^)]*\)/g, " ")); // qavssiz asosiy javob
  push(answer); // qavsi bilan to'liq ko'chirgan bo'lsa ham

  return [...new Set(out)];
};

/* ── Yumshoq solishtirish (o'zbekcha javob) ──
   Aynan mos kelmasa ham TO'G'RI: qavs izohi farqi («sen (muannas) yozyapsan» = «sen (ayol) yozasan»),
   fe'l zamoni (-yapti / -moqda / -adi bir xil — arabcha muzore' ikkalasiga tarjima qilinadi),
   olmosh tushirilgan («yozasan» = «sen yozasan»), «ular keldi» = «ular keldilar», so'z tartibi,
   x/h imlosi, harf o'rni almashgan yoki qo'sh harf tushgan («diqat» = «diqqat»).
   Fe'l shaxsi va inkori (-ma-), o/u kabi ma'no o'zgartiruvchi harflar — kechirilmaydi. */
const PRONOUNS = new Set(["men", "sen", "u", "biz", "siz", "ular"]);
const SYNONYMS: Record<string, string> = { muannas: "ayol", muzakkar: "erkak", hamda: "va" };
const PRES: Record<string, string> = { di: "ti", dilar: "tilar" }; // hozirgi zamon shaxslari: man san ti miz siz tilar
const PAST: Record<string, string> = { man: "m", san: "ng", miz: "k", siz: "ngiz" }; // -gan shaxslari → -di shaxslari

/** Fe'lni «o'zak|zamon|shaxs» ko'rinishiga keltiradi; fe'l bo'lmasa so'z o'zgarmaydi. */
const verbCanon = (w: string): string => {
  let m = w.match(/^(.{2,}?)(?:yap|moqda)(man|san|ti|di|miz|siz|tilar|dilar)?$/); // yozyapti, yozmoqda(man)
  if (m) return `${m[1]}|hoz|${PRES[m[2] ?? "ti"] ?? m[2] ?? "ti"}`;
  m = w.match(/^(.{2,}?)ma(di|dim|ding|dik|dingiz|dilar)$/); // o'tgan zamon inkori: bormadi
  if (m) return `${m[1]}|otgma|${m[2].slice(2)}`;
  m = w.match(/^(.{2,}?)[ay](man|san|di|miz|siz|dilar)$/); // hozirgi-kelasi: yozadi, o'qiyman, bormaydi
  if (m) return `${m[1]}|hoz|${PRES[m[2]] ?? m[2]}`;
  m = w.match(/^(.{2,}?)di(m|ng|k|ngiz|lar)?$/); // o'tgan: yozdi, yozdim
  if (m) return `${m[1]}|otg|${m[2] ?? ""}`;
  m = w.match(/^(.{2,}?)(?:gan|kan|qan)(man|san|miz|siz|lar)?$/); // yozgan(man) = yozdi(m)
  if (m) return `${m[1]}|otg|${m[2] ? PAST[m[2]] ?? m[2] : ""}`;
  return w;
};

const canonTokens = (s: string): string[] => {
  const t = s
    .replace(/\([^)]*\)/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => verbCanon((SYNONYMS[w] ?? w).replace(/x/g, "h")));
  // «ular» bo'lsa 3-shaxs birlik fe'l ko'plikka tenglashadi (moslashuv ixtiyoriy)
  return t.includes("ular")
    ? t.map((w) => (w.endsWith("|otg|") ? w + "lar" : w.endsWith("|hoz|ti") ? w + "lar" : w))
    : t;
};

/** Imlo xatosi: qo'shni harflar o'rni almashgan, yoki qo'sh harf bitta yozilgan / ortiqcha takrorlangan. */
const typoClose = (x: string, y: string): boolean => {
  if (x.length === y.length) {
    let i = 0;
    while (i < x.length && x[i] === y[i]) i++;
    return i < x.length - 1 && x[i] === y[i + 1] && x[i + 1] === y[i] && x.slice(i + 2) === y.slice(i + 2);
  }
  if (Math.abs(x.length - y.length) !== 1) return false;
  const [long, short] = x.length > y.length ? [x, y] : [y, x];
  let i = 0;
  while (i < short.length && long[i] === short[i]) i++;
  return long.slice(i + 1) === short.slice(i) && (long[i] === long[i + 1] || (i > 0 && long[i] === long[i - 1]));
};

const wordClose = (x: string, y: string): boolean =>
  x === y || (!x.includes("|") && !y.includes("|") && x.length >= 4 && typoClose(x, y));

const seqClose = (a: string[], b: string[]) => a.length === b.length && a.every((w, i) => wordClose(w, b[i]));

const tokensMatch = (a: string[], b: string[]): boolean => {
  // Olmosh faqat bir tomonda bo'lsa — tushirilgan deb hisoblanadi; ikkalasida bo'lsa mos kelishi shart
  const pa = a.some((w) => PRONOUNS.has(w));
  const pb = b.some((w) => PRONOUNS.has(w));
  if (pa !== pb) {
    const sa = a.filter((w) => !PRONOUNS.has(w));
    const sb = b.filter((w) => !PRONOUNS.has(w));
    if (sa.length && sb.length) [a, b] = [sa, sb];
  }
  return seqClose(a, b) || seqClose([...a].sort(), [...b].sort());
};

const latOk = (answer: string, value: string): Verdict => {
  const nv = normLat(value);
  if (!nv) return { ok: false };
  const variants = latVariants(answer);
  if (variants.includes(nv)) return { ok: true, exact: true };
  const vt = canonTokens(nv);
  const ok = vt.length > 0 && variants.some((v) => tokensMatch(canonTokens(v), vt));
  return ok ? { ok: true, exact: false } : { ok: false };
};

/** harakat mashqi: harakatlar solishtiriladi, lekin alif varianti va bo'shliq farqi kechiriladi. */
/* ── harakat mashqi (#F74): so'z harflari tayyor, o'quvchi faqat harakat qo'yadi ── */

/** Bitta harf + unga qo'yilgan harakatlar (combining belgilar). Bo'shliq ham alohida slot. */
export type HarakatSlot = { base: string; marks: string };
const MARK_RE = /[ً-ْٰ]/;
/** Sukun va xanjar alif — ko'pincha yozilmaydi, yo'qligi xato emas (izoh beriladi). */
const OPTIONAL_MARKS = /[ْٰ]/g;

export const splitHarakat = (word: string): HarakatSlot[] => {
  const out: HarakatSlot[] = [];
  for (const ch of word.replace(/ـ/g, "")) {
    if (MARK_RE.test(ch) && out.length) out[out.length - 1].marks += ch;
    else out.push({ base: ch, marks: "" });
  }
  return out;
};

const joinHarakat = (slots: HarakatSlot[]) => slots.map((s) => s.base + s.marks).join("");
const markKey = (marks: string, strict: boolean) =>
  [...(strict ? marks : marks.replace(OPTIONAL_MARKS, ""))].sort().join("");

/** Harakat tekshiruvi: aynan → exact; faqat sukun farqi → to'g'ri + izoh; faqat oxirgi harfda
 *  e'rob qo'yilmagan → to'g'ri + izoh (oxirgi harakat gapdagi o'rniga bog'liq — A0 hali o'rganmagan);
 *  boshqa farq → xato, `wrong` — noto'g'ri harf indekslari (qizil ko'rsatiladi). */
export const harakatVerdict = (user: HarakatSlot[], ans: HarakatSlot[]): Verdict & { wrong: number[] } => {
  if (user.length !== ans.length || user.some((s, i) => s.base !== ans[i].base)) return { ok: false, wrong: [] };
  const strict: number[] = [];
  const loose: number[] = [];
  user.forEach((s, i) => {
    if (markKey(s.marks, true) !== markKey(ans[i].marks, true)) strict.push(i);
    if (markKey(s.marks, false) !== markKey(ans[i].marks, false)) loose.push(i);
  });
  if (!strict.length) return { ok: true, exact: true, wrong: [] };
  if (!loose.length) return { ok: true, exact: false, note: "Sukun (ـْ) ham qo'yiladi — namunaga qarang", wrong: strict };
  let last = ans.length - 1;
  while (last > 0 && !/[؀-ۿ]/.test(ans[last].base)) last--;
  const untouchedEnd = !user[last].marks.replace(OPTIONAL_MARKS, "");
  if (loose.length === 1 && loose[0] === last && untouchedEnd && ans[last].marks) {
    return {
      ok: true,
      exact: false,
      note: `E'rob: so'z oxirida ${ans[last].base + ans[last].marks} — oxirgi harakat gapdagi o'rniga qarab o'zgaradi`,
      wrong: loose,
    };
  }
  return { ok: false, wrong: loose };
};

const HARAKAT_KEYS: { ch: string; label: string; title: string }[] = [
  { ch: "َ", label: "ـَ", title: "fatha (a)" },
  { ch: "ِ", label: "ـِ", title: "kasra (i)" },
  { ch: "ُ", label: "ـُ", title: "damma (u)" },
  { ch: "ْ", label: "ـْ", title: "sukun" },
  { ch: "ّ", label: "ـّ", title: "shadda" },
  { ch: "ً", label: "ـً", title: "tanvin an" },
  { ch: "ٍ", label: "ـٍ", title: "tanvin in" },
  { ch: "ٌ", label: "ـٌ", title: "tanvin un" },
];

/** Harfga harakat qo'yish: shadda alohida (unli bilan birga turadi), qolganlari bir-birini almashtiradi. */
export const applyMark = (marks: string, ch: string): string => {
  const hasShadda = marks.includes("ّ");
  const vowel = marks.replace(/ّ/g, "");
  if (ch === "ّ") return (hasShadda ? "" : "ّ") + vowel;
  return (hasShadda ? "ّ" : "") + (vowel === ch ? "" : ch);
};

export function HarakatEx({
  prompt,
  answer,
  audio,
  explain,
  onDone,
  onWrong,
}: {
  prompt: string;
  answer: string;
  audio?: string;
  explain?: string;
  onDone: (ok: boolean) => void;
  onWrong?: (given: string) => void;
}) {
  const target = useMemo(() => splitHarakat(answer), [answer]);
  const [slots, setSlots] = useState<HarakatSlot[]>(() => target.map((s) => ({ base: s.base, marks: "" })));
  const firstLetter = target.findIndex((s) => /[؀-ۿ]/.test(s.base));
  const [sel, setSel] = useState(firstLetter < 0 ? 0 : firstLetter);
  const [verdict, setVerdict] = useState<(Verdict & { wrong: number[] }) | null>(null);
  const done = verdict !== null;

  const isLetter = (i: number) => /[؀-ۿ]/.test(target[i]?.base ?? "");
  const nextLetter = (from: number) => {
    for (let i = from + 1; i < target.length; i++) if (isLetter(i)) return i;
    return from;
  };

  const put = (ch: string) => {
    if (done) return;
    tg()?.HapticFeedback?.impactOccurred("light");
    setSlots((prev) => prev.map((s, i) => (i === sel ? { ...s, marks: applyMark(s.marks, ch) } : s)));
    // unli qo'yilgach keyingi harfga o'tamiz (shadda — shu harfda qolamiz, unli ham kerak)
    if (ch !== "ّ") setSel((i) => nextLetter(i));
  };
  const clear = () => {
    if (done) return;
    setSlots((prev) => prev.map((s, i) => (i === sel ? { ...s, marks: "" } : s)));
  };
  const submit = () => {
    const v = harakatVerdict(slots, target);
    setVerdict(v);
    if (!v.ok) onWrong?.(joinHarakat(slots));
    tg()?.HapticFeedback?.notificationOccurred(v.ok ? "success" : "error");
  };
  const touched = slots.some((s) => s.marks);

  return (
    <div>
      <div className="font-bold text-lg">{prompt}</div>
      <p className="mt-1 text-[12px] text-ink-soft font-semibold">
        Harfni bosing, keyin harakatni tanlang — harflar tayyor, faqat harakat qo'yiladi.
      </p>
      {audio && (
        <button
          onClick={() => playAudio(audio)}
          className="mx-auto my-3 w-12 h-12 rounded-full bg-emerald-deep text-white text-lg flex items-center justify-center active:scale-90 transition-transform"
        >
          🔊
        </button>
      )}
      {/* Jonli natija */}
      <div className="my-3 text-center font-arabic text-5xl leading-snug min-h-16" dir="rtl">
        {joinHarakat(slots)}
      </div>
      {/* Harf plitkalari */}
      <div className="flex flex-wrap justify-center gap-1.5" dir="rtl">
        {slots.map((s, i) =>
          isLetter(i) ? (
            <button
              key={i}
              type="button"
              onClick={() => !done && setSel(i)}
              className={`min-w-12 h-14 px-2 rounded-xl border-2 font-arabic text-3xl leading-none transition-colors ${
                done && verdict.wrong.includes(i)
                  ? verdict.ok
                    ? "border-gold bg-gold-soft"
                    : "border-terracotta bg-terracotta/10"
                  : i === sel && !done
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
      {/* Harakat paneli */}
      {!done && (
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
            onClick={clear}
            className="mt-1.5 w-full h-9 rounded-xl bg-terracotta/10 border border-terracotta/40 text-xs font-extrabold text-ink-soft active:scale-95"
          >
            ✕ Tanlangan harfdan harakatni olib tashlash
          </button>
        </>
      )}
      {!done && (
        <button
          onClick={submit}
          disabled={!touched}
          className="mt-4 w-full rounded-2xl bg-emerald-deep py-3.5 text-white font-extrabold disabled:opacity-40 active:scale-[0.98] transition-transform"
        >
          Tekshirish
        </button>
      )}
      {verdict !== null && (
        <Feedback
          correct={verdict.ok}
          correctAnswer={answer}
          explain={explain}
          note={verdict.note}
          showSample={verdict.ok && verdict.exact === false}
          onNext={() => onDone(verdict.ok)}
        />
      )}
    </div>
  );
}

/* ── Umumiy feedback paneli ── */

function Feedback({
  correct,
  correctAnswer,
  explain,
  note,
  showSample,
  onNext,
}: {
  correct: boolean;
  correctAnswer?: string;
  explain?: string;
  /** Imlo izohi (yumshoq qabul qilingan arabcha javob) */
  note?: string;
  /** To'g'ri, lekin aynan emas — aniq shakl «Namuna» sifatida ko'rsatiladi */
  showSample?: boolean;
  onNext: () => void;
}) {
  const showAnswer = correctAnswer && (!correct || showSample);
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
        {showAnswer && (
          <div
            className={`text-white/95 font-bold mt-1 ${
              isArabic(correctAnswer) ? "font-arabic text-2xl" : "text-sm"
            }`}
            dir={isArabic(correctAnswer) ? "rtl" : "ltr"}
          >
            {correct ? "Namuna: " : "To'g'ri javob: "}
            {correctAnswer}
          </div>
        )}
        {note && (
          <div className="text-white/90 text-xs font-bold mt-1.5 leading-relaxed">✍️ {note}</div>
        )}
        {explain && (
          <div className="text-white/80 text-xs font-semibold mt-1.5 leading-relaxed">
            {explain}
          </div>
        )}
        <button
          onClick={onNext}
          className="mt-3 w-full rounded-2xl bg-white py-3.5 font-extrabold text-[#26211a] active:scale-[0.98] transition-transform"
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
  onWrong,
}: {
  prompt: string;
  arabicBig?: string;
  audio?: string;
  autoplay?: boolean;
  arabicInput: boolean;
  showHarakatKeys?: boolean;
  check: (value: string) => boolean | Verdict;
  correctAnswer: string;
  explain?: string;
  onDone: (ok: boolean) => void;
  /** #F70: rad etilgan javob jurnalga (admin /javoblar) */
  onWrong?: (given: string) => void;
}) {
  const [value, setValue] = useState("");
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const checked = verdict === null ? null : verdict.ok;

  useEffect(() => {
    if (autoplay) playAudio(audio);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = () => {
    const v = asVerdict(check(value));
    setVerdict(v);
    if (!v.ok) onWrong?.(value);
    tg()?.HapticFeedback?.notificationOccurred(v.ok ? "success" : "error");
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
      {/* Arab klaviaturasida — terilgan matn uchun alohida oyna kerak.
          Lotin javobida esa <input> ning o'zi ko'rsatadi, aks holda
          bir xil matnli IKKITA quti chiqadi. */}
      {arabicInput ? (
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
          <ArabicKeyboard
            onChar={(ch) => checked === null && setValue((v) => v + ch)}
            onBackspace={() => checked === null && setValue((v) => v.slice(0, -1))}
            showHarakat={showHarakatKeys}
          />
        </>
      ) : (
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={checked !== null}
          autoCapitalize="none"
          autoCorrect="off"
          className="mt-2 w-full min-h-14 rounded-2xl border-2 border-emerald-deep/50 bg-card px-4 py-3 text-xl font-bold outline-none focus:border-emerald-deep disabled:opacity-100"
          placeholder="Javobingiz..."
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
      {verdict !== null && (
        <Feedback
          correct={verdict.ok}
          correctAnswer={correctAnswer}
          explain={explain}
          note={verdict.note}
          showSample={verdict.ok && verdict.exact === false}
          onNext={() => onDone(verdict.ok)}
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
  context,
  onFinish,
  onProgress,
}: {
  items: MicroTestItem[];
  rootPool?: string[];
  label: string;
  /** #F70: jurnal uchun manba (dars id, «cp25», «exam»…); bo'lmasa label */
  context?: string;
  onFinish: (correct: number, total: number, wrongWords: string[]) => void;
  /** Test ichidagi ilgarilash (0..1) — yuqoridagi umumiy chiziq uchun. */
  onProgress?: (frac: number) => void;
}) {
  const [idx, setIdx] = useState(0);
  const results = useRef<boolean[]>([]);
  const wrong = useRef<string[]>([]);

  useEffect(() => {
    onProgress?.(items.length ? idx / items.length : 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx, items.length]);

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
  // #F70: yozma javob rad etilsa — serverga (adminga soxta-salbiylarni ko'rsatadi)
  const report = (given: string) =>
    void api.logWrongAnswer({
      context: (context || label).slice(0, 24),
      ex_type: item.type,
      q: item.q_uz || item.q_ar,
      expected: item.answer,
      given,
    });

  return (
    <div>
      <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-1">
        {label} · {idx + 1}/{items.length}
      </div>
      {renderExercise(item, key, done, rootPool, report)}
    </div>
  );
}

function renderExercise(
  item: MicroTestItem,
  key: string,
  onDone: (ok: boolean) => void,
  rootPool: string[],
  onWrong?: (given: string) => void
) {
  // Klaviatura talab qiladigan turlar (fill_blank / harakat / dictation /
  // translate_uz_ar) ba'zan TAYYOR VARIANTLAR bilan yoziladi ("...ni tanlang").
  // Bunday savolni yozdirish o'rniga variantli test qilib ko'rsatamiz —
  // aks holda o'quvchi klaviaturadan aynan mos matnni topa olmaydi.
  const KEYBOARD_TYPES = ["fill_blank", "harakat", "dictation", "translate_uz_ar"];
  if (KEYBOARD_TYPES.includes(item.type) && item.options && item.options.length >= 2) {
    return (
      <OptionsEx
        key={key}
        prompt={item.q_uz || item.q_ar}
        arabicBig={item.q_uz && isArabic(item.q_ar) ? item.q_ar : undefined}
        audio={item.audio || undefined}
        options={item.options}
        answer={item.answer}
        explain={item.explain_uz}
        arabicOptions={item.options.some(isArabic)}
        onDone={onDone}
      />
    );
  }

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
    case "fill_blank": {
      // Javob arabcha bo'lmasa (masalan «bir qalam (noaniq)») — arab
      // klaviaturasi bilan uni yozib bo'lmaydi, lotin kiritish beriladi.
      const arabicAnswer = isArabic(item.answer);
      return (
        <InputEx
          key={key}
          prompt={item.q_uz || "Bo'sh joyni to'ldiring"}
          arabicBig={item.q_ar}
          arabicInput={arabicAnswer}
          showHarakatKeys={false}
          check={(v) => (arabicAnswer ? arOk(item.answer, v) : latOk(item.answer, v))}
          correctAnswer={item.answer}
          explain={item.explain_uz}
          onDone={onDone}
          onWrong={onWrong}
        />
      );
    }
    case "translate_uz_ar":
      return (
        <InputEx
          key={key}
          prompt={`Arabchaga tarjima qiling: «${item.q_uz}»`}
          arabicInput
          showHarakatKeys={false}
          check={(v) => arOk(item.answer, v)}
          correctAnswer={item.answer}
          explain={item.explain_uz}
          onDone={onDone}
          onWrong={onWrong}
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
          onWrong={onWrong}
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
          check={(v) => arOk(item.answer, v)}
          correctAnswer={item.answer}
          explain={item.explain_uz}
          onDone={onDone}
          onWrong={onWrong}
        />
      );
    case "harakat":
      // #F74: so'zni qayta terish emas — harflar tayyor, faqat harakat tanlanadi
      return (
        <HarakatEx
          key={key}
          prompt={item.q_uz || "Harakatlarni qo'ying"}
          answer={item.answer}
          audio={item.audio || undefined}
          explain={item.explain_uz}
          onDone={onDone}
          onWrong={onWrong}
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
