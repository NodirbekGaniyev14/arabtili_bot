import { useEffect, useRef, useState } from "react";
import {
  api,
  type MockCriteria,
  type TutorFinishResult,
  type TutorMock,
  type TutorNewWord,
  type TutorPronounceResult,
  type TutorTopic,
  type TutorTopics,
} from "../lib/api";
import { playUrl, speakText } from "../lib/audio";
import { MAX_SECONDS, Recorder, micSupported } from "../lib/recorder";
import Drill from "./Drill";
import Paywall from "./Paywall";

/** AI ustoz — darajaga mos jonli suhbat (speaking) va mock imtihonlar.
 *
 *  Suhbat: mavzu → ustoz ochadi (audio) → o'quvchi yozadi yoki gapiradi
 *  (mikrofon → STT) → ustoz javobi + tuzatish kartasi + maslahat. O'zbekcha
 *  savol bersa — o'zbekcha tushuntiradi (answer_uz).
 *  Mock: kasb bo'yicha 5 savol, har javob 0-100 baholanadi, o'rtacha ball
 *  profil XP'siga qo'shiladi.
 *  VIP: bepul rejimda kuniga 3 javob, keyin Paywall.
 *  Talaffuz: AI'siz bepul mashq — lug'at jumlalari, STT + o'xshashlik bali (Drill.tsx).
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
  answerUz?: string;
  newWords?: TutorNewWord[];
  audioUrl?: string;
  /** O'quvchi javobi mikrofondan keldi */
  voice?: boolean;
  /** Ustozning shu javobga bergan bahosi (user xabariga biriktiriladi) */
  correction?: Correction;
  /** Mock: shu javob bali, izoh va namunaviy javob */
  mockScore?: number;
  feedback?: string;
  ideal?: string;
  crit?: MockCriteria;
  /** Takrorlash mashqi natijasi (assistant xabari uchun) */
  pron?: TutorPronounceResult;
}

type RecTarget = { kind: "answer" } | { kind: "repeat"; idx: number };
type Tab = "chat" | "mock" | "drill";

const tg = () => window.Telegram?.WebApp;
const VOICE_MODE_KEY = "arabiy_tutor_voice_mode";

