import { useEffect, useState } from "react";
import { api, type RecentWordsDay } from "../lib/api";
import { playAudio, speakText } from "../lib/audio";

/** 🆕 Yangi so'zlarim (K22.4) — kun davomida dars / AI ustoz / lug'at / o'zaklardan olingan
 *  so'zlar bitta joyda, kunlar bo'yicha (bugun, kecha, …), 🔊 bilan. Foydalanuvchi so'rovi:
 *  «kunlik yangi so'zlarni bir joyga jamlash kerak». Hammasi SRS kartotekasida — «Takrorlash»
 *  shu so'zlarni ham qaytaradi. */

interface Props {
  goal: number;
  onClose: () => void;
  onOpenVocab: () => void;
  onGoReview: () => void;
}

function label(day: string, i: number): string {
  if (i === 0) return "Bugun";
  if (i === 1) return "Kecha";
  const [, m, d] = day.split("-");
  return `${d}.${m}`;
}

const SOURCE: Record<string, string> = { word: "so'z", phrase: "ibora", root: "o'zak", pattern: "vazn", letter: "harf" };

export default function TodayWords({ goal, onClose, onOpenVocab, onGoReview }: Props) {
  const [days, setDays] = useState<RecentWordsDay[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .recentWords(7)
      .then((r) => setDays(r.days))
      .catch(() => setError("Yuklanmadi — internetni tekshiring"));
  }, []);

  const today = days?.[0]?.day === new Date(Date.now() + 5 * 3600e3).toISOString().slice(0, 10) ? days[0] : null;
  const todayCount = today?.words.length ?? 0;
  const total = days?.reduce((s, d) => s + d.words.length, 0) ?? 0;

  return (
    <div className="fixed inset-0 z-50 bg-sand flex flex-col max-w-md mx-auto">
      <div className="flex items-center justify-between px-4 py-3 border-b border-cardline bg-card">
        <div>
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">🆕 YANGI SO'ZLARIM</div>
          <div className="font-extrabold">
            Bugun {todayCount}/{goal} · 7 kunda {total} ta
          </div>
        </div>
        <button onClick={onClose} className="w-9 h-9 rounded-full bg-cardline text-ink-soft font-extrabold">
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3 pb-10">
        {error && (
          <div className="rounded-2xl bg-terracotta/10 border border-terracotta/30 px-4 py-3 text-sm font-semibold">{error}</div>
        )}

        {days && todayCount < goal && (
          <button
            onClick={onOpenVocab}
            className="w-full rounded-2xl bg-emerald-deep py-3.5 text-white font-extrabold active:scale-[0.98] transition-transform"
          >
            ➕ Yangi so'z o'rganish — lug'at bo'limi ({goal - todayCount} ta qoldi)
          </button>
        )}

        {days && days.length === 0 && (
          <div className="rounded-3xl bg-card border border-cardline p-5 text-center">
            <div className="text-4xl">📭</div>
            <div className="mt-2 font-extrabold">So'nggi 7 kunda yangi so'z yo'q</div>
            <p className="mt-1 text-[12px] text-ink-soft font-semibold">
              Dars o'ting yoki lug'atdan so'z belgilang — shu yerda to'planadi.
            </p>
          </div>
        )}

        {days?.map((d, i) => (
          <section key={d.day} className="rounded-3xl bg-card border border-cardline p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">
                {label(d.day, i).toUpperCase()} · {d.words.length} TA
              </div>
              {i === 0 && d.words.length >= goal && <span className="text-[11px] font-extrabold text-emerald-dark">✅ me'yor</span>}
            </div>
            <ul className="divide-y divide-cardline">
              {d.words.map((w) => (
                <li key={w.ar} className="flex items-center gap-3 py-2">
                  <button
                    onClick={() => (w.audio ? playAudio(w.audio) : speakText(w.ar))}
                    className="w-9 h-9 shrink-0 rounded-xl bg-gold-soft text-sm font-extrabold active:scale-90 transition-transform"
                    aria-label="Tinglash"
                  >
                    🔊
                  </button>
                  <div className="min-w-0 flex-1">
                    <div className="font-arabic text-xl leading-snug" dir="rtl">
                      {w.ar}
                    </div>
                    <div className="text-[12px] text-ink-soft font-semibold truncate">
                      {w.translit && <span className="italic">{w.translit} · </span>}
                      {w.uz}
                    </div>
                  </div>
                  <span className="shrink-0 rounded-md bg-cardline px-1.5 py-0.5 text-[10px] font-extrabold text-ink-soft">
                    {SOURCE[w.kind] ?? w.kind}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ))}

        {days && days.length > 0 && (
          <button
            onClick={onGoReview}
            className="w-full rounded-2xl bg-card border border-cardline py-3.5 font-extrabold active:scale-[0.98] transition-transform"
          >
            🔁 Takrorlash (SRS) — bu so'zlar ham kartotekada
          </button>
        )}
      </div>
    </div>
  );
}
