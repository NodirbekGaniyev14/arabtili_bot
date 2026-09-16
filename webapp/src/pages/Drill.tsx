import { useEffect, useRef, useState } from "react";
import {
  api,
  type DrillFinish,
  type DrillItem,
  type DrillStart,
  type TutorPronounceResult,
  type TutorTopic,
} from "../lib/api";
import { playUrl, speakText } from "../lib/audio";
import { MAX_SECONDS, Recorder } from "../lib/recorder";
import RateBar from "../components/RateBar";

/** Talaffuz mashqi — AI'siz, bepul: mavzu bo'yicha 10 ta jumla.
 *
 *  Har jumla: 🔊 eshit → 🎤 ayt → o'xshashlik bali (Groq STT + solishtirish).
 *  Aytilmagan so'zlar qizil chiziladi. Yakunda o'rtacha ball va XP (kamida
 *  5 jumla, bir mavzu uchun kuniga bir marta). Haiku sarfi yo'q.
 */

const tg = () => window.Telegram?.WebApp;

interface DrillProps {
  topic: TutorTopic;
  level: string;
  canVoice: boolean;
  onClose: () => void;
  /** Yakunlangach (XP tushdi) — ustoz sahifasi ma'lumotini yangilash */
  onFinished?: () => void;
}

const PASS = 80;

function scoreColor(s: number) {
  return s >= PASS ? "bg-emerald-deep text-white" : s >= 50 ? "bg-gold text-white" : "bg-terracotta text-white";
}

