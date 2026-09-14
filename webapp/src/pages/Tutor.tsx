import { useEffect, useRef, useState } from "react";
import {
  api,
  type TutorFinishResult,
  type TutorNewWord,
  type TutorPronounceResult,
  type TutorTopic,
  type TutorTopics,
} from "../lib/api";
import { playUrl, speakText } from "../lib/audio";
import { MAX_SECONDS, Recorder, micSupported } from "../lib/recorder";

/** AI ustoz — darajaga mos jonli suhbat (speaking).
 *
 *  Oqim: mavzu → ustoz ochadi (audio) → o'quvchi yozadi yoki gapiradi
 *  (mikrofon → STT) → ustoz javobi + tuzatish kartasi + maslahat.
 *  Har ustoz jumlasini «Takrorlash» bilan aytib, talaffuz balini olish mumkin.
 */

interface TutorProps {
  onClose: () => void;
}

interface Correction {
  ok: boolean;
  fixed_ar: string;
  note_uz: string;
}

interface Msg {
  role: "user" | "assistant";
  ar: string;
  translit?: string;
  uz?: string;
  hint?: string;
  newWords?: TutorNewWord[];
  audioUrl?: string;
  /** O'quvchi javobi mikrofondan keldi */
  voice?: boolean;
  /** Ustozning shu javobga bergan bahosi (user xabariga biriktiriladi) */
  correction?: Correction;
  /** Takrorlash mashqi natijasi (assistant xabari uchun) */
  score?: TutorPronounceResult;
}

type RecTarget = { kind: "answer" } | { kind: "repeat"; idx: number };

const tg = () => window.Telegram?.WebApp;

