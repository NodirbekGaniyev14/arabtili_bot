/** Yozma javob tekshiruvi — mikro-test, nazorat testi, mini-imtihon (QuizRunner).
 *
 *  Sof funksiyalar (React'siz): tests/test_answer_check.py ularni node orqali sinaydi.
 *  K27 — o'quvchilarning «to'g'ri javobim xato hisoblandi» xabarlari bo'yicha:
 *   • kirillcha javob lotinga o'giriladi (rus klaviaturasidagi к/г/у/х ham kechiriladi);
 *   • «akamga/ukamga o'rgatdim» — so'z ichidagi «/» butun gapga yoyiladi;
 *   • `accept` — kontentdagi qo'shimcha to'g'ri javoblar (namuna baribir ko'rsatiladi);
 *   • o'zbekcha: «siz» hurmat shakli, egalik olmoshi («mening»), «-ni», «-dir», «bir»
 *     ixtiyoriy; uzun so'zda bitta harf xatosi; bordi ≈ ketdi, dedi ≈ aytdi;
 *   • arabcha (faqat tarjimada): hamza o'rni, ko'plik «ـوا» alifi, «ال» farqi — izoh bilan.
 */

/** Tekshiruv natijasi: `exact=false` — yumshoq qabul (namuna ko'rsatiladi), `note` — imlo izohi. */
export type Verdict = { ok: boolean; exact?: boolean; note?: string };
export const asVerdict = (r: boolean | Verdict): Verdict => (typeof r === "boolean" ? { ok: r, exact: r } : r);

export type CheckOpts = {
  /** Qo'shimcha to'g'ri javoblar (kontentdagi `accept`) */
  accept?: string[];
  /** Arabcha javob qat'iyligi: "strict" — diktant (faqat ى/ي, ة/ه — izoh bilan);
   *  "fill" — to'ldirish (+ «ـوا» alifi); "translate" — tarjima (+ hamza, «ال», olmosh, bo'shliq) */
  mode?: "strict" | "fill" | "translate";
  /** Savol matni: «artikl», «aniq», «tanvin» bo'lsa — «ال» va «bir» qat'iy tekshiriladi */
  prompt?: string;
};

const STRICT_PROMPT = /artikl|\baniq|noaniq|tanvin|ال/i;

export const isArabic = (s: string) => /[؀-ۿ]/.test(s);

/* ── Arabcha ── */

const HARAKAT = /[ً-ْٰ]/g;

/** Alif variantlari (أ إ آ ٱ) → ا: klaviaturada yakka hamzali alif teriladi,
 *  hamza imlosi esa yuqori darajalarda o'rgatiladi — shuning uchun tenglashtiramiz. */
export const normAr = (s: string) =>
  s
    .replace(HARAKAT, "")
    .replace(/ـ/g, "") // tatvil
    .replace(/[أإآٱ]/g, "ا")
    .replace(/ک/g, "ك") // fors ک → ك
    .replace(/ی/g, "ي") // fors ی → ي
    .replace(/[.,،؟!·:؛—–\s]+/g, " ")
    .trim();

type ArRule = { note: string; apply: (s: string) => string };

/** ى/ي va ة/ه — klaviaturada eng ko'p adashadigan juftliklar: kechiriladi, lekin izoh beriladi. */
const YA_TA: ArRule = {
  note: "",
  apply: (s) => s.replace(/ى/g, "ي").replace(/ة/g, "ه"),
};
const HAMZA: ArRule = {
  note: "hamza (ء ؤ ئ) yozilishi — namunaga qarang",
  apply: (s) => s.replace(/ؤ/g, "و").replace(/ئ/g, "ي").replace(/ء/g, ""),
};
const WAW_ALIF: ArRule = {
  note: "ko'plik fe'li oxirida «ـوا» — alif yoziladi, lekin o'qilmaydi",
  apply: (s) => s.replace(/وا(?=\s|$)/g, "و"),
};
const ARTICLE: ArRule = {
  note: "«ال» (aniqlik artikli) farqi kechirildi",
  apply: (s) =>
    s
      .split(" ")
      .map((w) => (w.length > 3 && w.startsWith("ال") ? w.slice(2) : w))
      .join(" "),
};
/** «هم كتبوا» = «كتبوا»: savolda «ular» bo'lsa, o'quvchi olmoshni ham yozishi mumkin. */
const AR_PRONOUNS = new Set(["انا", "نحن", "انت", "انتم", "انتن", "انتما", "هو", "هي", "هم", "هن", "هما"]);
const PRONOUN: ArRule = {
  note: "",
  apply: (s) => {
    const w = s.split(" ");
    return w.length > 1 && AR_PRONOUNS.has(w[0]) ? w.slice(1).join(" ") : s;
  },
};
/** «مازال» = «ما زال» */
const SPACES: ArRule = { note: "", apply: (s) => s.replace(/ /g, "") };

