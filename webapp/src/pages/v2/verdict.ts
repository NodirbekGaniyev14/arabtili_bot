/** Javob qulflangach (server to'g'ri javobni ochgach) imlo izohi va «aynan emas» belgisi uchun MAHALLIY hukm (K33.2).
 *
 *  ✓/✗ ni SERVER aytadi (tests/test_answer_check_parity.py ikkalasi bir xil ekanini tekshiradi); bu yerda faqat
 *  ko'rsatish: `note` («Imlo: …», «Oxirida ـتم yetishmayapti…») va `exact === false` («Namuna: …» ko'rsatiladi).
 *  Qoidalar exercises.tsx `renderExercise` dagi bilan bir xil. */

import type { QuizInput } from "../../lib/api";
import { arOk, blankFills, isArabic, latOk, normAr, type Verdict } from "./answerCheck";
import { harakatCheck } from "./exerciseLogic";

export interface Revealed {
  type: string;
  q_uz: string;
  q_ar: string;
  answer: string;
  accept: string[];
}

export function localVerdict(item: Revealed, input: QuizInput, given: string): Verdict {
  const { answer, accept } = item;
  const opts = { accept, prompt: item.q_uz };
  switch (input) {
    case "options":
      return { ok: given === answer, exact: true };
    case "harakat":
      return harakatCheck(given, answer);
    case "order":
      return { ok: normAr(given) === normAr(answer), exact: true };
    case "self":
      return { ok: true, exact: true };
    case "lat":
      return latOk(answer, given, opts);
    default: {
      if (item.type === "translate_uz_ar") return arOk(answer, given, { ...opts, mode: "translate" });
      if (item.type === "dictation") return arOk(answer, given, { accept });
      // fill_blank: bo'sh joy so'zga yopishgan bo'lsa to'liq so'z ham to'g'ri (K27.2)
      const blank = item.q_ar || item.q_uz.match(/«([^»]*_{2,}[^»]*)»/)?.[1] || "";
      return isArabic(answer)
        ? arOk(answer, given, { ...opts, mode: "fill", accept: [...accept, ...blankFills(blank, answer)] })
        : latOk(answer, given, opts);
    }
  }
}