export default function Drill({ topic, level, canVoice, onClose, onFinished }: DrillProps) {
  const [data, setData] = useState<DrillStart | null>(null);
  const [error, setError] = useState("");
  const [idx, setIdx] = useState(0);
  const [results, setResults] = useState<Record<number, TutorPronounceResult>>({});
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [finish, setFinish] = useState<DrillFinish | null>(null);
  const [finishing, setFinishing] = useState(false);
  const [notice, setNotice] = useState("");
  const [showHelp, setShowHelp] = useState(() => !["B1", "B2"].includes(level));
  const recorder = useRef(new Recorder());

  const load = () => {
    setData(null);
    setError("");
    setIdx(0);
    setResults({});
    setFinish(null);
    api
      .tutorDrill(topic.id)
      .then(setData)
      .catch(() => setError("Jumlalar yuklanmadi. Qayta urinib ko'ring."));
  };

  useEffect(() => {
    load();
    const r = recorder.current;
    return () => {
      if (r.active) r.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topic.id]);

  useEffect(() => {
    if (!recording) return;
    setSeconds(0);
    const id = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [recording]);

  const item: DrillItem | undefined = data?.items[idx];
  const total = data?.items.length ?? 0;
  const result = results[idx];

  const speak = (it?: DrillItem) => {
    if (!it) return;
    playUrl(it.audio_url).then((ok) => {
      if (!ok) speakText(it.ar);
    });
  };

  // Keyingi jumlaga o'tganda avtomatik eshittiramiz (tugma bosilgan — ruxsat bor)
  const goTo = (i: number) => {
    setIdx(i);
    setNotice("");
    const it = data?.items[i];
    if (it) speak(it);
  };

  const startRec = async () => {
    if (!item || recording || busy) return;
    try {
      await recorder.current.start(() => stopRec());
      setRecording(true);
      tg()?.HapticFeedback?.impactOccurred("medium");
    } catch {
      setNotice("Mikrofonga ruxsat berilmadi.");
    }
  };

  const stopRec = async () => {
    if (!data || !item) return;
    const rec = await recorder.current.stop();
    setRecording(false);
    if (!rec) {
      setNotice("Yozuv juda qisqa. Qayta urinib ko'ring.");
      return;
    }
    setBusy(true);
    setNotice("");
    try {
      const r = await api.tutorPronounce(rec.blob, rec.filename, item.ar, {
        key: data.key,
        idx: item.idx,
      });
      setResults((rs) => {
        const prev = rs[item.idx];
        // Eng yaxshi urinish ko'rsatiladi (server ham shunday hisoblaydi)
        return prev && prev.score > r.score ? rs : { ...rs, [item.idx]: r };
      });
      tg()?.HapticFeedback?.notificationOccurred(r.score >= PASS ? "success" : "warning");
    } catch (e) {
      const err = e as { status?: number; detail?: string };
      if (err?.status === 404) {
        setNotice("Mashq muddati tugadi — qaytadan boshlang.");
      } else {
        setNotice(err?.detail || "Ovoz xizmati javob bermadi.");
      }
    } finally {
      setBusy(false);
    }
  };

  const finishDrill = async () => {
    if (!data || finishing) return;
    if (recorder.current.active) await recorder.current.stop();
    setFinishing(true);
    try {
      const f = await api.tutorDrillFinish(data.key);
      setFinish(f);
      if (f.xp > 0) tg()?.HapticFeedback?.notificationOccurred("success");
      onFinished?.();
    } catch {
      setNotice("Natija saqlanmadi. Qayta urinib ko'ring.");
    } finally {
      setFinishing(false);
    }
  };

  const scoredCount = Object.keys(results).length;
  const isLast = idx >= total - 1;

  // ── Yakun ──
  if (finish) {
    const rows = finish.items
      .map((it, i) => ({ ...it, score: finish.scores[i] }))
      .sort((a, b) => (a.score < 0 ? 1 : b.score < 0 ? -1 : a.score - b.score));
    return (
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <div className="rounded-3xl bg-gradient-to-br from-emerald-deep to-emerald-dark p-5 text-white text-center shadow-lg">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-gold-soft">
            🎤 TALAFFUZ · {topic.title_uz.toUpperCase()}
          </div>
          <div className="text-5xl font-extrabold mt-1">{finish.score}%</div>
          <div className="text-sm font-semibold text-white/85 mt-1">
            {finish.count}/{finish.total} jumla aytildi
            {finish.xp > 0 ? ` · +${finish.xp} XP` : finish.count < 5 ? " · XP uchun kamida 5 ta" : ""}
          </div>
          {finish.xp === 0 && finish.count >= 5 && (
            <div className="text-[11px] text-white/70 mt-1">
              Bu mavzu uchun bugungi XP allaqachon olingan
            </div>
          )}
        </div>

        {data && finish.count > 0 && (
          <RateBar sessionKey={data.key} mode="drill" topic={topic.id} question="Talaffuz bahosi to'g'rimi?" />
        )}

        <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">
          JUMLALAR (avval qiyinlari)
        </div>
        {rows.map((r, i) => (
          <div key={i} className="rounded-2xl bg-card border border-cardline px-4 py-3">
            <div className="flex items-start gap-2">
              <span
                className={`shrink-0 rounded-lg px-2 py-0.5 text-[11px] font-extrabold ${
                  r.score < 0 ? "bg-cardline text-ink-soft" : scoreColor(r.score)
                }`}
              >
                {r.score < 0 ? "—" : `${r.score}%`}
              </span>
              <div className="min-w-0 flex-1">
                <div className="font-arabic text-xl leading-relaxed" dir="rtl">
                  {r.ar}
                </div>
                <div className="text-xs text-ink-soft font-semibold">{r.uz}</div>
              </div>
            </div>
          </div>
        ))}

        <div className="grid grid-cols-2 gap-2 pt-1">
          <button
            onClick={load}
            className="rounded-2xl bg-emerald-deep py-3 text-sm font-extrabold text-white active:scale-95 transition-transform"
          >
            🔁 Yana mashq
          </button>
          <button
            onClick={onClose}
            className="rounded-2xl bg-card border border-cardline py-3 text-sm font-extrabold active:scale-95 transition-transform"
          >
            Mavzular
          </button>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 p-6 text-center">
        <div className="text-ink-soft font-semibold">{error}</div>
        <button onClick={load} className="rounded-xl bg-emerald-deep px-4 py-2 text-sm font-extrabold text-white">
          Qayta urinish
        </button>
      </div>
    );
  }

  if (!data || !item) {
    return (
      <div className="flex-1 flex items-center justify-center text-sm text-ink-soft font-semibold">
        Jumlalar tayyorlanmoqda…
      </div>
    );
  }

  return (
    <>
      {/* Progress */}
      <div className="flex items-center gap-2 px-4 py-2 bg-card border-b border-cardline">
        <div className="flex-1 flex gap-1">
          {data.items.map((it, i) => {
            const s = results[it.idx]?.score;
            return (
              <button
                key={it.idx}
                onClick={() => goTo(i)}
                className={`h-1.5 flex-1 rounded-full transition-colors ${
                  s === undefined
                    ? i === idx
                      ? "bg-ink/40"
                      : "bg-cardline"
                    : s >= PASS
                      ? "bg-emerald-deep"
                      : s >= 50
                        ? "bg-gold"
                        : "bg-terracotta"
                }`}
                aria-label={`Jumla ${i + 1}`}
              />
            );
          })}
        </div>
        <span className="text-[11px] font-extrabold text-ink-soft">
          {idx + 1}/{total}
        </span>
        <button
          onClick={() => setShowHelp((v) => !v)}
          className={`h-7 px-2.5 rounded-full text-[11px] font-extrabold border ${
            showHelp ? "bg-emerald-deep text-white border-emerald-deep" : "bg-card text-ink-soft border-cardline"
          }`}
        >
          Aa
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {!canVoice && (
          <div className="rounded-2xl bg-gold-soft border border-gold/30 p-3 text-sm font-semibold">
            Mikrofon yo'q yoki ovoz xizmati sozlanmagan — jumlalarni eshitib takrorlang, baholash
            keyinroq.
          </div>
        )}

        {/* So'z */}
        <div className="inline-flex items-center gap-2 rounded-full bg-card border border-cardline px-3 py-1 text-xs font-bold">
          <span className="font-arabic text-base">{item.word.ar}</span>
          <span className="text-ink-soft">
            {item.word.translit} · {item.word.uz}
          </span>
        </div>

        {/* Jumla kartasi */}
        <div className="rounded-3xl bg-card border border-cardline p-5 shadow-sm">
          <div className="font-arabic text-3xl leading-[1.9]" dir="rtl">
            {result
              ? result.words.map((w, i) => (
                  <span key={i} className={w.ok ? "" : "text-terracotta underline decoration-2"}>
                    {w.ar}{" "}
                  </span>
                ))
              : item.ar}
          </div>
          {showHelp && (
            <>
              <div className="text-sm text-ink-soft font-semibold mt-2 italic">{item.translit}</div>
              <div className="text-sm font-semibold mt-1">{item.uz}</div>
            </>
          )}

          <div className="mt-4 flex items-center gap-2 flex-wrap">
            <button
              onClick={() => speak(item)}
              className="h-10 px-4 rounded-xl bg-gold-soft text-sm font-extrabold active:scale-95 transition-transform"
            >
              🔊 Eshitish
            </button>
            {result && (
              <span className={`h-10 inline-flex items-center px-3 rounded-xl text-sm font-extrabold ${scoreColor(result.score)}`}>
                🎯 {result.score}%
              </span>
            )}
          </div>
          {result && result.score < PASS && result.transcript && (
            <div className="mt-2 text-[12px] text-ink-soft font-semibold" dir="rtl">
              Eshitildi: {result.transcript}
            </div>
          )}
          {result && (
            <div className="mt-2 text-xs font-bold text-ink-soft">
              {result.score >= PASS
                ? "Zo'r! Keyingi jumlaga o'ting."
                : result.score >= 50
                  ? "Yaxshi. Qizil so'zlarga e'tibor berib, yana urinib ko'ring."
                  : "Sekinroq va aniqroq ayting — avval eshitib oling."}
            </div>
          )}
        </div>

        {notice && (
          <div className="rounded-2xl bg-gold-soft border border-gold/30 p-3 text-sm font-semibold">{notice}</div>
        )}
      </div>

      {/* Boshqaruv */}
      <div className="p-3 border-t border-cardline bg-card space-y-2">
        {recording ? (
          <button
            onClick={stopRec}
            className="w-full flex items-center gap-3 rounded-2xl bg-terracotta text-white px-4 py-3.5 font-extrabold active:scale-[0.98] transition-transform"
          >
            <span className="w-3 h-3 rounded-full bg-white animate-pulse" />
            <span className="flex-1 text-left">
              Gapiring… {seconds}s / {MAX_SECONDS}s
            </span>
            <span>■ Tayyor</span>
          </button>
        ) : (
          <div className="flex items-center gap-2">
            {canVoice && (
              <button
                onClick={startRec}
                disabled={busy}
                className="flex-1 h-12 rounded-2xl bg-emerald-deep text-white text-sm font-extrabold active:scale-[0.98] transition-transform disabled:opacity-50"
              >
                {busy ? "🎧 Eshitilmoqda…" : result ? "🎤 Yana ayting" : "🎤 Ayting"}
              </button>
            )}
            <button
              onClick={() => (isLast ? finishDrill() : goTo(idx + 1))}
              disabled={busy || finishing}
              className={`h-12 px-4 rounded-2xl text-sm font-extrabold active:scale-[0.98] transition-transform disabled:opacity-50 ${
                canVoice ? "" : "flex-1"
              } ${
                result || !canVoice
                  ? "bg-gold-soft text-ink"
                  : "bg-card border border-cardline text-ink-soft"
              }`}
            >
              {isLast ? (finishing ? "…" : "Yakunlash ✓") : result || !canVoice ? "Keyingi →" : "O'tkazish →"}
            </button>
          </div>
        )}
        <div className="flex items-center justify-between text-[11px] font-bold text-ink-soft px-0.5">
          <span>{scoredCount} ta aytildi · XP uchun kamida 5</span>
          {scoredCount > 0 && !isLast && (
            <button
              onClick={finishDrill}
              disabled={finishing}
              className="font-extrabold text-emerald-dark underline underline-offset-4 disabled:opacity-40"
            >
              Yakunlash ✓
            </button>
          )}
        </div>
      </div>
    </>
  );
}