const AR_NOTES: Record<string, string> = {
  "ىي": "so'z oxirida ى (alif maqsura, nuqtasiz) bo'lishi kerak, ي emas",
  "يى": "bu yerda ي (ikki nuqtali) bo'lishi kerak, ى emas",
  "ةه": "so'z oxirida ة (ta marbuta, ikki nuqtali) bo'lishi kerak, ه emas",
  "هة": "bu yerda ه (nuqtasiz) bo'lishi kerak, ة emas",
};

const applyAll = (s: string, rules: ArRule[]) => rules.reduce((acc, r) => r.apply(acc), s);

/** `a` (namuna) va `v` (o'quvchi) qoidalar bilan tenglashsa — qaysi qoidalar KERAK bo'lganini izohlaydi. */
const arLoose = (a: string, v: string, rules: ArRule[]): Verdict | null => {
  if (applyAll(a, rules) !== applyAll(v, rules)) return null;
  const notes = new Set<string>();
  for (const r of rules) {
    const rest = rules.filter((x) => x !== r);
    const [x, y] = [applyAll(a, rest), applyAll(v, rest)];
    if (x === y) continue; // bu qoidasiz ham teng — izoh kerak emas
    if (r !== YA_TA) {
      if (r.note) notes.add(r.note);
    } else if (x.length === y.length) {
      for (let i = 0; i < x.length; i++) if (x[i] !== y[i] && AR_NOTES[x[i] + y[i]]) notes.add(AR_NOTES[x[i] + y[i]]);
    } else notes.add("ى/ي yoki ة/ه farqi — namunaga qarang");
  }
  return { ok: true, exact: false, note: notes.size ? "Imlo: " + [...notes].join("; ") : undefined };
};

/** Xato javobga yo'naltiruvchi izoh (/javoblar: «تكتبان» ↔ يكتبان, «استيقظ» ↔ استيقظت, «كتبا» ↔ كتبوا). */
const PERSON_PREFIX = "اتين";
const arHint = (a: string, v: string): string | undefined => {
  if (a.length === v.length && a.slice(1) === v.slice(1) && PERSON_PREFIX.includes(a[0]) && PERSON_PREFIX.includes(v[0]))
    return "Boshidagi harf shaxsni bildiradi: أ — men, ن — biz, ت — sen/siz (va u — ayol), ي — u/ular";
  if (a.length === v.length && a.length > 1) {
    const diff = [...a].map((ch, i) => (ch !== v[i] ? i : -1)).filter((i) => i >= 0);
    // oxirgi 2 harf — qo'shimcha (كتبنا ↔ كتبوا): uni pastdagi qoida tushuntiradi
    if (diff.length === 1 && diff[0] < a.length - 2) return `Bitta harf xato: «${v[diff[0]]}» emas, «${a[diff[0]]}»`;
  }
  if (v.length >= 2 && a.length > v.length && a.length - v.length <= 3 && a.startsWith(v))
    return `Oxiridagi qo'shimcha tushib qolgan: «ـ${a.slice(v.length)}»`;
  if (v.length >= 2 && a.length > v.length && a.length - v.length <= 2 && a.endsWith(v))
    return `Boshidagi harf tushib qolgan: «${a.slice(0, a.length - v.length)}ـ»`;
  let i = 0;
  while (i < a.length && i < v.length && a[i] === v[i]) i++;
  if (i >= 3 && i < a.length && i < v.length && a.length - i <= 3 && v.length - i <= 3)
    return `Qo'shimcha boshqa: «ـ${a.slice(i)}» kerak (siz «ـ${v.slice(i)}» yozdingiz)`;
  return undefined;
};

/** To'ldirishda bo'sh joy so'zga yopishgan bo'lsa («عَلَّمَ___», «يَـ___»), o'quvchi so'zni to'liq
 *  yozishi mumkin («علمهم», «يبني») — to'ldirilgan so'z va butun gap ham to'g'ri javob. */
