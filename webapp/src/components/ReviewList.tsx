/** Mini-imtihon / chellenj natijasi: xato javoblar — to'g'ri javob va izoh bilan (K33).
 *
 *  Savollar javobsiz berilgani uchun to'g'ri javob faqat javoblar yuborilgach shu yerda ko'rinadi.
 *  Har xato ostida «Xatolik bormi?» — to'g'ri javobi xato hisoblangan o'quvchi adminga yozadi (K26). */

import type { ReviewItem } from "../lib/api";
import { isArabic } from "../pages/v2/answerCheck";
import ReportIssue from "./ReportIssue";

export default function ReviewList({ items, context }: { items: ReviewItem[]; context: string }) {
  if (!items.length) return null;
  return (
    <div className="w-full text-left">
      <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2">
        XATO JAVOBLAR · {items.length}
      </div>
      {items.map((r) => {
        const ctx = {
          context,
          label: `${context} · ${r.index + 1}`,
          ex_type: r.type,
          q: r.q_uz || r.q_ar,
          q_ar: r.q_ar,
          options: r.options,
          answer: r.answer,
          given: r.given,
          audio: r.audio,
        };
        const q = r.q_uz || r.q_ar;
        return (
          <div key={r.index} className="rounded-2xl bg-card border border-cardline p-3 mb-2">
            <div className="text-xs font-bold text-ink-soft">
              {r.index + 1}. {q}
            </div>
            {r.q_uz && r.q_ar && (
              <div className="mt-1 font-arabic text-2xl" dir="rtl">
                {r.q_ar}
              </div>
            )}
            <div className="mt-2 text-sm font-bold text-terracotta" dir={isArabic(r.given) ? "rtl" : "ltr"}>
              Sizning javobingiz: {r.given || "— javob berilmagan"}
            </div>
            <div
              className={`mt-1 font-bold text-emerald-deep ${isArabic(r.answer) ? "font-arabic text-xl" : "text-sm"}`}
              dir={isArabic(r.answer) ? "rtl" : "ltr"}
            >
              To'g'ri javob: {r.answer}
            </div>
            {r.explain_uz && <div className="mt-1 text-xs font-semibold text-ink-soft leading-relaxed">{r.explain_uz}</div>}
            <ReportIssue ctx={ctx} className="mt-1" />
          </div>
        );
      })}
    </div>
  );
}
