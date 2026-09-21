import { useEffect, useRef, useState } from "react";
import {
  wordClass,
  api,
  type SpeakingHistoryItem,
  type TutorLog,
  type TutorMistakeItem,
  type TutorPronounceResult,
} from "../lib/api";
import { playUrl, speakText } from "../lib/audio";
import { Recorder, micSupported } from "../lib/recorder";

/** Speaking daftari (profil): 📒 xatolar (ustoz tuzatgan jumlalar, past mock
 *  javoblari) — eshitish, qayta aytish (STT bali), «o'rgandim»; 📈 natijalar —
 *  mock va talaffuz mashqlari tarixi (eng yaxshi, oxirgi, dinamika). */

const tg = () => window.Telegram?.WebApp;

type Tab = "mistakes" | "results";

interface Props {
  onClose: () => void;
  initialTab?: Tab;
}

function scoreClass(s: number) {
  return s >= 80 ? "bg-emerald-deep text-white" : s >= 50 ? "bg-gold text-white" : "bg-terracotta text-white";
}

export default function SpeakingLog({ onClose, initialTab = "mistakes" }: Props) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const [log, setLog] = useState<TutorLog | null>(null);
  const [error, setError] = useState(false);
  const [voice, setVoice] = useState(false);
  const [pron, setPron] = useState<Record<number, TutorPronounceResult>>({});
  const [recId, setRecId] = useState<number | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const recorder = useRef(new Recorder());

  useEffect(() => {
    api.getTutorLog().then(setLog).catch(() => setError(true));
    api
      .getTutorTopics()
      .then((t) => setVoice(t.voice && micSupported()))
      .catch(() => {});
    const r = recorder.current;
    return () => {
      if (r.active) r.stop();
    };
  }, []);

  useEffect(() => {
    if (recId === null) return;
    setSeconds(0);
    const id = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [recId]);

  const say = async (text: string) => {
    try {
      const r = await api.tutorSay(text);
      const ok = await playUrl(r.audio_url);
      if (!ok) speakText(text);
    } catch {
      speakText(text);
    }
  };

  const startRec = async (m: TutorMistakeItem) => {
    if (recId !== null || busyId !== null) return;
    try {
      await recorder.current.start(() => stopRec(m));
      setRecId(m.id);
      tg()?.HapticFeedback?.impactOccurred("medium");
    } catch {
      setNotice("Mikrofonga ruxsat berilmadi.");
    }
  };

  const stopRec = async (m: TutorMistakeItem) => {
    const rec = await recorder.current.stop();
    setRecId(null);
    if (!rec) {
      setNotice("Yozuv juda qisqa. Qayta urinib ko'ring.");
      return;
    }
    setBusyId(m.id);
    setNotice("");
    try {
      const r = await api.tutorPronounce(rec.blob, rec.filename, m.fixed_ar);
      setPron((p) => ({ ...p, [m.id]: r }));
      tg()?.HapticFeedback?.notificationOccurred(r.score >= 80 ? "success" : "warning");
    } catch (e) {
      setNotice((e as { detail?: string })?.detail || "Ovoz xizmati javob bermadi.");
    } finally {
      setBusyId(null);
    }
  };

  const learned = async (m: TutorMistakeItem) => {
    setLog((l) => (l ? { ...l, mistakes: l.mistakes.filter((x) => x.id !== m.id) } : l));
    tg()?.HapticFeedback?.impactOccurred("light");
    try {
      await api.deleteMistake(m.id);
    } catch {
      /* ro'yxatdan chiqdi — keyingi yuklashda qaytsa ham zarar yo'q */
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-sand flex flex-col max-w-md mx-auto">
      <div className="flex items-center justify-between px-4 py-3 border-b border-cardline bg-card">
        <div>
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">🗣 SPEAKING</div>
          <div className="font-extrabold">Daftar va natijalar</div>
        </div>
        <button onClick={onClose} className="w-9 h-9 rounded-full bg-cardline text-ink-soft font-extrabold">
          ✕
        </button>
      </div>

      <div className="px-4 pt-3">
        <div className="grid grid-cols-2 gap-1 rounded-2xl bg-cardline/60 p-1">
          {(["mistakes", "results"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-xl py-2 text-[13px] font-extrabold transition-colors ${
                tab === t ? "bg-card shadow-sm" : "text-ink-soft"
              }`}
            >
              {t === "mistakes" ? `📒 Xatolar${log ? ` (${log.mistakes.length})` : ""}` : "📈 Natijalar"}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {error && <div className="text-center text-ink-soft font-semibold pt-8">Yuklanmadi. Qayta urinib ko'ring.</div>}
        {!log && !error && <div className="text-center text-sm text-ink-soft font-semibold pt-8">Yuklanmoqda…</div>}
        {notice && (
          <div className="rounded-2xl bg-gold-soft border border-gold/30 p-3 text-sm font-semibold">{notice}</div>
        )}

        {log && tab === "mistakes" && (
          <>
            {log.mistakes.length === 0 ? (
              <div className="rounded-3xl bg-card border border-cardline p-6 text-center">
                <div className="text-3xl">📒</div>
                <div className="font-extrabold mt-2">Daftar bo'sh</div>
                <p className="text-sm text-ink-soft font-semibold mt-1">
                  AI ustoz bilan suhbatda tuzatilgan jumlalar va past baholangan mock javoblari shu yerga
                  tushadi — keyin eshitib, qayta aytib mashq qilasiz.
                </p>
              </div>
            ) : (
              <p className="text-xs text-ink-soft font-semibold">
                Qizil — siz aytgan, yashil — to'g'ri shakl. 🎤 bilan to'g'ri jumlani ayting, bali chiqadi.
              </p>
            )}
            {log.mistakes.map((m) => {
              const r = pron[m.id];
              const rec = recId === m.id;
              return (
                <div key={m.id} className="rounded-2xl bg-card border border-cardline p-4 space-y-2">
                  <div className="flex items-center justify-between text-[11px] font-extrabold text-ink-soft">
                    <span>
                      {m.kind === "mock" ? "🎯" : "💬"} {m.title || m.topic}
                    </span>
                    <span>{m.date}</span>
                  </div>
                  <div className="font-arabic text-lg text-terracotta line-through decoration-terracotta/60 leading-relaxed" dir="rtl">
                    {m.said_ar}
                  </div>
                  <div className="font-arabic text-2xl text-emerald-dark leading-relaxed" dir="rtl">
                    {r
                      ? r.words.map((w, i) => (
                          <span key={i} className={wordClass(w)}>
                            {w.ar}{" "}
                          </span>
                        ))
                      : m.fixed_ar}
                  </div>
                  {m.note_uz && <div className="text-xs font-semibold text-ink-soft">💡 {m.note_uz}</div>}
                  {r && r.score < 80 && r.transcript && (
                    <div className="text-[11px] text-ink-soft font-semibold" dir="rtl">
                      Eshitildi: {r.transcript}
                    </div>
                  )}
                  <div className="flex items-center gap-2 flex-wrap pt-1">
                    <button
                      onClick={() => say(m.fixed_ar)}
                      className="h-9 px-3 rounded-lg bg-gold-soft text-sm font-extrabold active:scale-95 transition-transform"
                    >
                      🔊
                    </button>
                    {voice && (
                      <button
                        onClick={() => (rec ? stopRec(m) : startRec(m))}
                        disabled={busyId !== null || (recId !== null && !rec)}
                        className={`h-9 px-3 rounded-lg text-xs font-extrabold active:scale-95 transition-transform disabled:opacity-40 ${
                          rec ? "bg-terracotta text-white animate-pulse" : "bg-emerald-deep/10 text-emerald-dark"
                        }`}
                      >
                        {rec
                          ? `■ ${seconds}s`
                          : busyId === m.id
                            ? "🎧 …"
                            : r
                              ? "🎤 Yana"
                              : "🎤 Mashq"}
                      </button>
                    )}
                    {r && (
                      <span className={`h-9 inline-flex items-center px-3 rounded-lg text-xs font-extrabold ${scoreClass(r.score)}`}>
                        🎯 {r.score}%
                      </span>
                    )}
                    <button
                      onClick={() => learned(m)}
                      className="ml-auto h-9 px-3 rounded-lg bg-card border border-cardline text-xs font-extrabold text-ink-soft active:scale-95 transition-transform"
                    >
                      ✓ O'rgandim
                    </button>
                  </div>
                </div>
              );
            })}
          </>
        )}

        {log && tab === "results" && (
          <>
            <HistorySection
              title="🎯 MOCK IMTIHONLAR"
              empty="Hali mock topshirilmagan. AI ustoz → Mock bo'limida kasb tanlang."
              items={log.mocks}
            />
            <HistorySection
              title="🎤 TALAFFUZ MASHQLARI"
              empty="Hali mashq yo'q. AI ustoz → Talaffuz bo'limi bepul, hoziroq boshlang."
              items={log.drills}
            />
            <HistorySection
              title="🎧 TINGLAB TUSHUNISH"
              empty="Hali mashq yo'q. AI ustoz → Tinglash bo'limi bepul."
              items={log.listens ?? []}
            />
          </>
        )}
      </div>
    </div>
  );
}

function HistorySection({
  title,
  empty,
  items,
}: {
  title: string;
  empty: string;
  items: SpeakingHistoryItem[];
}) {
  return (
    <section className="space-y-2">
      <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">{title}</div>
      {items.length === 0 && (
        <div className="rounded-2xl bg-card border border-cardline p-4 text-sm text-ink-soft font-semibold">{empty}</div>
      )}
      {items.map((it, i) => {
        const delta = it.history.length >= 2 ? it.last - it.history[it.history.length - 2] : 0;
        return (
          <div key={i} className="rounded-2xl bg-card border border-cardline p-3.5 flex items-center gap-3">
            <div className="text-2xl">{it.emoji}</div>
            <div className="min-w-0 flex-1">
              <div className="font-extrabold text-[14px] leading-tight truncate">{it.title}</div>
              <div className="text-[11px] text-ink-soft font-semibold">
                {it.attempts} marta · oxirgi {it.last}% ({it.date})
                {delta !== 0 && (
                  <span className={delta > 0 ? "text-emerald-dark" : "text-terracotta"}>
                    {" "}
                    {delta > 0 ? "▲" : "▼"} {Math.abs(delta)}
                  </span>
                )}
              </div>
              <div className="mt-1.5 flex items-end gap-0.5 h-5">
                {it.history.map((s, j) => (
                  <div
                    key={j}
                    className={`w-2.5 rounded-sm ${s >= 80 ? "bg-emerald-deep" : s >= 50 ? "bg-gold" : "bg-terracotta"}`}
                    style={{ height: `${Math.max(12, s)}%` }}
                    title={`${s}%`}
                  />
                ))}
              </div>
            </div>
            <div className="text-right shrink-0">
              <div className={`rounded-xl px-2.5 py-1 text-sm font-extrabold ${scoreClass(it.best)}`}>{it.best}%</div>
              <div className="text-[10px] text-ink-soft font-bold mt-0.5">eng yaxshi</div>
            </div>
          </div>
        );
      })}
    </section>
  );
}
