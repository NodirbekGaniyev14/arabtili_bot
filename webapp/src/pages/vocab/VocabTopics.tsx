/** Lug'at 2.0 (K24) — daraja ichidagi mavzular: «Aralash» (butun daraja) + raqamlangan mavzular. */

import { useEffect, useState } from "react";
import { api, type VocabTopicList } from "../../lib/api";
import { ProgressBar, haptic, levelBg } from "./vocabUi";

interface Props {
  level: string;
  refreshKey: number;
  onBack: () => void;
  onStart: (topic: string) => void;
}

export default function VocabTopics({ level, refreshKey, onBack, onStart }: Props) {
  const [data, setData] = useState<VocabTopicList | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    api
      .vocabTopics(level)
      .then(setData)
      .catch(() => setError("Yuklanmadi — internetni tekshiring"));
  }, [level, refreshKey]);

  const start = (slug: string) => {
    haptic.tap();
    onStart(slug);
  };

  return (
    <div className="px-4 pt-4 pb-6">
      <div className="flex items-center gap-3">
        <button
          onClick={onBack}
          className="w-10 h-10 shrink-0 rounded-full bg-card border border-cardline text-lg font-extrabold active:scale-95"
          aria-label="Orqaga"
        >
          ←
        </button>
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
            {level} · {data?.title_uz ?? ""}
          </div>
          <h1 className="text-xl font-extrabold leading-tight">Mavzuni tanlang</h1>
        </div>
        {data && (
          <span className="font-arabic text-xl text-emerald-deep/70 shrink-0" dir="rtl">
            {data.title_ar}
          </span>
        )}
      </div>

      {error && (
        <div className="mt-4 rounded-2xl bg-terracotta/10 border border-terracotta/30 px-4 py-3 text-sm font-semibold">{error}</div>
      )}

      {!data && !error && (
        <div className="mt-4 space-y-2.5">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="h-[74px] rounded-2xl bg-card border border-cardline animate-pulse" />
          ))}
        </div>
      )}

      {data && (
        <>
          <p className="mt-1 text-[12px] font-semibold text-ink-soft">
            📘 {data.total} so'z · {data.learned} o'rganildi · har mavzuda 10 tadan: fleshkarta → test
          </p>

          {/* Aralash — butun daraja */}
          <button
            onClick={() => start("all")}
            className="relative mt-4 w-full overflow-hidden rounded-3xl p-4 text-left text-white shadow-md active:scale-[0.99] transition-transform"
            style={levelBg(level)}
          >
            <span className="pointer-events-none absolute -right-3 -bottom-4 text-[88px] leading-none text-white/10">✦</span>
            <div className="flex items-center gap-3.5">
              <span className="w-14 h-14 shrink-0 rounded-2xl bg-white/15 flex items-center justify-center text-2xl">✨</span>
              <div className="min-w-0 flex-1">
                <div className="text-[18px] font-extrabold leading-tight">Aralash — {level}</div>
                <div className="text-[12px] font-semibold text-white/75">Butun daraja bo'yicha · {data.total} so'z</div>
              </div>
              <span className="text-2xl font-extrabold text-white/70">›</span>
            </div>
            <ProgressBar value={data.learned} max={data.total} className="mt-3 h-1.5 bg-white/20" fill="bg-gold" />
          </button>

          {/* Mavzular */}
          <div className="mt-3 space-y-2.5">
            {data.topics.map((t, i) => {
              const complete = t.learned >= t.total;
              return (
                <button
                  key={t.slug}
                  onClick={() => start(t.slug)}
                  className="w-full rounded-2xl bg-card border border-cardline px-3.5 pt-3 pb-2.5 text-left active:scale-[0.99] transition-transform"
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`w-11 h-11 shrink-0 rounded-xl flex items-center justify-center text-[15px] font-extrabold ${
                        complete ? "bg-gold text-white" : "bg-emerald-deep/10 text-emerald-deep"
                      }`}
                    >
                      {complete ? "✓" : i + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="font-arabic text-[21px] leading-snug text-emerald-dark text-right truncate" dir="rtl">
                        {t.title_ar}
                      </div>
                      <div className="text-[13px] font-extrabold truncate">
                        <span className="mr-1">{t.icon}</span>
                        {t.title_uz}
                      </div>
                    </div>
                    <span className="shrink-0 rounded-full bg-sand border border-cardline px-2.5 py-1 text-[11px] font-extrabold text-ink-soft">
                      {t.learned > 0 ? `${t.learned}/${t.total}` : `${t.total} so'z`}
                    </span>
                  </div>
                  {t.learned > 0 && (
                    <ProgressBar
                      value={t.learned}
                      max={t.total}
                      className="mt-2.5 h-1 bg-cardline"
                      fill={complete ? "bg-gold" : "bg-emerald-deep"}
                    />
                  )}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
