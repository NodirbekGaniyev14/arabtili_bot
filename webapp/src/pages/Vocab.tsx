/** Lug'at 2.0 (K24) — darajalar → mavzular → fleshkarta sessiyasi (vocab/VocabSession).
 *
 *  Bosh ekran: darajalar kartalari (so'z soni, mavzular, o'rganilgan progress), «Davom etish»
 *  (oxirgi mavzu), qidiruv (6000 so'zlik baza — natija kartalari vocab/WordCard). */

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type VocabLevels, type VocabWord } from "../lib/api";
import VocabSession from "./vocab/VocabSession";
import VocabTopics from "./vocab/VocabTopics";
import WordCard from "./vocab/WordCard";
import { ProgressBar, haptic, levelBg, loadLast, type VocabLast } from "./vocab/vocabUi";

type View = { v: "levels" } | { v: "topics"; level: string };

/** `onClose` berilsa — to'liq ekran qoplamasi sifatida ochilgan (✕ ko'rinadi). */
export default function Vocab({ onClose }: { onClose?: () => void }) {
  const [view, setView] = useState<View>({ v: "levels" });
  const [session, setSession] = useState<{ level: string; topic: string } | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const openTopics = (level: string) => {
    haptic.tap();
    setView({ v: "topics", level });
    window.scrollTo({ top: 0 });
  };

  const body =
    view.v === "levels" ? (
      <Levels
        refreshKey={refreshKey}
        onClose={onClose}
        onOpen={openTopics}
        onContinue={(last) => setSession({ level: last.level, topic: last.topic })}
      />
    ) : (
      <VocabTopics
        level={view.level}
        refreshKey={refreshKey}
        onBack={() => setView({ v: "levels" })}
        onStart={(topic) => setSession({ level: view.level, topic })}
      />
    );

  return (
    <div className={onClose ? "fixed inset-0 z-30 bg-sand overflow-y-auto" : undefined}>
      <div className={onClose ? "max-w-md mx-auto pb-24" : "pb-4"}>{body}</div>
      {/* Sessiya — portal: pastki menyu (NavBar) va sahifa qatlamlaridan ustun turadi */}
      {session &&
        createPortal(
          <VocabSession
            key={`${session.level}-${session.topic}`}
            level={session.level}
            topic={session.topic}
            onClose={(changed) => {
              setSession(null);
              if (changed) setRefreshKey((k) => k + 1);
            }}
          />,
          document.body
        )}
    </div>
  );
}