export const blankFills = (text: string, answer: string): string[] => {
  const BLANK = /_{2,}/;
  if (!text || !BLANK.test(text)) return [];
  const out: string[] = [];
  const word = text.split(/\s+/).find((w) => BLANK.test(w)) ?? "";
  if (normAr(word.replace(BLANK, ""))) out.push(word.replace(BLANK, answer));
  out.push(text.replace(BLANK, answer));
  return out;
};

export const arOk = (answer: string, value: string, opts: CheckOpts = {}): Verdict => {
  const v = normAr(value);
  if (!v) return { ok: false };
  const main = normAr(answer);
  if (v === main) return { ok: true, exact: true };
  const alts = (opts.accept ?? []).map(normAr).filter(Boolean);
  if (alts.includes(v)) return { ok: true, exact: false };

  const mode = opts.mode ?? "strict";
  const rules = [YA_TA];
  if (mode !== "strict") rules.push(WAW_ALIF);
  if (mode === "translate") {
    rules.push(HAMZA);
    if (!STRICT_PROMPT.test(opts.prompt ?? "")) rules.push(ARTICLE);
    rules.push(PRONOUN, SPACES);
  }
  for (const target of [main, ...alts]) {
    const r = arLoose(target, v, rules);
    if (r) return r;
  }
  return { ok: false, note: arHint(main, v) };
};

/* ── O'zbekcha (lotin) ── */

const APOS = "'ʼ’‘ʻ`´";

export const normLat = (s: string) =>
  s
    .toLowerCase()
    .replace(new RegExp(`[${APOS}\\-_.?!:;«»"“”—–…]`, "g"), "")
    .replace(/\s+/g, " ")
    .trim();

/* Kirill → lotin (o'zbek imlosi). «е» so'z boshida va unlidan keyin — «ye». */
const CYR: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", ё: "yo", ж: "j", з: "z", и: "i", й: "y", к: "k", л: "l",
  м: "m", н: "n", о: "o", п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f", х: "x", ц: "s", ч: "ch",
  ш: "sh", щ: "sh", ъ: "'", ы: "i", ь: "", э: "e", ю: "yu", я: "ya", ў: "o'", қ: "q", ғ: "g'", ҳ: "h",
};
const CYR_LETTER = /[а-яёўқғҳ]/;
const CYR_SOFT = /[аеёиоуўэюяъь]/;

export const hasCyr = (s: string) => /[Ѐ-ӿ]/.test(s);

export const cyrToLat = (s: string): string => {
  const low = s.toLowerCase();
  let out = "";
  for (let i = 0; i < low.length; i++) {
    const ch = low[i];
    if (ch === "е") {
      const prev = i ? low[i - 1] : "";
      out += !prev || !CYR_LETTER.test(prev) || CYR_SOFT.test(prev) ? "ye" : "e";
    } else out += CYR[ch] ?? ch;
  }
  return out;
};

/** Rus klaviaturasida ў/қ/ғ/ҳ yo'q — у/к/г/х teriladi: ikkala tomonni shu ko'rinishga keltiramiz. */
const ruFold = (s: string) =>
  s
    .toLowerCase()
    .replace(new RegExp(`o[${APOS}]`, "g"), "u")
    .replace(new RegExp(`g[${APOS}]`, "g"), "g")
    .replace(/q/g, "k")
    .replace(/h/g, "x");

/** Butun javob muqobillari: « / », vergul, nuqtali vergul, «yoki». */
const WHOLE_SPLIT = /\s+\/\s*|\s*\/\s+|\s*[,;]\s*|\s+yoki\s+/;

/** So'z ichidagi «/»: «men akamga/ukamga o'rgatdim» → ikkala to'liq gap. */
const expandSlashes = (s: string): string[] => {
  let acc = [""];
  for (const w of s.split(/\s+/).filter(Boolean)) {
    const alts = w.split("/").filter(Boolean);
    acc = acc.flatMap((a) => alts.map((x) => (a ? `${a} ${x}` : x))).slice(0, 24);
  }
  return acc;
};

/** "qalam / ruchka" yoki "ta'til, ruxsat" kabi javoblarda BITTA variant yetarli. */
const latVariants = (answer: string): string[] => {
  const out: string[] = [];
  const push = (s: string) =>
    s
      .split(WHOLE_SPLIT)
      .flatMap(expandSlashes)
      .map(normLat)
      .filter(Boolean)
      .forEach((v) => out.push(v));

  // Oxirgi qavs — sinonim izohi ("maktab (madrasa)"), u ham TO'G'RI javob.
  // O'rtadagi qavs esa gapning bo'lagi ("sen (ayol) yozasan") — yakka
  // o'zi javob emas, shuning uchun faqat oxirgisi variantga aylanadi.
  const tail = answer.match(/\(([^)]*)\)\s*$/);
  if (tail) push(tail[1]);
  push(answer.replace(/\([^)]*\)/g, " ")); // qavssiz asosiy javob
  push(answer.replace(/[()]/g, " ")); // qavs ichidagisi bilan: «sen ayol yozasan»
  push(answer); // qavsi bilan to'liq ko'chirgan bo'lsa ham

  return [...new Set(out)];
};