const fmtSum = (n: number) => n.toLocaleString("ru-RU").replace(/,/g, " ");

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
  const [tab, setTab] = useState<Tab>("chat");
  const [topic, setTopic] = useState<TutorTopic | null>(null);
  const [mock, setMock] = useState<TutorMock | null>(null);
  const [drillTopic, setDrillTopic] = useState<TutorTopic | null>(null);
  const [sessionKey, setSessionKey] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [turnsLeft, setTurnsLeft] = useState(0);
  const [showUz, setShowUz] = useState(true);
  // «Faqat ovoz» rejimi: matn yashirin (tinglash mashqi), bosib-gapir tugmasi
  const [voiceMode, setVoiceMode] = useState(() => {
    try {
      return localStorage.getItem(VOICE_MODE_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [revealed, setRevealed] = useState<Set<number>>(new Set());
  const [notice, setNotice] = useState("");
  const [finish, setFinish] = useState<TutorFinishResult | null>(null);
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const [paywall, setPaywall] = useState<string | null>(null);

  // Mikrofon
  const recorder = useRef(new Recorder());
  const [recTarget, setRecTarget] = useState<RecTarget | null>(null);
  const [recSeconds, setRecSeconds] = useState(0);
  const [transcribing, setTranscribing] = useState(false);
  const canVoice = !!info?.voice && micSupported();
  const voiceOnly = voiceMode && canVoice;

  const toggleVoiceMode = () => {
    setVoiceMode((v) => {
      try {
        localStorage.setItem(VOICE_MODE_KEY, v ? "0" : "1");
      } catch {
        /* jim */
      }
      return !v;
    });
  };

  const scrollRef = useRef<HTMLDivElement>(null);
  const active = topic || mock;
  const isMock = !!mock;

  const loadInfo = () =>
    api
      .getTutorTopics()
      .then((t) => {
        setInfo(t);
        setTurnsLeft(t.turns_left);
        setShowUz(uzDefault(t.level));
      })
      .catch(() => setLoadError("Mavzular yuklanmadi. Qayta urinib ko'ring."));

  useEffect(() => {
    loadInfo();
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
    if (err?.status === 402) {
      setTurnsLeft(0);
      setPaywall(err.detail || "Bepul javoblar tugadi — VIP bilan davom eting.");
    } else if (err?.status === 429) {
      setTurnsLeft(0);
      setNotice(err.detail || "Bugungi suhbat limiti tugadi — ertaga davom eting.");
    } else {
      setNotice(err?.detail || fallback);
    }
  };

  const turnBody = (key: string, history: Msg[], voice: boolean) => ({
    session_key: key,
    topic_id: topic?.id ?? "erkin",
    history: historyFor(history),
    voice,
    mode: (mock ? "mock" : "chat") as "chat" | "mock",
    mock_id: mock?.id,
  });

  const start = async (t: TutorTopic | null, m: TutorMock | null) => {
    if (info && !info.vip && info.turns_left <= 0) {
      setPaywall("Bepul javoblar tugadi — VIP bilan davom eting.");
      return;
    }
    const key = newSessionKey();
    setTopic(t);
    setMock(m);
    setSessionKey(key);
    setMessages([]);
    setDone(false);
    setFinish(null);
    setNotice("");
    setLoading(true);
    try {
      const r = await api.tutorTurn({
        session_key: key,
        topic_id: t?.id ?? "erkin",
        history: [],
        voice: false,
        mode: m ? "mock" : "chat",
        mock_id: m?.id,
      });
      const msg: Msg = {
        role: "assistant",
        ar: r.reply.ar,
        translit: r.reply.translit,
        uz: r.reply.uz,
        hint: r.reply.hint_uz,
        newWords: r.reply.new_words,
        audioUrl: r.audio_url,
      };
      setMessages([msg]);
      setTurnsLeft(r.turns_left);
      speak(msg);
    } catch (e) {
      showError(e, "Ustoz javob bermadi. Qayta urinib ko'ring.");
      setTopic(null);
      setMock(null);
    } finally {
      setLoading(false);
    }
  };

  const send = async (text: string, voice: boolean) => {
    const clean = text.trim();
    if (!clean || !active || loading || done) return;
    const userMsg: Msg = { role: "user", ar: clean, voice };
    const next = [...messages, userMsg];
    setMessages(next);
    setInput("");
    setNotice("");
    setLoading(true);
    tg()?.HapticFeedback?.impactOccurred("light");
    try {
      const r = await api.tutorTurn(turnBody(sessionKey, next, voice));
      const reply: Msg = {
        role: "assistant",
        ar: r.reply.ar,
        translit: r.reply.translit,
        uz: r.reply.uz,
        hint: r.reply.hint_uz,
        answerUz: r.reply.answer_uz,
        newWords: r.reply.new_words,
        audioUrl: r.audio_url,
      };
      const graded: Msg = isMock
        ? {
            ...userMsg,
            mockScore: r.reply.score ?? 0,
            feedback: r.reply.feedback_uz ?? "",
            ideal: r.reply.ideal_ar ?? "",
            crit: {
              vocab: r.reply.vocab ?? -1,
              grammar: r.reply.grammar ?? -1,
              content: r.reply.content ?? -1,
              pron: r.reply.pron ?? -1,
            },
          }
        : {
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
      const bad = isMock ? (r.reply.score ?? 0) < 50 : !r.reply.correction_ok;
      if (bad) tg()?.HapticFeedback?.notificationOccurred("warning");
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
        const r = await api.tutorTranscribe(
          rec.blob,
          rec.filename,
          lastAssistant?.ar ?? "",
          isMock ? (sessionKey ?? "") : ""
        );
        if (!r.text) {
          setNotice("Ovoz tushunilmadi. Yaqinroq va aniqroq gapiring.");
        } else {
          await send(r.text, true);
        }
      } else {
        const m = messages[target.idx];
        const r = await api.tutorPronounce(rec.blob, rec.filename, m.ar);
        setMessages((ms) => ms.map((x, i) => (i === target.idx ? { ...x, pron: r } : x)));
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
      loadInfo();
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

  const backToList = () => {
    setTopic(null);
    setMock(null);
    setFinish(null);
    setMessages([]);
    setDone(false);
    setRevealed(new Set());
  };

  const userTurns = messages.filter((m) => m.role === "user").length;
  const outOfTurns = turnsLeft <= 0;
  const questionNo = Math.min(userTurns + 1, mock?.questions ?? 5);

  return (
    <div className="fixed inset-0 z-50 bg-sand flex flex-col max-w-md mx-auto">
      {paywall !== null && (
        <Paywall
          reason={paywall || undefined}
          onClose={() => {
            setPaywall(null);
            loadInfo();
          }}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-cardline bg-card">
        <div className="min-w-0">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
            🤖 AI USTOZ{info ? ` · ${info.level}` : ""}
          </div>
          <div className="font-extrabold truncate">
            {drillTopic
              ? `🎤 ${drillTopic.title_uz}`
              : mock
                ? `${mock.emoji} ${mock.title_uz}`
                : topic
                  ? `${topic.emoji} ${topic.title_uz}`
                  : "Jonli suhbat"}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {info &&
            (info.vip ? (
              <span className="h-9 inline-flex items-center rounded-full bg-gold-soft px-3 text-[11px] font-extrabold text-ink whitespace-nowrap">
                {active ? `👑 ${info.vip_days_left}` : `👑 VIP · ${info.vip_days_left} kun`}
              </span>
            ) : (
              <button
                onClick={() => setPaywall("")}
                className="h-9 rounded-full bg-emerald-deep px-3 text-[11px] font-extrabold text-white active:scale-95 transition-transform"
              >
                👑 VIP olish
              </button>
            ))}
          {active && canVoice && !finish && (
            <button
              onClick={toggleVoiceMode}
              className={`h-9 px-2.5 rounded-full text-sm font-extrabold border ${
                voiceMode
                  ? "bg-terracotta text-white border-terracotta"
                  : "bg-card text-ink-soft border-cardline"
              }`}
              aria-label="Faqat ovoz rejimi"
              title="Faqat ovoz: matn yashirin, bosib gapiring"
            >
              🎧
            </button>
          )}
          {active && (
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
            onClick={() =>
              drillTopic ? setDrillTopic(null) : active && !finish ? backToList() : onClose()
            }
            className="w-9 h-9 rounded-full bg-cardline text-ink-soft font-extrabold"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Talaffuz mashqi (AI'siz) */}
      {drillTopic && info && (
        <Drill
          topic={drillTopic}
          level={info.level}
          canVoice={canVoice}
          onClose={() => setDrillTopic(null)}
          onFinished={loadInfo}
        />
      )}

      {/* Mavzu / mock tanlash */}
      {!active && !drillTopic && (
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          <div className="grid grid-cols-3 gap-1 rounded-2xl bg-cardline/60 p-1">
            {(["chat", "mock", "drill"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded-xl py-2 text-[12px] font-extrabold transition-colors ${
                  tab === t ? "bg-card shadow-sm" : "text-ink-soft"
                }`}
              >
                {t === "chat" ? "💬 Suhbat" : t === "mock" ? "🎯 Mock" : "🎤 Talaffuz"}
              </button>
            ))}
          </div>

          <p className="text-sm text-ink-soft font-semibold">
            {tab === "chat"
              ? "Ustoz sizning darajangizda gaplashadi, xatolaringizni yumshoq tuzatadi. Arabcha yozing yoki 🎤 gapiring. Tushunmasangiz — o'zbekcha so'rang, tushuntiradi."
              : tab === "mock"
                ? "Kasb yoki soha bo'yicha 5 savollik og'zaki imtihon. Har javob 0–100 baholanadi, o'rtacha ball profil ballaringizga qo'shiladi."
                : "Mavzu bo'yicha 10 ta jumla: eshiting, ayting — talaffuzingiz baholanadi, aytilmagan so'zlar ko'rsatiladi. Bepul, cheklovsiz."}
          </p>

          {tab === "drill" && info && (
            <div className="flex items-center justify-between rounded-2xl bg-card border border-cardline px-4 py-2.5 text-xs font-bold">
              <span className="text-ink-soft">
                🆓 Bepul · daraja <span className="text-ink">{info.level}</span> · XP: 5+ jumla
              </span>
              <span className="text-ink-soft">
                {info.voice && canVoice ? "🎤 tayyor" : "⚠️ mikrofon yo'q"}
              </span>
            </div>
          )}

          {tab !== "drill" && info && (
            <div className="flex items-center justify-between rounded-2xl bg-card border border-cardline px-4 py-2.5 text-xs font-bold">
              <span className="text-ink-soft">
                Bugun qoldi: <span className="text-ink">{turnsLeft}</span>/{info.daily_limit}{" "}
                javob{!info.vip ? " (bepul)" : ""}
              </span>
              <span className="text-ink-soft">
                {info.voice ? "🎤 ovoz yoqilgan" : "⌨️ faqat matn"}
              </span>
            </div>
          )}

          {info && !info.vip && tab !== "drill" && (
            <button
              onClick={() => setPaywall("")}
              className="w-full text-left rounded-3xl bg-gradient-to-br from-emerald-deep to-emerald-dark p-4 text-white shadow-lg active:scale-[0.98] transition-transform"
            >
              <div className="text-[11px] font-extrabold tracking-[0.14em] text-gold-soft">
                👑 VIP TARIF
              </div>
              <div className="text-[15px] font-extrabold mt-0.5">
                {outOfTurns
                  ? "Bugungi bepul javoblar tugadi"
                  : `Bepulda kuniga ${info.free_turns} javob — VIP'da ${info.vip_turns}`}
              </div>
              <div className="text-[12px] text-white/80 font-semibold">
                Suhbat, speaking, mock imtihonlar · oyiga {fmtSum(info.price.month)} so'm
                <span className="ml-1 rounded-md bg-white/15 px-1.5 py-0.5 text-[10px] font-extrabold">
                  {fmtSum(info.price.per_day)} so'm/kun
                </span>
              </div>
            </button>
          )}

          {info && !info.ai && tab !== "drill" && (
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

          {tab === "chat" &&
            info?.topics.map((t) => (
              <ListCard
                key={t.id}
                emoji={t.emoji}
                title={t.title_uz}
                desc={t.desc_uz}
                badge={t.recommended ? "" : `${t.min_level}+`}
                disabled={!info.ai || loading}
                onClick={() => start(t, null)}
              />
            ))}

          {tab === "drill" &&
            info?.topics.map((t) => (
              <ListCard
                key={t.id}
                emoji={t.emoji}
                title={t.title_uz}
                desc={`10 jumla · ${t.desc_uz}`}
                badge={t.recommended ? "" : `${t.min_level}+`}
                disabled={loading}
                onClick={() => setDrillTopic(t)}
              />
            ))}

          {tab === "mock" && info && (
            <>
              {info.mocks.map((m) => {
                const last = info.mock_results.find((r) => r.mock_id === m.id);
                return (
                  <ListCard
                    key={m.id}
                    emoji={m.emoji}
                    title={m.title_uz}
                    desc={`${m.desc_uz} · ${m.questions} savol`}
                    badge={m.recommended ? "" : `${m.min_level}+`}
                    score={last?.score}
                    disabled={!info.ai || loading}
                    onClick={() => start(null, m)}
                  />
                );
              })}
              {info.mock_results.length > 0 && (
                <div className="rounded-2xl bg-card border border-cardline p-3">
                  <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft mb-1.5">
                    SO'NGGI NATIJALAR
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {info.mock_results.slice(0, 8).map((r, i) => {
                      const m = info.mocks.find((x) => x.id === r.mock_id);
                      return (
                        <span
                          key={i}
                          className="rounded-full bg-sand border border-cardline px-2.5 py-1 text-[11px] font-bold"
                        >
                          {m?.emoji ?? "🎯"} {r.score}% · {r.date}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}
            </>
          )}

          {loading && (
            <div className="text-center text-sm text-ink-soft font-semibold py-3">
              {tab === "mock" ? "Imtihon tayyorlanmoqda…" : "Ustoz suhbatni boshlamoqda…"}
            </div>
          )}
        </div>
      )}

      {/* Suhbat / imtihon */}
      {active && !finish && (
        <>
          {isMock && (
            <div className="flex items-center gap-2 px-4 py-2 bg-card border-b border-cardline">
              <div className="flex-1 h-1.5 rounded-full bg-cardline overflow-hidden">
                <div
                  className="h-full bg-emerald-deep rounded-full transition-[width]"
                  style={{
                    width: `${Math.min(100, (userTurns / (mock?.questions ?? 5)) * 100)}%`,
                  }}
                />
              </div>
              <span className="text-[11px] font-extrabold text-ink-soft">
                {done ? "Yakunlandi" : `Savol ${questionNo}/${mock?.questions ?? 5}`}
              </span>
            </div>
          )}

          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.map((m, i) =>
              m.role === "user" ? (
                <UserBubble key={i} m={m} mock={isMock} />
              ) : (
                <TutorBubble
                  key={i}
                  m={m}
                  showUz={showUz && !(voiceOnly && !revealed.has(i))}
                  hidden={voiceOnly && !revealed.has(i)}
                  onReveal={() => setRevealed((r) => new Set(r).add(i))}
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
                  {transcribing ? "🎧 Eshitilmoqda…" : isMock ? "Baholanmoqda…" : "Ustoz yozmoqda…"}
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
                <p className="text-sm font-bold text-emerald-dark">
                  {isMock ? "Imtihon tugadi — natijani ko'ring" : "Suhbat yakunlandi!"}
                </p>
                <button
                  onClick={finishSession}
                  className="mt-2 rounded-xl bg-emerald-deep px-5 py-2.5 text-sm font-extrabold text-white active:scale-95 transition-transform"
                >
                  Natija ›
                </button>
              </div>
            )}
          </div>

          {/* Kiritish */}
          <div className="p-3 border-t border-cardline bg-card space-y-2">
            {voiceOnly && !done && !outOfTurns ? (
              <button
                onPointerDown={(e) => {
                  e.preventDefault();
                  if (!recTarget) startRec({ kind: "answer" });
                }}
                onPointerUp={() => recTarget?.kind === "answer" && stopRec(recTarget)}
                onPointerCancel={() => recTarget?.kind === "answer" && stopRec(recTarget)}
                onPointerLeave={() => recTarget?.kind === "answer" && stopRec(recTarget)}
                onContextMenu={(e) => e.preventDefault()}
                disabled={loading || transcribing}
                style={{ touchAction: "none" }}
                className={`w-full h-16 rounded-2xl text-base font-extrabold select-none transition-transform disabled:opacity-50 ${
                  recTarget?.kind === "answer"
                    ? "bg-terracotta text-white scale-[1.02]"
                    : "bg-emerald-deep text-white active:scale-[0.98]"
                }`}
              >
                {recTarget?.kind === "answer"
                  ? `● Gapiring… ${recSeconds}s — qo'yib yuboring`
                  : transcribing
                    ? "🎧 Eshitilmoqda…"
                    : loading
                      ? "Ustoz o'ylamoqda…"
                      : "🎤 Bosib turing va gapiring"}
              </button>
            ) : recTarget?.kind === "answer" ? (
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
                  placeholder={
                    outOfTurns
                      ? info?.vip
                        ? "Bugungi limit tugadi"
                        : "Bepul javoblar tugadi — VIP"
                      : "جوابك هنا… yoki lotincha / o'zbekcha"
                  }
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
                {voiceOnly && (
                  <button onClick={toggleVoiceMode} className="ml-2 underline underline-offset-4">
                    ⌨️ yozish
                  </button>
                )}
              </span>
              {outOfTurns && !info?.vip ? (
                <button
                  onClick={() => setPaywall("Bepul javoblar tugadi — VIP bilan davom eting.")}
                  className="font-extrabold text-emerald-dark underline underline-offset-4"
                >
                  👑 VIP olish
                </button>
              ) : (
                <button
                  onClick={finishSession}
                  disabled={loading || userTurns === 0}
                  className="font-extrabold text-emerald-dark underline underline-offset-4 disabled:opacity-40"
                >
                  Yakunlash ✓
                </button>
              )}
            </div>
          </div>
        </>
      )}

      {/* Yakuniy hisobot */}
      {active && finish && (
        <Summary
          result={finish}
          messages={messages}
          mock={mock}
          saved={saved}
          onSave={saveWord}
          onAgain={() => start(topic, mock)}
          onTopics={backToList}
          onClose={onClose}
        />
      )}
    </div>
  );
}

// ────────────────────────── Bo'laklar ──────────────────────────

function ListCard({
  emoji,
  title,
  desc,
  badge,
  score,
  disabled,
  onClick,
}: {
  emoji: string;
  title: string;
  desc: string;
  badge: string;
  score?: number;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="w-full flex items-center gap-3 rounded-2xl bg-card border border-cardline p-4 text-left active:scale-[0.98] transition-transform disabled:opacity-50"
    >
      <div className="w-12 h-12 shrink-0 rounded-xl bg-gold-soft flex items-center justify-center text-2xl">
        {emoji}
      </div>
      <div className="min-w-0 flex-1">
        <div className="font-extrabold flex items-center gap-2">
          {title}
          {badge && (
            <span className="text-[10px] font-extrabold rounded-full bg-cardline px-2 py-0.5 text-ink-soft">
              {badge}
            </span>
          )}
        </div>
        <div className="text-xs text-ink-soft font-semibold">{desc}</div>
      </div>
      {score !== undefined ? (
        <span
          className={`shrink-0 rounded-lg px-2 py-1 text-[11px] font-extrabold text-white ${
            score >= 80 ? "bg-emerald-deep" : score >= 50 ? "bg-gold" : "bg-terracotta"
          }`}
        >
          {score}%
        </span>
      ) : (
        <span className="text-emerald-dark font-extrabold text-xl">›</span>
      )}
    </button>
  );
}

function ScoreBadge({ score }: { score: number }) {
  return (
    <span
      className={`inline-flex items-center rounded-lg px-2 py-0.5 text-[11px] font-extrabold text-white ${
        score >= 80 ? "bg-emerald-deep" : score >= 50 ? "bg-gold" : "bg-terracotta"
      }`}
    >
      {score}/100
    </span>
  );
}

const CRITERIA: { k: keyof MockCriteria; label: string; icon: string }[] = [
  { k: "vocab", label: "Lug'at", icon: "📖" },
  { k: "grammar", label: "Grammatika", icon: "🧩" },
  { k: "content", label: "Mazmun", icon: "💬" },
  { k: "pron", label: "Talaffuz", icon: "🎤" },
];

function critColor(v: number) {
  return v >= 80 ? "text-emerald-dark" : v >= 50 ? "text-gold" : "text-terracotta";
}

/** Mock javobi mezonlari — bitta qatorda kichik yorliqlar (-1 = ko'rsatilmaydi) */
function CriteriaChips({ c }: { c: MockCriteria }) {
  const items = CRITERIA.filter(({ k }) => c[k] >= 0);
  if (!items.length) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {items.map(({ k, label, icon }) => (
        <span key={k} className="rounded-md bg-sand px-1.5 py-0.5 text-[10px] font-extrabold text-ink-soft">
          {icon} {label} <span className={critColor(c[k])}>{c[k]}</span>
        </span>
      ))}
    </div>
  );
}

/** Yakuniy hisobot: mezonlar bo'yicha chiziqli diagramma */
function CriteriaBars({ c }: { c: MockCriteria }) {
  const items = CRITERIA.filter(({ k }) => c[k] >= 0);
  return (
    <section className="rounded-2xl bg-card border border-cardline p-4 space-y-2.5">
      <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">MEZONLAR BO'YICHA</div>
      {items.map(({ k, label, icon }) => (
        <div key={k}>
          <div className="flex items-center justify-between text-xs font-bold">
            <span>
              {icon} {label}
            </span>
            <span className={critColor(c[k])}>{c[k]}</span>
          </div>
          <div className="mt-1 h-2 rounded-full bg-cardline overflow-hidden">
            <div
              className={`h-full rounded-full ${
                c[k] >= 80 ? "bg-emerald-deep" : c[k] >= 50 ? "bg-gold" : "bg-terracotta"
              }`}
              style={{ width: `${Math.max(4, c[k])}%` }}
            />
          </div>
        </div>
      ))}
      {c.pron < 0 && (
        <div className="text-[11px] text-ink-soft font-semibold">
          🎤 Talaffuz faqat ovozli javoblarda o'lchanadi — keyingi safar mikrofon bilan javob bering.
        </div>
      )}
    </section>
  );
}

function UserBubble({ m, mock }: { m: Msg; mock: boolean }) {
  const c = m.correction;
  return (
    <div className="flex flex-col items-end gap-1">
      <div className="max-w-[82%] rounded-2xl px-4 py-2.5 bg-emerald-deep text-white">
        <div className="font-arabic text-xl leading-snug" dir="auto">
          {m.voice && <span className="text-sm mr-1 opacity-80">🎤</span>}
          {m.ar}
        </div>
      </div>

      {mock && m.mockScore !== undefined && (
        <div className="max-w-[88%] rounded-xl bg-card border border-cardline px-3 py-2 text-xs font-semibold space-y-1">
          <div className="flex items-center gap-2">
            <ScoreBadge score={m.mockScore} />
            {m.feedback && <span className="text-ink-soft">{m.feedback}</span>}
          </div>
          {m.crit && <CriteriaChips c={m.crit} />}
          {m.ideal && (
            <div className="rounded-lg bg-sand px-2.5 py-1.5">
              <div className="text-[10px] font-extrabold text-ink-soft">NAMUNAVIY JAVOB</div>
              <div className="font-arabic text-lg leading-snug" dir="rtl">
                {m.ideal}
              </div>
            </div>
          )}
        </div>
      )}

      {!mock && c && (
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
  hidden = false,
  onReveal,
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
  /** Faqat ovoz rejimi: matn xiralashtirilgan — avval eshitib, keyin ochiladi */
  hidden?: boolean;
  onReveal?: () => void;
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
      {m.answerUz && (
        <div className="max-w-[92%] rounded-2xl bg-card border border-emerald-deep/30 px-4 py-3 text-sm font-semibold">
          <div className="text-[10px] font-extrabold tracking-[0.12em] text-emerald-dark mb-1">
            📘 TUSHUNTIRISH
          </div>
          <div className="whitespace-pre-line leading-snug">{m.answerUz}</div>
        </div>
      )}

      <div className="max-w-[88%] rounded-2xl px-4 py-3 bg-card border border-cardline">
        <div className={`font-arabic text-2xl leading-relaxed ${hidden ? "blur-sm select-none" : ""}`} dir="rtl">
          {m.pron
            ? m.pron.words.map((w, i) => (
                <span key={i} className={w.ok ? "" : "text-terracotta underline decoration-2"}>
                  {w.ar}{" "}
                </span>
              ))
            : m.ar}
        </div>
        {hidden && (
          <button
            onClick={onReveal}
            className="mt-1 h-8 px-2.5 rounded-lg bg-cardline text-xs font-extrabold text-ink-soft active:scale-95 transition-transform"
          >
            👁 Matnni ko'rsatish
          </button>
        )}
        {m.translit && !hidden && (
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
          {m.pron && (
            <span
              className={`h-8 inline-flex items-center px-2.5 rounded-lg text-xs font-extrabold ${
                m.pron.score >= 80
                  ? "bg-emerald-deep text-white"
                  : m.pron.score >= 50
                    ? "bg-gold text-white"
                    : "bg-terracotta text-white"
              }`}
            >
              🎯 {m.pron.score}%
            </span>
          )}
        </div>
        {m.pron && m.pron.transcript && m.pron.score < 80 && (
          <div className="mt-1.5 text-[11px] text-ink-soft font-semibold" dir="rtl">
            Eshitildi: {m.pron.transcript}
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
  mock,
  saved,
  onSave,
  onAgain,
  onTopics,
  onClose,
}: {
  result: TutorFinishResult;
  messages: Msg[];
  mock: TutorMock | null;
  saved: Set<string>;
  onSave: (w: TutorNewWord) => void;
  onAgain: () => void;
  onTopics: () => void;
  onClose: () => void;
}) {
  const fixes = messages.filter((m) => m.role === "user" && m.correction && !m.correction.ok);
  const answers = messages.filter((m) => m.role === "user" && m.mockScore !== undefined);
  const words = new Map<string, TutorNewWord>();
  messages.forEach((m) => m.newWords?.forEach((w) => words.set(w.ar, w)));
  const pct = result.turns ? Math.round((result.ok_turns / result.turns) * 100) : 0;
  const score = result.score ?? 0;
  const headline = mock ? score : pct;

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      <div className="rounded-3xl bg-gradient-to-br from-emerald-deep to-emerald-dark p-5 text-white text-center shadow-lg">
        <div className="text-3xl">{headline >= 80 ? "🌟" : headline >= 50 ? "👏" : "💪"}</div>
        <div className="text-xl font-extrabold mt-1">
          {mock ? `${mock.emoji} ${mock.title_uz}` : "Suhbat yakunlandi"}
        </div>
        {mock ? (
          <>
            <div className="mt-2 text-[44px] leading-none font-extrabold">{score}</div>
            <div className="text-sm text-white/80 font-semibold">ball (100 dan) · {result.turns} javob</div>
          </>
        ) : (
          <div className="text-sm text-white/80 font-semibold">
            {result.turns} javob · {pct}% xatosiz
            {result.voice_turns > 0 ? ` · 🎤 ${result.voice_turns}` : ""}
          </div>
        )}
        <div className="mt-3 inline-block rounded-full bg-white/15 px-4 py-1.5 font-extrabold">
          {result.xp > 0
            ? `+${result.xp} XP profilga qo'shildi`
            : mock
              ? "XP: shu mock uchun bugun olingan yoki imtihon tugallanmagan"
              : "XP uchun kamida 3 javob"}
        </div>
      </div>

      {mock && result.certificate && (
        <section className="rounded-2xl bg-card border-2 border-gold p-3">
          <img src={result.certificate.png_url} alt="Sertifikat" className="rounded-xl w-full" />
          <p className="mt-2 text-xs text-ink-soft font-semibold text-center">
            🏅 Shaxsiy rekord! Sertifikat botga yuborildi — u yerdan do'stlaringizga ulashing.
          </p>
        </section>
      )}

      {mock && result.criteria && <CriteriaBars c={result.criteria} />}

      {mock && answers.length > 0 && (
        <section className="rounded-2xl bg-card border border-cardline p-4">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2">
            SAVOLLAR BO'YICHA
          </div>
          <div className="space-y-2.5">
            {answers.map((m, i) => (
              <div key={i} className="text-sm">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-extrabold text-ink-soft">#{i + 1}</span>
                  <ScoreBadge score={m.mockScore ?? 0} />
                </div>
                <div className="font-arabic text-base mt-0.5" dir="auto">
                  {m.ar}
                </div>
                {m.feedback && (
                  <div className="text-xs text-ink-soft font-semibold">{m.feedback}</div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

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
          {mock ? "Boshqa mock" : "Boshqa mavzu"}
        </button>
      </div>
      <button onClick={onClose} className="w-full text-sm font-bold text-ink-soft py-2">
        Bosh sahifaga
      </button>
    </div>
  );
}