function Levels({
  refreshKey,
  onClose,
  onOpen,
  onContinue,
}: {
  refreshKey: number;
  onClose?: () => void;
  onOpen: (level: string) => void;
  onContinue: (last: VocabLast) => void;
}) {
  const [data, setData] = useState<VocabLevels | null>(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [results, setResults] = useState<VocabWord[] | null>(null);
  const [total, setTotal] = useState(0);
  const [searching, setSearching] = useState(false);
  const last = loadLast();

  useEffect(() => {
    api
      .vocabLevels()
      .then(setData)
      .catch(() => setError("Yuklanmadi — internetni tekshiring"));
  }, [refreshKey]);

  // Qidiruv — kechiktirib (har harfda so'rov ketmasin)
  const timer = useRef<number | null>(null);
  useEffect(() => {
    if (timer.current) window.clearTimeout(timer.current);
    if (!q.trim()) {
      setResults(null);
      return;
    }
    setSearching(true);
    timer.current = window.setTimeout(() => {
      api
        .searchVocabBase(q.trim())
        .then((r) => {
          setResults(r.items);
          setTotal(r.total);
        })
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 300);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [q]);

  return (
    <div className="px-4 pt-5">
      <div className="flex items-start gap-3">
        {onClose && (
          <button onClick={onClose} className="mt-1 text-2xl text-ink-soft font-bold leading-none active:opacity-60">
            ✕
          </button>
        )}
        <div className="min-w-0 flex-1">
          <div className="font-arabic text-lg text-emerald-deep leading-none" dir="rtl">
            المُفْرَدَات
          </div>
          <h1 className="text-2xl font-extrabold leading-tight">Lug'at</h1>
          <p className="text-[12px] font-semibold text-ink-soft">
            {data ? `${data.total} so'z · ${data.learned} o'rganildi · darajani tanlang` : "Darajani tanlang"}
          </p>
        </div>
      </div>

      {/* Qidiruv */}
      <div className="relative mt-3">
        <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-soft">🔍</span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="So'z izlash: kitob, كتاب, ك ت ب…"
          className="w-full rounded-2xl border border-cardline bg-card pl-10 pr-10 py-3 text-[15px] font-semibold outline-none focus:border-emerald-deep"
        />
        {q && (
          <button
            onClick={() => setQ("")}
            className="absolute right-3 top-1/2 -translate-y-1/2 w-7 h-7 rounded-full bg-cardline text-ink-soft text-xs font-extrabold"
            aria-label="Tozalash"
          >
            ✕
          </button>
        )}
      </div>

      {results !== null ? (
        <div className="mt-3">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
            {searching ? "IZLANMOQDA…" : `${total} SO'Z`}
          </div>
          {!searching && results.length === 0 && (
            <div className="mt-8 text-center text-ink-soft font-semibold">
              <div className="text-4xl mb-2">🔍</div>
              Hech narsa topilmadi. Boshqa so'z bilan urinib ko'ring.
            </div>
          )}
          <div className="mt-2 space-y-2">
            {results.map((w) => (
              <WordCard key={w.id} word={w} />
            ))}
            {total > results.length && (
              <p className="text-center text-xs text-ink-soft font-semibold pt-2">
                {results.length} / {total} ko'rsatildi — qidiruvni aniqlashtiring
              </p>
            )}
          </div>
        </div>
      ) : (
        <>
          {error && (
            <div className="mt-4 rounded-2xl bg-terracotta/10 border border-terracotta/30 px-4 py-3 text-sm font-semibold">
              {error}
            </div>
          )}

          {last && (
            <button
              onClick={() => {
                haptic.tap();
                onContinue(last);
              }}
              className="mt-3 w-full flex items-center gap-3 rounded-2xl bg-gold-soft border border-gold/30 px-4 py-3 text-left active:scale-[0.99] transition-transform"
            >
              <span className="w-10 h-10 shrink-0 rounded-xl bg-emerald-deep text-white flex items-center justify-center text-lg">▶</span>
              <div className="min-w-0 flex-1">
                <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">DAVOM ETISH</div>
                <div className="text-[14px] font-extrabold truncate">
                  {last.level} · {last.title}
                </div>
              </div>
              <span className="text-xl font-extrabold text-ink-soft">›</span>
            </button>
          )}

          <div className="mt-3 grid grid-cols-2 gap-3">
            {(data?.levels ?? []).map((lv) => (
              <button
                key={lv.level}
                onClick={() => onOpen(lv.level)}
                className="relative overflow-hidden rounded-3xl p-4 pb-5 text-left text-white shadow-md min-h-[148px] flex flex-col active:scale-[0.98] transition-transform"
                style={levelBg(lv.level)}
              >
                <span className="pointer-events-none absolute right-3 top-3 font-arabic text-[15px] text-white/35" dir="rtl">
                  {lv.title_ar}
                </span>
                {/* bezak — ustunchalar */}
                <span className="pointer-events-none absolute right-3 bottom-4 flex items-end gap-1 opacity-20">
                  <span className="w-2.5 h-4 rounded-sm bg-white" />
                  <span className="w-2.5 h-7 rounded-sm bg-white" />
                  <span className="w-2.5 h-10 rounded-sm bg-white" />
                </span>
                <span className="text-[34px] font-extrabold leading-none mt-4">{lv.level}</span>
                {/* qat'iy rang: kartalar ikkala mavzuda ham yashil — gold-soft tokeni qorong'ida to'q bo'lib qoladi */}
                <span className="mt-1 text-[13px] font-extrabold text-[#f3e8c8]">{lv.title_uz}</span>
                <span className="mt-auto pt-3 text-[11px] font-semibold text-white/75">
                  {lv.topics} mavzu · {lv.total} so'z
                </span>
                {lv.learned > 0 && (
                  <span className="text-[11px] font-extrabold text-white">✓ {lv.learned} o'rganildi</span>
                )}
                <span className="absolute left-0 right-0 bottom-0">
                  <ProgressBar value={lv.learned} max={lv.total} className="h-1.5 bg-white/15 rounded-none" fill="bg-gold" />
                </span>
              </button>
            ))}
            {!data &&
              !error &&
              [0, 1, 2, 3, 4].map((i) => <div key={i} className="min-h-[148px] rounded-3xl bg-card border border-cardline animate-pulse" />)}
          </div>

          <div className="mt-4 rounded-2xl bg-card border border-cardline px-4 py-3 text-[12px] font-semibold text-ink-soft">
            💡 Har mavzuda: <b className="text-ink">5 ta so'z</b> bilan tanishasiz → eslaysiz («Bildim / Bilmadim») → yana 5 ta →{" "}
            <b className="text-ink">10 savollik test</b>. O'rganilgan so'zlar «Takror» bo'limida qaytib keladi.
          </div>
        </>
      )}
    </div>
  );
}
