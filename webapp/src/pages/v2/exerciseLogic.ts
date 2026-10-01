/** Mashq mantig'i — React'siz sof funksiyalar (tests/test_exercise_logic.py ularni node orqali sinaydi).
 *
 *  K29.4 — o'quvchilar xabarlari (#F150, #F151, #F158) bo'yicha:
 *   • «so'z yasash»: variantlardan biri javobning harakatsiz nusxasi edi (مَكْتُوب ↔ مَكْتوب) — endi distraktor
 *     javob bilan bir xil «skelet»li bo'lmaydi;
 *   • «harakat qo'yish»: so'z yakka turganda namunada oxirgi harfda harakat yo'q — o'quvchi e'rob harakatini
 *     (مُدَرِّسُ) qo'ysa ham to'g'ri.
 */

import { normAr, type Verdict } from "./answerCheck";

/* ── harakat mashqi (#F74): so'z harflari tayyor, o'quvchi faqat harakat qo'yadi ── */

/** Bitta harf + unga qo'yilgan harakatlar (combining belgilar). Bo'shliq ham alohida slot. */
export type HarakatSlot = { base: string; marks: string };
const MARK_RE = /[ً-ْٰ]/;
/** Sukun va xanjar alif — ko'pincha yozilmaydi, yo'qligi xato emas (izoh beriladi). */
const OPTIONAL_MARKS = /[ْٰ]/g;
/** E'rob harakati: fathatan, dammatan, kasratan, fatha, damma, kasra (shadda va sukun emas). */
const CASE_ENDING = /^[ً-ِ]$/;

export const splitHarakat = (word: string): HarakatSlot[] => {
  const out: HarakatSlot[] = [];
  for (const ch of word.replace(/ـ/g, "")) {
    if (MARK_RE.test(ch) && out.length) out[out.length - 1].marks += ch;
    else out.push({ base: ch, marks: "" });
  }
  return out;
};

export const joinHarakat = (slots: HarakatSlot[]) => slots.map((s) => s.base + s.marks).join("");
const markKey = (marks: string, strict: boolean) =>
  [...(strict ? marks : marks.replace(OPTIONAL_MARKS, ""))].sort().join("");

/** Harakat tekshiruvi: aynan → exact; faqat sukun farqi → to'g'ri + izoh; faqat oxirgi harfda
 *  e'rob farqi (qo'yilmagan YOKI namunada yo'q, o'quvchi qo'ygan) → to'g'ri + izoh (oxirgi harakat
 *  gapdagi o'rniga bog'liq — A0 hali o'rganmagan); boshqa farq → xato, `wrong` — noto'g'ri harf
 *  indekslari (qizil ko'rsatiladi). */
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
  const userEnd = user[last].marks.replace(OPTIONAL_MARKS, "");
  const ansEnd = ans[last].marks.replace(OPTIONAL_MARKS, "");
  if (loose.length === 1 && loose[0] === last && !userEnd && ansEnd) {
    return {
      ok: true,
      exact: false,
      note: `E'rob: so'z oxirida ${ans[last].base + ans[last].marks} — oxirgi harakat gapdagi o'rniga qarab o'zgaradi`,
      wrong: loose,
    };
  }
  // K29.4 (#F158, a0-28 «mudarris»: 4 kishi): namunada oxirgi harf yalang'och, o'quvchi e'rob harakati qo'ygan
  if (loose.length === 1 && loose[0] === last && !ansEnd && CASE_ENDING.test(userEnd)) {
    return {
      ok: true,
      exact: false,
      note: "Oxirgi harf: namunada harakat yo'q (so'z yakka turibdi). Gap ichida oxirgi harakat e'robga qarab qo'yiladi — sizniki ham to'g'ri",
      wrong: loose,
    };
  }
  return { ok: false, wrong: loose };
};

/** Harakat paneli tugmalari (belgilar \u kodlari bilan — ko'rinmas combining belgi yo'qolib ketmasin). */
export const HARAKAT_KEYS: { ch: string; label: string; title: string }[] = [
  { ch: "َ", label: "ـَ", title: "fatha (a)" },
  { ch: "ِ", label: "ـِ", title: "kasra (i)" },
  { ch: "ُ", label: "ـُ", title: "damma (u)" },
  { ch: "ْ", label: "ـْ", title: "sukun" },
  { ch: "ّ", label: "ـّ", title: "shadda" },
  { ch: "ً", label: "ـً", title: "tanvin an" },
  { ch: "ٍ", label: "ـٍ", title: "tanvin in" },
  { ch: "ٌ", label: "ـٌ", title: "tanvin un" },
];

/** So'z ko'rinishida (matn) solishtirish — testlar va jurnal uchun. */
export const harakatCheck = (userWord: string, answerWord: string) =>
  harakatVerdict(splitHarakat(userWord), splitHarakat(answerWord));

/** Harfga harakat qo'yish: shadda alohida (unli bilan birga turadi), qolganlari bir-birini almashtiradi. */
export const applyMark = (marks: string, ch: string): string => {
  const hasShadda = marks.includes("ّ");
  const vowel = marks.replace(/ّ/g, "");
  if (ch === "ّ") return (hasShadda ? "" : "ّ") + vowel;
  return (hasShadda ? "ّ" : "") + (vowel === ch ? "" : ch);
};

/* ── Vazn qo'llash (build_word distraktorlari uchun) ── */

/** To'liq harakatli qoliplar: o'zakka qo'llanganda javobning o'zi emas, boshqa shakl chiqadi. */
export const FALLBACK_PATTERNS = [
  "فَاعِل", "مَفْعُول", "مَفْعَل", "فِعَال", "تَفْعِيل", "مُفَعِّل", "مُفَاعِل", "اِسْتِفْعَال", "فَعِيل", "فُعُول",
];

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

/** 3 ta distraktor. Javob bilan (yoki bir-biri bilan) HARAKATSIZ yozilishi bir xil bo'lgan so'z olinmaydi:
 *  مَكْتُوب va مَكْتوب — o'quvchi uchun bir xil so'z, ikkinchisini tanlasa «to'g'ri javobim xato» chiqardi (#F150). */
export function buildWordDistractors(item: { root: string; answer: string }): string[] {
  const seen = new Set([normAr(item.answer)]);
  const out: string[] = [];
  for (const p of FALLBACK_PATTERNS) {
    const w = applyPattern(p, item.root);
    const k = normAr(w);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(w);
    if (out.length === 3) break;
  }
  return out;
}

/** Arabcha variantlar orasida faqat harakat bilan farq qiladiganlari bormi (مُعَلِّم ↔ مُعَلَّم) —
 *  bunda o'quvchiga «harakatlarga qarang» deb eslatiladi. */
export const hasLookalikes = (options: string[]): boolean =>
  new Set(options.map(normAr)).size < options.length;