function newSessionKey(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

/** Tarjima sukut bo'yicha: A0–A2 ochiq, B1+ yopiq (avval arabchani o'qisin) */
function uzDefault(level: string): boolean {
  return !["B1", "B2"].includes(level.toUpperCase());
}

export default function Tutor({ onClose }: TutorProps) {
  const [info, setInfo] = useState<TutorTopics | null>(null);
  const [loadError, setLoadError] = useState("");
  const [topic, setTopic] = useState<TutorTopic | null>(null);
  const [sessionKey, setSessionKey] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [turnsLeft, setTurnsLeft] = useState(0);
  const [showUz, setShowUz] = useState(true);
  const [notice, setNotice] = useState("");
  const [finish, setFinish] = useState<TutorFinishResult | null>(null);
  const [saved, setSaved] = useState<Set<string>>(new Set());

  // Mikrofon
  const recorder = useRef(new Recorder());
  const [recTarget, setRecTarget] = useState<RecTarget | null>(null);
  const [recSeconds, setRecSeconds] = useState(0);
  const [transcribing, setTranscribing] = useState(false);
  const canVoice = !!info?.voice && micSupported();

  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .getTutorTopics()
      .then((t) => {
        setInfo(t);
        setTurnsLeft(t.turns_left);
        setShowUz(uzDefault(t.level));
      })
      .catch(() => setLoadError("Mavzular yuklanmadi. Qayta urinib ko'ring."));
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, loading, transcribing]);

  // Yozuv sekundomeri
  useEffect(() => {
    if (!recTarget) return;
    setRecSeconds(0);
    const id = window.setInterval(() => setRecSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [recTarget]);

  // Sahifa yopilganda mikrofon qolib ketmasin
  useEffect(() => {
    const r = recorder.current;
    return () => {
      if (r.active) r.stop();
    };
  }, []);

  const historyFor = (msgs: Msg[]) =>
    msgs.map((m) => ({
      role: m.role,
      // 🎤 prefiksi — modelga "STT xatosi bo'lishi mumkin" signali (qoida 6)
      content: m.role === "user" && m.voice ? `🎤 ${m.ar}` : m.ar,
    }));

  const speak = (m: Msg) => {
    playUrl(m.audioUrl).then((ok) => {
      if (!ok) speakText(m.ar);
    });
  };

  const showError = (e: unknown, fallback: string) => {
    const err = e as { status?: number; detail?: string };
    if (err?.status === 429) {
      setTurnsLeft(0);
      setNotice(err.detail || "Bugungi suhbat limiti tugadi — ertaga davom eting.");
    } else {
      setNotice(err?.detail || fallback);
    }
  };

  const start = async (t: TutorTopic) => {
    const key = newSessionKey();
    setTopic(t);
    setSessionKey(key);
    setMessages([]);
    setDone(false);
    setFinish(null);
    setNotice("");
    setLoading(true);
    try {
      const r = await api.tutorTurn({
        session_key: key,
        topic_id: t.id,
        history: [],
        voice: false,
      });
      const m: Msg = {
        role: "assistant",
        ar: r.reply.ar,
        translit: r.reply.translit,
        uz: r.reply.uz,
        hint: r.reply.hint_uz,
        newWords: r.reply.new_words,
        audioUrl: r.audio_url,
      };
      setMessages([m]);
      setTurnsLeft(r.turns_left);
      speak(m);
    } catch (e) {
      showError(e, "Ustoz javob bermadi. Qayta urinib ko'ring.");
      setTopic(null);
    } finally {
      setLoading(false);
    }
  };

  const send = async (text: string, voice: boolean) => {
    const clean = text.trim();
    if (!clean || !topic || loading || done) return;
    const userMsg: Msg = { role: "user", ar: clean, voice };
    const next = [...messages, userMsg];
    setMessages(next);
    setInput("");
    setNotice("");
    setLoading(true);
    tg()?.HapticFeedback?.impactOccurred("light");
    try {
      const r = await api.tutorTurn({
        session_key: sessionKey,
        topic_id: topic.id,
        history: historyFor(next),
        voice,
      });
      const reply: Msg = {
        role: "assistant",
        ar: r.reply.ar,
        translit: r.reply.translit,
        uz: r.reply.uz,
        hint: r.reply.hint_uz,
        newWords: r.reply.new_words,
        audioUrl: r.audio_url,
      };
      const graded: Msg = {
        ...userMsg,
        correction: {
          ok: r.reply.correction_ok,
          fixed_ar: r.reply.fixed_ar,
          note_uz: r.reply.note_uz,
        },
      };
      setMessages([...messages, graded, reply]);
      setTurnsLeft(r.turns_left);
      if (r.reply.done) setDone(true);
      speak(reply);
      if (!r.reply.correction_ok) tg()?.HapticFeedback?.notificationOccurred("warning");
    } catch (e) {
      // Javob o'tmadi — o'quvchi matnini qaytaramiz, yana yuborsin
      setMessages(messages);
      setInput(clean);
      showError(e, "Ustoz javob bermadi. Qayta urinib ko'ring.");
    } finally {
      setLoading(false);
    }
  };

  // ── Mikrofon ──
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");

  const startRec = async (target: RecTarget) => {
    if (recTarget || loading || transcribing) return;
    try {
      await recorder.current.start(() => stopRec(target));
      setRecTarget(target);
      tg()?.HapticFeedback?.impactOccurred("medium");
    } catch {
      setNotice("Mikrofonga ruxsat berilmadi — yozib javob bering.");
    }
  };

  const stopRec = async (target: RecTarget) => {
    const rec = await recorder.current.stop();
    setRecTarget(null);
    if (!rec) {
      setNotice("Yozuv juda qisqa. Qayta urinib ko'ring.");
      return;
    }
    setTranscribing(true);
    try {
      if (target.kind === "answer") {
        const r = await api.tutorTranscribe(rec.blob, rec.filename, lastAssistant?.ar ?? "");
        if (!r.text) {
          setNotice("Ovoz tushunilmadi. Yaqinroq va aniqroq gapiring.");
        } else {
          await send(r.text, true);
        }
      } else {
        const m = messages[target.idx];
        const r = await api.tutorPronounce(rec.blob, rec.filename, m.ar);
        setMessages((ms) => ms.map((x, i) => (i === target.idx ? { ...x, score: r } : x)));
        tg()?.HapticFeedback?.notificationOccurred(r.score >= 70 ? "success" : "warning");
      }
    } catch (e) {
      showError(e, "Ovoz xizmati javob bermadi.");
    } finally {
      setTranscribing(false);
    }
  };

  // Bitta tugma: yozuv yo'q — boshlaydi; bor — to'xtatadi (qaysi tugma bosilmasin)
  const toggleRec = (target: RecTarget) => {
    if (recTarget) {
      stopRec(recTarget);
      return;
    }
    startRec(target);
  };

  const finishSession = async () => {
    if (!sessionKey) return;
    setLoading(true);
    try {
      const r = await api.tutorFinish(sessionKey);
      setFinish(r);
      if (r.xp > 0) tg()?.HapticFeedback?.notificationOccurred("success");
    } catch {
      setFinish({ turns: 0, ok_turns: 0, voice_turns: 0, xp: 0 });
    } finally {
      setLoading(false);
    }
  };

  const saveWord = async (w: TutorNewWord) => {
    if (saved.has(w.ar)) return;
    try {
      await api.tutorSaveWord(w.ar, w.uz);
      setSaved((s) => new Set(s).add(w.ar));
      tg()?.HapticFeedback?.impactOccurred("light");
    } catch {
      /* jim */
    }
  };

  const userTurns = messages.filter((m) => m.role === "user").length;
  const outOfTurns = turnsLeft <= 0;

  return (
    <div className="fixed inset-0 z-50 bg-sand flex flex-col max-w-md mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-cardline bg-card">
        <div className="min-w-0">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
            🤖 AI USTOZ{info ? ` · ${info.level}` : ""}
          </div>
          <div className="font-extrabold truncate">
            {topic ? `${topic.emoji} ${topic.title_uz}` : "Jonli suhbat"}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {topic && (
            <button
              onClick={() => setShowUz((v) => !v)}
              className={`h-9 px-3 rounded-full text-xs font-extrabold border ${
                showUz
                  ? "bg-emerald-deep text-white border-emerald-deep"
                  : "bg-card text-ink-soft border-cardline"
              }`}
              aria-label="Tarjimani ko'rsatish"
            >
              UZ
            </button>
          )}
          <button
            onClick={() => (topic && !finish ? setTopic(null) : onClose())}
            className="w-9 h-9 rounded-full bg-cardline text-ink-soft font-extrabold"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Mavzu tanlash */}
      {!topic && (
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          <p className="text-sm text-ink-soft font-semibold">
            Ustoz sizning darajangizda gaplashadi, xatolaringizni yumshoq tuzatadi.
            Arabcha yozing yoki 🎤 gapiring — lotin yozuvida ham bo'ladi.
          </p>
          {info && (
            <div className="flex items-center justify-between rounded-2xl bg-card border border-cardline px-4 py-2.5 text-xs font-bold">
              <span className="text-ink-soft">
                Bugun qoldi: <span className="text-ink">{turnsLeft}</span>/{info.daily_limit}{" "}
                javob
              </span>
              <span className="text-ink-soft">
                {info.voice ? "🎤 ovoz yoqilgan" : "⌨️ faqat matn"}
              </span>
            </div>
          )}
          {info && !info.ai && (
            <div className="rounded-2xl bg-gold-soft border border-gold/30 p-4 text-sm font-semibold">
              AI ustoz hozircha o'chiq (server sozlanmoqda). Birozdan keyin qayta kiring.
            </div>
          )}
          {notice && (
            <div className="rounded-2xl bg-gold-soft border border-gold/30 p-3 text-sm font-semibold">
              {notice}
            </div>
          )}
          {loadError && (
            <div className="text-center text-ink-soft font-semibold pt-8">{loadError}</div>
          )}
          {info?.topics.map((t) => (
            <button
              key={t.id}
              onClick={() => start(t)}
              disabled={!info.ai || loading || outOfTurns}
              className="w-full flex items-center gap-3 rounded-2xl bg-card border border-cardline p-4 text-left active:scale-[0.98] transition-transform disabled:opacity-50"
            >
              <div className="w-12 h-12 shrink-0 rounded-xl bg-gold-soft flex items-center justify-center text-2xl">
                {t.emoji}
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-extrabold flex items-center gap-2">
                  {t.title_uz}
                  {!t.recommended && (
                    <span className="text-[10px] font-extrabold rounded-full bg-cardline px-2 py-0.5 text-ink-soft">
                      {t.min_level}+
                    </span>
                  )}
                </div>
                <div className="text-xs text-ink-soft font-semibold">{t.desc_uz}</div>
              </div>
              <span className="text-emerald-dark font-extrabold text-xl">›</span>
            </button>
          ))}
          {loading && (
            <div className="text-center text-sm text-ink-soft font-semibold py-3">
              Ustoz suhbatni boshlamoqda…
            </div>
          )}
        </div>
      )}

      {/* Suhbat */}
      {topic && !finish && (
        <>
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.map((m, i) =>
              m.role === "user" ? (
                <UserBubble key={i} m={m} />
              ) : (
                <TutorBubble
                  key={i}
                  m={m}
                  showUz={showUz}
                  canVoice={canVoice}
                  recording={recTarget?.kind === "repeat" && recTarget.idx === i}
                  busy={!!recTarget || transcribing || loading}
                  saved={saved}
                  onSpeak={() => speak(m)}
                  onRepeat={() => toggleRec({ kind: "repeat", idx: i })}
                  onSave={saveWord}
                />
              )
            )}
            {(loading || transcribing) && (
              <div className="flex justify-start">
                <div className="rounded-2xl bg-card border border-cardline px-4 py-3 text-xs font-bold text-ink-soft">
                  {transcribing ? "🎧 Eshitilmoqda…" : "Ustoz yozmoqda…"}
                </div>
              </div>
            )}
            {notice && (
              <div className="rounded-2xl bg-gold-soft border border-gold/30 p-3 text-sm font-semibold">
                {notice}
              </div>
            )}
            {done && (
              <div className="text-center py-3">
                <div className="text-2xl">🎉</div>
                <p className="text-sm font-bold text-emerald-dark">Suhbat yakunlandi!</p>
              </div>
            )}
          </div>

          {/* Kiritish */}
          <div className="p-3 border-t border-cardline bg-card space-y-2">
            {recTarget?.kind === "answer" ? (
              <div className="flex items-center gap-3 rounded-xl bg-terracotta/10 border border-terracotta/40 px-3 py-2.5">
                <span className="w-3 h-3 rounded-full bg-terracotta animate-pulse" />
                <span className="flex-1 text-sm font-extrabold">
                  Gapiring… {recSeconds}s / {MAX_SECONDS}s
                </span>
                <button
                  onClick={() => toggleRec({ kind: "answer" })}
                  className="h-10 px-4 rounded-xl bg-terracotta text-white font-extrabold active:scale-95 transition-transform"
                >
                  ■ Tayyor
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                {canVoice && (
                  <button
                    onClick={() => toggleRec({ kind: "answer" })}
                    disabled={loading || transcribing || done || outOfTurns || !!recTarget}
                    className="w-11 h-11 shrink-0 rounded-xl bg-gold-soft text-xl active:scale-90 transition-transform disabled:opacity-40"
                    aria-label="Gapirish"
                  >
                    🎤
                  </button>
                )}
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && send(input, false)}
                  dir="auto"
                  placeholder={outOfTurns ? "Bugungi limit tugadi" : "جوابك هنا… yoki lotincha"}
                  disabled={done || outOfTurns}
                  className="flex-1 min-w-0 rounded-xl bg-sand border border-cardline px-3 py-2.5 font-arabic text-lg outline-none focus:border-emerald-deep/40 disabled:opacity-60"
                />
                <button
                  onClick={() => send(input, false)}
                  disabled={!input.trim() || loading || done || outOfTurns}
                  className="w-11 h-11 shrink-0 rounded-xl bg-emerald-deep text-white text-xl font-extrabold active:scale-90 transition-transform disabled:opacity-40"
                >
                  ↑
                </button>
              </div>
            )}
            <div className="flex items-center justify-between text-[11px] font-bold text-ink-soft px-0.5">
              <span>
                {userTurns} javob · bugun qoldi: {turnsLeft}
              </span>
              <button
                onClick={finishSession}
                disabled={loading || userTurns === 0}
                className="font-extrabold text-emerald-dark underline underline-offset-4 disabled:opacity-40"
              >
                Yakunlash ✓
              </button>
            </div>
          </div>
        </>
      )}

      {/* Yakuniy hisobot */}
      {topic && finish && (
        <Summary
          result={finish}
          messages={messages}
          saved={saved}
          onSave={saveWord}
          onAgain={() => start(topic)}
          onTopics={() => {
            setTopic(null);
            setFinish(null);
            setMessages([]);
          }}
          onClose={onClose}
        />
      )}
    </div>
  );
}

