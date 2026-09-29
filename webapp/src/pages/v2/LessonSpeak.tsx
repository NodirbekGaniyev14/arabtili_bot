/** 🗣 Dars GAPIRISH fazasi (K28) — bot endi haqiqatan eshitadi.
 *
 *  Ilgari faza faqat «Ovoz chiqarib o'qing» + «✓ O'qib chiqdim» edi — mikrofon yo'q, bot hech narsani
 *  eshitmasdi (egasi, 2026-09-28). Endi har namuna: 🔊 namuna → 🎤 ayting (ovoz shkalasi ko'rinadi) →
 *  server STT + solishtirish (harf nomi / bo'g'in / so'z / gap) → 🎯 ball, so'zlar rangi, «Eshitildi: …», maslahat.
 *  Mikrofon yo'q yoki ovoz xizmati o'chiq bo'lsa — eski oqim (o'qib chiqish), dars to'xtamaydi. */

import { useEffect, useRef, useState } from "react";
import { api, wordClass, type LessonSpeakResult, type LessonV2Data } from "../../lib/api";
import { playUrl, speakText } from "../../lib/audio";
import { Recorder, SILENT_MSG, isSilent, micSupported } from "../../lib/recorder";
import ArabicText from "./ArabicText";

const tg = () => window.Telegram?.WebApp;
const PASS = 80;
const MAX_SECONDS = 20; // bitta namuna uchun yetarli; STT limiti tejaladi

function scoreColor(s: number) {
  return s >= PASS ? "bg-emerald-deep text-white" : s >= 50 ? "bg-gold text-white" : "bg-terracotta text-white";
}

