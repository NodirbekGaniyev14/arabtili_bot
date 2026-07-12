export interface Option {
  id: string;
  label: string;
  icon: string;
}

export const GOALS: Option[] = [
  { id: "travel", label: "Sayohat", icon: "سفر" },
  { id: "work", label: "Ish va biznes", icon: "عمل" },
  { id: "study", label: "O'qish (universitet)", icon: "علم" },
  { id: "family", label: "Oila va do'stlar", icon: "أهل" },
  { id: "culture", label: "Madaniyat", icon: "فن" },
];

export const LEVELS: Option[] = [
  { id: "zero", label: "Noldan boshlayman", icon: "٠" },
  { id: "letters", label: "Harflarni bilaman", icon: "أب" },
  { id: "reads", label: "O'qiyman, lekin tushunmayman", icon: "قرأ" },
  { id: "speaks", label: "Biroz gaplasha olaman", icon: "كلم" },
];

export const TARGETS: Option[] = [
  { id: "read", label: "Harflarni o'qish", icon: "١" },
  { id: "understand", label: "Oddiy matnlarni tushunish", icon: "٢" },
  { id: "conversation", label: "Erkin suhbat", icon: "٣" },
  { id: "professional", label: "Professional daraja", icon: "٤" },
];

export const DURATIONS: Option[] = [
  { id: "3oy", label: "3 oy", icon: "٣" },
  { id: "6oy", label: "6 oy", icon: "٦" },
  { id: "1yil", label: "1 yil", icon: "١٢" },
  { id: "sekin", label: "Shoshilmayman", icon: "صبر" },
];

export const FOCUS: Option[] = [
  { id: "reading", label: "O'qish", icon: "قرأ" },
  { id: "writing", label: "Yozish", icon: "كتب" },
  { id: "listening", label: "Tinglash", icon: "سمع" },
  { id: "speaking", label: "Gapirish", icon: "كلم" },
  { id: "grammar", label: "Grammatika", icon: "نحو" },
  { id: "vocab", label: "Lug'at boyligi", icon: "لغة" },
];

export const MINUTES: Option[] = [
  { id: "10", label: "10 daqiqa", icon: "١٠" },
  { id: "20", label: "20 daqiqa", icon: "٢٠" },
  { id: "30", label: "30 daqiqa", icon: "٣٠" },
  { id: "60", label: "1 soat", icon: "٦٠" },
];

/* ───────────────────────── Mini-test banki ───────────────────────── */

export type Tier = "letters" | "words" | "sentences";

interface BankQuestion {
  id: string;
  tier: Tier;
  prompt: string;
  arabic?: string;
  options: string[]; // birinchisi to'g'ri javob (ko'rsatishda aralashtiriladi)
}

const BANK: BankQuestion[] = [
  { id: "l1", tier: "letters", prompt: "Bu harf qanday o'qiladi?", arabic: "ب", options: ["b", "t", "n", "s"] },
  { id: "l2", tier: "letters", prompt: "Qaysi harf «m» tovushini beradi?", options: ["م", "ن", "ت", "ك"] },
  { id: "l3", tier: "letters", prompt: "Bu qanday o'qiladi?", arabic: "بَ", options: ["ba", "bi", "bu", "ab"] },
  { id: "l4", tier: "letters", prompt: "Bu qanday o'qiladi?", arabic: "مُ", options: ["mu", "ma", "mi", "um"] },
  { id: "w1", tier: "words", prompt: "Bu so'zni o'qing:", arabic: "بَاب", options: ["bāb (eshik)", "bayt (uy)", "nab", "tabb"] },
  { id: "w2", tier: "words", prompt: "Bu so'zning ma'nosi?", arabic: "كِتَاب", options: ["kitob", "qalam", "uy", "suv"] },
  { id: "w3", tier: "words", prompt: "Bu so'zning ma'nosi?", arabic: "مَاء", options: ["suv", "non", "osmon", "qo'l"] },
  { id: "s1", tier: "sentences", prompt: "Jumla ma'nosi?", arabic: "أَنَا طَالِبٌ", options: ["Men talabaman", "U o'qituvchi", "Bu kitob", "Sen qayerdansan?"] },
  { id: "s2", tier: "sentences", prompt: "Jumla ma'nosi?", arabic: "هٰذَا بَيْتٌ كَبِيرٌ", options: ["Bu katta uy", "Bu kichkina uy", "U yangi mashina", "Bu mening kitobim"] },
  { id: "s3", tier: "sentences", prompt: "Bunga qanday javob beriladi?", arabic: "السَّلامُ عَلَيْكُم", options: ["وَعَلَيْكُمُ السَّلام", "شُكْرًا", "مَعَ السَّلامَة", "أَهْلًا"] },
];

// O'z bahosiga qarab qaysi savollar beriladi
const SELECTION: Record<string, string[]> = {
  letters: ["l1", "l2", "l3", "l4", "w1", "w2"],
  reads: ["l3", "l4", "w1", "w2", "w3", "s1", "s2"],
  speaks: ["w1", "w2", "w3", "s1", "s2", "s3"],
};

export interface PreparedQuestion {
  id: string;
  tier: Tier;
  prompt: string;
  arabic?: string;
  options: string[];
  correctIndex: number;
}

/** Darajaga mos savollarni tanlab, variantlarni aralashtirib beradi */
export function prepareTest(selfLevel: string): PreparedQuestion[] {
  const ids = SELECTION[selfLevel] ?? [];
  return ids
    .map((id) => BANK.find((q) => q.id === id))
    .filter((q): q is BankQuestion => Boolean(q))
    .map((q) => {
      const correct = q.options[0];
      const shuffled = [...q.options].sort(() => Math.random() - 0.5);
      return {
        id: q.id,
        tier: q.tier,
        prompt: q.prompt,
        arabic: q.arabic,
        options: shuffled,
        correctIndex: shuffled.indexOf(correct),
      };
    });
}

export const UZ_MONTHS = [
  "yanvar", "fevral", "mart", "aprel", "may", "iyun",
  "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
];

export function formatTargetDate(iso: string): string {
  const [y, m] = iso.split("-").map(Number);
  if (!y || !m) return iso;
  return `${UZ_MONTHS[m - 1]} ${y}`;
}