// ────────────────────────── Bo'laklar ──────────────────────────

function UserBubble({ m }: { m: Msg }) {
  const c = m.correction;
  return (
    <div className="flex flex-col items-end gap-1">
      <div className="max-w-[82%] rounded-2xl px-4 py-2.5 bg-emerald-deep text-white">
        <div className="font-arabic text-xl leading-snug" dir="auto">
          {m.voice && <span className="text-sm mr-1 opacity-80">🎤</span>}
          {m.ar}
        </div>
      </div>
      {c && (
        <div
          className={`max-w-[82%] rounded-xl px-3 py-2 text-xs font-semibold ${
            c.ok
              ? "bg-emerald-deep/10 text-emerald-dark"
              : "bg-gold-soft border border-gold/30 text-ink"
          }`}
        >
          {c.ok ? (
            "✅ To'g'ri!"
          ) : (
            <>
              <div className="font-arabic text-lg leading-snug" dir="rtl">
                ✏️ {c.fixed_ar}
              </div>
              {c.note_uz && <div className="mt-0.5 text-ink-soft">{c.note_uz}</div>}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function TutorBubble({
  m,
  showUz,
  canVoice,
  recording,
  busy,
  saved,
  onSpeak,
  onRepeat,
  onSave,
}: {
  m: Msg;
  showUz: boolean;
  canVoice: boolean;
  recording: boolean;
  busy: boolean;
  saved: Set<string>;
  onSpeak: () => void;
  onRepeat: () => void;
  onSave: (w: TutorNewWord) => void;
}) {
  return (
    <div className="flex flex-col items-start gap-1.5">
      <div className="max-w-[88%] rounded-2xl px-4 py-3 bg-card border border-cardline">
        <div className="font-arabic text-2xl leading-relaxed" dir="rtl">
          {m.score
            ? m.score.words.map((w, i) => (
                <span key={i} className={w.ok ? "" : "text-terracotta underline decoration-2"}>
                  {w.ar}{" "}
                </span>
              ))
            : m.ar}
        </div>
        {m.translit && (
          <div className="text-xs text-ink-soft font-semibold mt-1 italic">{m.translit}</div>
        )}
        {showUz && m.uz && <div className="text-sm font-semibold mt-1">{m.uz}</div>}
        <div className="mt-2 flex items-center gap-2 flex-wrap">
          <button
            onClick={onSpeak}
            className="h-8 px-2.5 rounded-lg bg-gold-soft text-sm font-extrabold active:scale-90 transition-transform"
            aria-label="Tinglash"
          >
            🔊
          </button>
          {canVoice && (
            <button
              onClick={onRepeat}
              disabled={busy && !recording}
              className={`h-8 px-2.5 rounded-lg text-xs font-extrabold active:scale-95 transition-transform disabled:opacity-40 ${
                recording
                  ? "bg-terracotta text-white animate-pulse"
                  : "bg-emerald-deep/10 text-emerald-dark"
              }`}
            >
              {recording ? "■ Tayyor" : "🎤 Takrorlash"}
            </button>
          )}
          {m.score && (
            <span
              className={`h-8 inline-flex items-center px-2.5 rounded-lg text-xs font-extrabold ${
                m.score.score >= 80
                  ? "bg-emerald-deep text-white"
                  : m.score.score >= 50
                    ? "bg-gold text-white"
                    : "bg-terracotta text-white"
              }`}
            >
              🎯 {m.score.score}%
            </span>
          )}
        </div>
        {m.score && m.score.transcript && m.score.score < 80 && (
          <div className="mt-1.5 text-[11px] text-ink-soft font-semibold" dir="rtl">
            Eshitildi: {m.score.transcript}
          </div>
        )}
      </div>

      {m.hint && (
        <div className="max-w-[88%] rounded-xl bg-emerald-deep/10 px-3 py-2 text-xs font-semibold text-emerald-dark">
          💡 {m.hint}
        </div>
      )}

      {m.newWords && m.newWords.length > 0 && (
        <div className="flex flex-wrap gap-1.5 max-w-[88%]">
          {m.newWords.map((w) => (
            <button
              key={w.ar}
              onClick={() => onSave(w)}
              className="rounded-full bg-card border border-cardline px-3 py-1 text-xs font-bold active:scale-95 transition-transform"
            >
              <span className="font-arabic text-base">{w.ar}</span> · {w.uz}{" "}
              <span className="text-emerald-dark">{saved.has(w.ar) ? "✓" : "+"}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Summary({
  result,
  messages,
  saved,
  onSave,
  onAgain,
  onTopics,
  onClose,
}: {
  result: TutorFinishResult;
  messages: Msg[];
  saved: Set<string>;
  onSave: (w: TutorNewWord) => void;
  onAgain: () => void;
  onTopics: () => void;
  onClose: () => void;
}) {
  const fixes = messages.filter((m) => m.role === "user" && m.correction && !m.correction.ok);
  const words = new Map<string, TutorNewWord>();
  messages.forEach((m) => m.newWords?.forEach((w) => words.set(w.ar, w)));
  const pct = result.turns ? Math.round((result.ok_turns / result.turns) * 100) : 0;

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      <div className="rounded-3xl bg-gradient-to-br from-emerald-deep to-emerald-dark p-5 text-white text-center shadow-lg">
        <div className="text-3xl">{pct >= 80 ? "🌟" : pct >= 50 ? "👏" : "💪"}</div>
        <div className="text-xl font-extrabold mt-1">Suhbat yakunlandi</div>
        <div className="text-sm text-white/80 font-semibold">
          {result.turns} javob · {pct}% xatosiz
          {result.voice_turns > 0 ? ` · 🎤 ${result.voice_turns}` : ""}
        </div>
        <div className="mt-3 inline-block rounded-full bg-white/15 px-4 py-1.5 font-extrabold">
          {result.xp > 0 ? `+${result.xp} XP` : "XP uchun kamida 3 javob"}
        </div>
      </div>

      {fixes.length > 0 && (
        <section className="rounded-2xl bg-card border border-cardline p-4">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2">
            TUZATISHLAR ({fixes.length})
          </div>
          <div className="space-y-2.5">
            {fixes.map((m, i) => (
              <div key={i} className="text-sm">
                <div className="font-arabic text-base text-ink-soft line-through" dir="auto">
                  {m.ar}
                </div>
                <div className="font-arabic text-lg" dir="rtl">
                  {m.correction!.fixed_ar}
                </div>
                {m.correction!.note_uz && (
                  <div className="text-xs text-ink-soft font-semibold">{m.correction!.note_uz}</div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {words.size > 0 && (
        <section className="rounded-2xl bg-card border border-cardline p-4">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2">
            YANGI SO'ZLAR — kartotekaga qo'shing
          </div>
          <div className="flex flex-wrap gap-1.5">
            {[...words.values()].map((w) => (
              <button
                key={w.ar}
                onClick={() => onSave(w)}
                className="rounded-full bg-sand border border-cardline px-3 py-1 text-xs font-bold active:scale-95 transition-transform"
              >
                <span className="font-arabic text-base">{w.ar}</span> · {w.uz}{" "}
                <span className="text-emerald-dark">{saved.has(w.ar) ? "✓" : "+"}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      <div className="grid grid-cols-2 gap-3 pt-1">
        <button
          onClick={onAgain}
          className="rounded-2xl bg-emerald-deep py-3.5 text-white font-extrabold active:scale-95 transition-transform"
        >
          Yana bir bor
        </button>
        <button
          onClick={onTopics}
          className="rounded-2xl bg-card border border-cardline py-3.5 font-extrabold active:scale-95 transition-transform"
        >
          Boshqa mavzu
        </button>
      </div>
      <button onClick={onClose} className="w-full text-sm font-bold text-ink-soft py-2">
        Bosh sahifaga
      </button>
    </div>
  );
}