/* ── Yumshoq solishtirish (o'zbekcha javob) ──
   Aynan mos kelmasa ham TO'G'RI: qavs izohi farqi («sen (muannas) yozyapsan» = «sen (ayol) yozasan»),
   fe'l zamoni (-yapti / -moqda / -adi bir xil — arabcha muzore' ikkalasiga tarjima qilinadi),
   olmosh tushirilgan («yozasan» = «sen yozasan»), «ular keldi» = «ular keldilar», so'z tartibi,
   x/h imlosi, harf o'rni almashgan yoki qo'sh harf tushgan («diqat» = «diqqat»), «siz» hurmat shakli.
   Fe'l shaxsi va inkori (-ma-), o/u kabi ma'no o'zgartiruvchi harflar — kechirilmaydi. */
const PRONOUNS = new Set([
  "men", "sen", "u", "biz", "siz", "ular", "sizlar",
  "mening", "sening", "uning", "bizning", "sizning", "ularning",
]);
const SYNONYMS: Record<string, string> = {
  muannas: "ayol",
  muzakkar: "erkak",
  hamda: "va",
  // imlo va so'zlashuv variantlari
  qaerga: "qayerga",
  qaerda: "qayerda",
  qaerdan: "qayerdan",
  qayoqqa: "qayerga",
  qayoqda: "qayerda",
  qayda: "qayerda",
  man: "men",
  ikkisi: "ikkovi",
  ikkalasi: "ikkovi",
};
/** Fe'l o'zagi muqobillari: kutilgan → qabul qilinadigan (ذَهَبَ = bordi/ketdi, قَالَ = dedi/aytdi). */
const STEM_ALT: Record<string, string[]> = { bor: ["ket"], de: ["ayt"], ayt: ["de"] };
/** «sen» shakli o'rniga «siz» (hurmat) — qabul; teskarisi (ko'plik o'rniga birlik) — yo'q. */
const POLITE: Record<string, string> = { sen: "siz", ng: "ngiz", san: "siz" };
const PRES: Record<string, string> = { di: "ti", dilar: "tilar" }; // hozirgi zamon shaxslari: man san ti miz siz tilar
const PAST: Record<string, string> = { man: "m", san: "ng", miz: "k", siz: "ngiz" }; // -gan shaxslari → -di shaxslari