export default function LessonSpeak({
  lesson,
  lookup,
  onNext,
}: {
  lesson: LessonV2Data;
  lookup: Map<string, { ar: string; uz: string }>;
  onNext: () => void;
}) {
  const sp = lesson.skills.speaking;
  const targets = sp.target_ar ?? [];
  const canVoice = !!lesson.voice && micSupported();
  const recorder = useRef(new Recorder());
  const [active, setActive] = useState<number | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [quiet, setQuiet] = useState(false);
  const [results, setResults] = useState<Record<number, LessonSpeakResult>>({});
  const [notice, setNotice] = useState<Record<number, string>>({});

  useEffect(() => {
    const r = recorder.current;
    return () => {
      if (r.active) void r.stop(0);
    };
  }, []);

  // Yozish paytida: soniya va ovoz shkalasi («bot eshityaptimi?» — ko'rinib turadi)
  useEffect(() => {
    if (active === null) return;
    const t0 = Date.now();
    let loudSeen = false;
    setSeconds(0);
    setQuiet(false);
    const id = window.setInterval(() => {
      const r = recorder.current;
      const sec = Math.floor((Date.now() - t0) / 1000);
      setSeconds(sec);
      setLevel(r.level);
      if (r.level > 0.06) loudSeen = true;
      setQuiet(r.metering && !loudSeen && sec >= 2);
    }, 120);
    return () => {
      window.clearInterval(id);
      setLevel(0);
    };
  }, [active]);

  const say = (i: number, text: string) => setNotice((n) => ({ ...n, [i]: text }));

  const listen = (i: number) => {
    playUrl(api.lessonSpeakAudioUrl(lesson.id, i)).then((ok) => {
      if (!ok) speakText(targets[i]);
    });
  };

  const stop = async (i: number) => {
    const rec = await recorder.current.stop();
    setActive(null);
    if (!rec) {
      say(i, "Yozuv juda qisqa — 🎤 ni bosing, gapirib bo'lgach «■ Tayyor» ni bosing.");
      return;
    }
    if (isSilent(rec)) {
      say(i, SILENT_MSG);
      return;
    }
    setBusy(i);
    try {
      const r = await api.lessonSpeak(lesson.id, i, rec.blob, rec.filename);
      setResults((rs) => ({ ...rs, [i]: r }));
      tg()?.HapticFeedback?.notificationOccurred(r.score >= PASS ? "success" : "warning");
    } catch (e) {
      say(i, (e as { detail?: string })?.detail || "Ovoz xizmati javob bermadi — qayta urinib ko'ring.");
    } finally {
      setBusy(null);
    }
  };

  const start = async (i: number) => {
    if (active !== null || busy !== null) return;
    say(i, "");
    try {
      await recorder.current.start(() => void stop(i), MAX_SECONDS);
      setActive(i);
      tg()?.HapticFeedback?.impactOccurred("medium");
    } catch {
      say(i, "Mikrofonga ruxsat berilmadi — Telegram so'raganda «Ruxsat berish» ni bosing.");
    }
  };

  const done = Object.keys(results).length;

  return (
    <div className="pt-4">
      <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2">🗣 GAPIRISH</div>
      <p className="text-sm font-semibold">{sp.task_uz}</p>
      {canVoice ? (
        <p className="mt-1 text-[12px] font-semibold text-emerald-dark">
          🔊 namunani eshiting → 🎤 bosib ayting → bot eshitib baholaydi
        </p>
      ) : (
        <div className="mt-2 rounded-2xl bg-gold-soft border border-gold/30 p-3 text-[12px] font-semibold">
          {micSupported()
            ? "Ovozni tekshirish hozircha o'chiq — namunani eshitib, ovoz chiqarib takrorlang."
            : "Bu qurilmada mikrofon ishlamaydi — namunani eshitib, ovoz chiqarib takrorlang."}
        </div>
      )}

      <div className="mt-3 space-y-2">
        {targets.map((t, i) => {
          const r = results[i];
          const recHere = active === i;
          const single = r && r.mode !== "text" && r.words.length === 1 ? r.words[0] : null;
          return (
            <div key={i} className="rounded-2xl bg-card border border-cardline p-4">
              <div className="text-center">
                {r && r.mode === "text" ? (
                  <div className="font-arabic text-3xl leading-[1.9]" dir="rtl">
                    {r.words.map((w, k) => (
                      <span key={k} className={wordClass(w)}>
                        {w.ar}{" "}
                      </span>
                    ))}
                  </div>
                ) : r && r.mode === "letters" ? (
                  <div className="font-arabic text-3xl leading-[1.9]" dir="rtl">
                    {r.words.map((w, k) => (
                      <span key={k} className={`mx-1 ${wordClass(w)}`}>
                        {w.ar}
                      </span>
                    ))}
                  </div>
                ) : (
                  <ArabicText
                    text={t}
                    lookup={lookup}
                    className={`text-3xl ${single && !single.ok ? (single.close ? "text-gold" : "text-terracotta") : ""}`}
                  />
                )}
              </div>

              <div className="mt-3 flex items-center justify-center gap-2 flex-wrap">
                <button
                  onClick={() => listen(i)}
                  className="h-10 px-4 rounded-xl bg-gold-soft text-sm font-extrabold active:scale-95 transition-transform"
                >
                  🔊 Namuna
                </button>
                {canVoice &&
                  (recHere ? (
                    <button
                      onClick={() => void stop(i)}
                      className="h-10 px-4 rounded-xl bg-terracotta text-white text-sm font-extrabold flex items-center gap-2 active:scale-95 transition-transform"
                    >
                      <span className="w-2.5 h-2.5 rounded-full bg-white animate-pulse" />
                      {seconds}s · ■ Tayyor
                    </button>
                  ) : (
                    <button
                      onClick={() => void start(i)}
                      disabled={active !== null || busy !== null}
                      className="h-10 px-4 rounded-xl bg-emerald-deep text-white text-sm font-extrabold active:scale-95 transition-transform disabled:opacity-40"
                    >
                      {busy === i ? "🎧 Eshitilmoqda…" : r ? "🎤 Yana ayting" : "🎤 Ayting"}
                    </button>
                  ))}
                {r && (
                  <span className={`h-10 inline-flex items-center px-3 rounded-xl text-sm font-extrabold ${scoreColor(r.score)}`}>
                    🎯 {r.score}%
                  </span>
                )}
              </div>

              {recHere && (
                <div className="mt-3">
                  <div className="h-2 rounded-full bg-cardline overflow-hidden">
                    <div
                      className="h-full rounded-full bg-emerald-deep transition-[width] duration-100"
                      style={{ width: `${Math.max(4, Math.round(level * 100))}%` }}
                    />
                  </div>
                  <div className="mt-1 text-[11px] font-bold text-center text-ink-soft">
                    {quiet ? "Ovoz sezilmayapti — telefonni yaqinroq tutib, balandroq gapiring" : "Gapiring… bot eshityapti"}
                  </div>
                </div>
              )}

              {r && r.transcript && r.score < 100 && (
                <div className="mt-2 text-[12px] text-ink-soft font-semibold text-center">
                  Eshitildi:{" "}
                  <span className="font-arabic text-lg" dir="rtl">
                    {r.transcript.replace(/[\s.،,؟?!]+$/, "")}
                  </span>
                </div>
              )}
              {r && <div className="mt-1 text-xs font-bold text-ink-soft text-center">{r.tip_uz}</div>}
              {notice[i] && (
                <div className="mt-2 rounded-xl bg-gold-soft border border-gold/30 p-2.5 text-[12px] font-semibold">
                  {notice[i]}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <button
        onClick={() => {
          if (recorder.current.active) void recorder.current.stop(0);
          tg()?.HapticFeedback?.impactOccurred("light");
          onNext();
        }}
        disabled={busy !== null}
        className="mt-6 w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg active:scale-[0.98] transition-transform disabled:opacity-50"
      >
        {done > 0 || !canVoice ? "Keyingi" : "✓ O'qib chiqdim"}
      </button>
    </div>
  );
}