/** Fe'lni «o'zak|zamon|shaxs» ko'rinishiga keltiradi; fe'l bo'lmasa so'z o'zgarmaydi. */
const verbCanon = (w: string): string => {
  let m = w.match(/^(.{2,}?)(?:yap|mo[qk]da)(man|san|ti|di|miz|siz|tilar|dilar)?$/); // yozyapti, yozmoqda(man)
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

/** Bitta tahrir (almashtirish / qo'shish / tushirish) — uzun so'zlarda imlo xatosi deb kechiriladi. */
const lev1 = (a: string, b: string): boolean => {
  if (Math.abs(a.length - b.length) > 1) return false;
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  if (a.length === b.length) return a.slice(i + 1) === b.slice(i + 1);
  const [long, short] = a.length > b.length ? [a, b] : [b, a];
  return long.slice(i + 1) === short.slice(i);
};

const stemOk = (e: string, g: string): boolean => {
  if (e === g) return true;
  const neg = e.endsWith("ma") && g.endsWith("ma"); // bormaydi ≈ ketmaydi
  const [e0, g0] = neg ? [e.slice(0, -2), g.slice(0, -2)] : [e, g];
  return (STEM_ALT[e0] ?? []).includes(g0) || (e0.length >= 4 && typoClose(e0, g0));
};

const verbClose = (e: string, g: string): boolean => {
  const [es, et, ep] = e.split("|");
  const [gs, gt, gp] = g.split("|");
  return et === gt && stemOk(es, gs) && (ep === gp || POLITE[ep] === gp);
};

/** Kelishik qo'shimchasi almashgan («qayerga» ≠ «qayerda», «akamga» ≠ «akamni») — ma'no farqi, imlo xatosi emas. */
const CASES = ["ning", "dan", "ga", "ka", "qa", "da", "ta", "ni"];
const caseSwap = (e: string, g: string): boolean => {
  const split = (w: string) => {
    const c = CASES.find((x) => w.endsWith(x) && w.length > x.length + 1);
    return c ? [w.slice(0, -c.length), c] : [w, ""];
  };
  const [es, ec] = split(e);
  const [gs, gc] = split(g);
  return es === gs && ec !== gc;
};

/** `e` — namuna so'zi, `g` — o'quvchi so'zi. */
const wordClose = (e: string, g: string): boolean => {
  if (e === g) return true;
  const ev = e.includes("|");
  const gv = g.includes("|");
  if (ev || gv) return ev && gv && verbClose(e, g);
  if (POLITE[e] === g) return true; // sen → siz
  if (e.endsWith("ng") && g === e + "iz") return true; // isming → ismingiz
  if (e.endsWith("san") && g === e.slice(0, -3) + "siz") return true; // kimsan → kimsiz
  if (g === e + "ni" || e === g + "ni") return true; // Qur'on(ni) o'qidim
  if (g === e + "dir" || e === g + "dir") return true; // kitob yangi(dir)
  if (caseSwap(e, g)) return false;
  if (Math.max(e.length, g.length) >= 7 && Math.min(e.length, g.length) >= 5 && lev1(e, g)) return true;
  return e.length >= 4 && typoClose(e, g);
};

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

const TANVIN_NOTE = "«bir» — noaniqlik ma'nosi (tanvin ـٌ ـً ـٍ)";

const latMatch = (answer: string, typed: string, opts: CheckOpts): Verdict => {
  const raw = normLat(typed);
  if (!raw) return { ok: false };
  if (raw === normLat(answer)) return { ok: true, exact: true }; // namunani «/» yoki vergul bilan aynan ko'chirgan
  if ((opts.accept ?? []).some((a) => normLat(a) === raw)) return { ok: true, exact: false };
  // O'quvchi ham «/» bilan bir nechta variant yozgan — HAR BIRI to'g'ri bo'lishi shart
  const parts = typed.split(/\s+\/\s*|\s*\/\s+|\s+yoki\s+/).flatMap(expandSlashes);
  if (parts.length > 1) {
    const rs = parts.map((p) => latMatch(answer, p, opts));
    return rs.every((r) => r.ok) ? { ok: true, exact: false, note: rs.find((r) => r.note)?.note } : { ok: false };
  }
  const nv = raw.replace(/[,;]/g, " ").replace(/\s+/g, " ").trim(); // vergul — tinish belgisi
  const main = latVariants(answer);
  if (main.includes(nv)) return { ok: true, exact: true };
  const extra = (opts.accept ?? []).flatMap(latVariants);
  if (extra.includes(nv)) return { ok: true, exact: false };

  const all = [...main, ...extra];
  const vt = canonTokens(nv);
  if (vt.length && all.some((v) => tokensMatch(canonTokens(v), vt))) return { ok: true, exact: false };
  const squash = (s: string) => s.replace(/ /g, "");
  if (all.some((v) => squash(v) === squash(nv))) return { ok: true, exact: false }; // «ob havo» = «ob-havo»

  // «bir» (noaniqlik) faqat bir tomonda — kechiriladi, izoh bilan
  if (!STRICT_PROMPT.test(opts.prompt ?? "")) {
    const noBir = (t: string[]) => t.filter((w) => w !== "bir");
    for (const v of all) {
      const at = canonTokens(v);
      const withBir = at.includes("bir");
      if (withBir !== vt.includes("bir") && noBir(vt).length && tokensMatch(noBir(at), noBir(vt))) {
        return { ok: true, exact: false, note: withBir ? TANVIN_NOTE : undefined };
      }
    }
  }
  return { ok: false };
};

export const latOk = (answer: string, value: string, opts: CheckOpts = {}): Verdict => {
  if (!hasCyr(value)) return latMatch(answer, value, opts);
  // Kirillcha javob: avval to'g'ri o'zbek kirilli (ў қ ғ ҳ), keyin rus klaviaturasi (у к г х)
  const typed = cyrToLat(value);
  const r1 = latMatch(answer, typed, opts);
  if (r1.ok) return { ...r1, exact: false };
  const r2 = latMatch(ruFold(answer), ruFold(typed), { ...opts, accept: (opts.accept ?? []).map(ruFold) });
  return r2.ok ? { ...r2, exact: false } : r2;
};
