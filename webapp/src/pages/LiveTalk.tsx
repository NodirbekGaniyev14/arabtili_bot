import { useEffect, useRef, useState } from "react";
import { api, type LiveReview, type TutorTopic } from "../lib/api";
import { LiveCall, liveSupported, type LiveState } from "../lib/liveVoice";

/** K30 «📞 Jonli suhbat» — Jamal ustoz bilan real vaqtda ovozli gaplashish (Gemini Live, server relay orqali).
 *  Qo'ng'iroq faqat tugma bosilganda boshlanadi (iOS: ovoz faqat bosish ichida yoqiladi).
 *  Oxirida — tahlil (Claude): xatolar daftarga, yangi so'zlar, XP. */

type Line = { role: "user" | "model"; text: string };

const tg = () => window.Telegram?.WebApp;

function mmss(s: number): string {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

const END_TEXT: Record<string, string> = {
  idle: "Uzoq jimlik bo'ldi — suhbat yakunlandi.",
  time: "Bitta suhbat vaqti tugadi. Yana davom etish uchun yangi qo'ng'iroq boshlang.",
  closed: "Suhbat yakunlandi.",
  error: "Aloqa uzildi — suhbat saqlandi.",
};

export default function LiveTalk({
  topic,
  onClose,
  onFinished,
}: {
  topic: TutorTopic;
  onClose: () => void;
  onFinished?: () => void;
}) {
  const [started, setStarted] = useState(false);
  const [state, setState] = useState<LiveState>("connecting");
  const [lines, setLines] = useState<Line[]>([]);
  const [partial, setPartial] = useState<Line | null>(null);
  const [level, setLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [maxSec, setMaxSec] = useState(0);
  const [error, setError] = useState("");
  const [ended, setEnded] = useState<{ reason: string; seconds: number; sessionId: number } | null>(null);
  const [review, setReview] = useState<LiveReview | null>(null);
  const [reviewErr, setReviewErr] = useState("");
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const call = useRef<LiveCall | null>(null);
  const partialRef = useRef<Line | null>(null);
  const t0 = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  const flush = () => {
    const p = partialRef.current;
    if (p && p.text.trim()) setLines((ls) => [...ls, p]);
    partialRef.current = null;
    setPartial(null);
  };
  const add = (role: Line["role"], text: string) => {
    if (partialRef.current && partialRef.current.role !== role) flush();
    const p = partialRef.current ?? { role, text: "" };
    partialRef.current = { role, text: p.text + text };
    setPartial(partialRef.current);
  };

  useEffect(() => () => call.current?.cleanup(), []);

  useEffect(() => {
    if (!started || ended || error) return;
    const id = window.setInterval(() => setElapsed((Date.now() - t0.current) / 1000), 500);
    return () => window.clearInterval(id);
  }, [started, ended, error]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [lines, partial]);

  const begin = () => {
    setStarted(true);
    setError("");
    setEnded(null);
    setReview(null);
    setReviewErr("");
    setLines([]);
    partialRef.current = null;
    setPartial(null);
    setElapsed(0);
    t0.current = Date.now();
    tg()?.HapticFeedback?.impactOccurred("medium");
    const c = new LiveCall({
      onState: setState,
      onUserText: (t) => add("user", t),
      onModelText: (t) => add("model", t),
      onTurn: flush,
      onLevel: setLevel,
      onReady: (s) => {
        setMaxSec(s);
        t0.current = Date.now();
      },
      onEnd: (e) => {
        flush();
        setEnded(e);
        tg()?.HapticFeedback?.notificationOccurred("success");
        if (e.sessionId) {
          api
            .liveReview(e.sessionId)
            .then((r) => {
              setReview(r);
              onFinished?.();
            })
            .catch(() => setReviewErr("Tahlil yuklanmadi — suhbat saqlangan."));
        }
      },
      onError: (detail) => {
        flush();
        setError(detail);
        tg()?.HapticFeedback?.notificationOccurred("error");
      },
    });
    call.current = c;
    void c.start(topic.id);
  };

  const saveWord = (ar: string, uz: string) => {
    if (saved.has(ar)) return;
    setSaved((s) => new Set(s).add(ar));
    api.tutorSaveWord(ar, uz).catch(() => undefined);
  };

  const inCall = started && !ended && !error;
  const speaking = state === "speaking";
  const ring = speaking ? 1 : Math.min(1, level * 6);

  return (
    <div className="fixed inset-0 z-[55] bg-sand flex flex-col max-w-md mx-auto">
      {/* Sarlavha */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-cardline bg-card">
        <div className="min-w-0">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">📞 JONLI SUHBAT</div>
          <div className="font-extrabold truncate">
            {topic.emoji} {topic.title_uz}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {inCall && (
            <span className="rounded-full bg-cardline px-2.5 py-1 text-[12px] font-extrabold tabular-nums text-ink-soft">
              {mmss(elapsed)}
              {maxSec ? ` / ${mmss(maxSec)}` : ""}
            </span>
          )}
          <button
            onClick={() => {
              call.current?.cleanup();
              onClose();
            }}
            className="w-9 h-9 rounded-full bg-cardline text-ink-soft font-extrabold"
            aria-label="Yopish"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Boshlash ekrani */}
      {!started && (
        <div className="flex-1 overflow-y-auto p-5 flex flex-col items-center text-center">
          <div className="mt-6 w-28 h-28 rounded-full bg-gradient-to-br from-emerald-deep to-emerald-dark text-white flex items-center justify-center text-5xl font-arabic shadow-lg">
            ج
          </div>
          <div className="mt-4 text-xl font-extrabold">Jamal bilan jonli gaplashing</div>
          <p className="mt-2 text-sm font-semibold text-ink-soft leading-relaxed">
            Telefon qo'ng'irog'idek: siz arabcha gapirasiz, ustoz eshitadi, javob beradi va xatoni o'zbekcha tushuntiradi.
            Tushunmasangiz — o'zbekcha so'rang.
          </p>
          <div className="mt-4 w-full space-y-2 text-left">
            {[
              "🎧 Quloqchin bilan eng yaxshi ishlaydi",
              "🤫 Tinch joyda gapiring",
              "✋ Ustoz gapirayotganda bosib, gapini bo'lishingiz mumkin",
            ].map((t) => (
              <div key={t} className="rounded-2xl bg-card border border-cardline px-4 py-2.5 text-[13px] font-semibold">
                {t}
              </div>
            ))}
          </div>
          {!liveSupported() && (
            <div className="mt-4 rounded-2xl bg-terracotta/10 border border-terracotta/30 px-4 py-3 text-sm font-semibold">
              Bu qurilma brauzeri jonli ovozni qo'llamaydi. Telegram ilovasini yangilab ko'ring.
            </div>
          )}
          <button
            onClick={begin}
            disabled={!liveSupported()}
            className="mt-6 w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-[16px] active:scale-[0.98] transition-transform disabled:opacity-40"
          >
            📞 Qo'ng'iroqni boshlash
          </button>
        </div>
      )}

      {/* Suhbat */}
      {started && !ended && !error && (
        <>
          <div className="flex flex-col items-center pt-6 pb-3">
            <div className="relative w-32 h-32 flex items-center justify-center">
              <div
                className={`absolute inset-0 rounded-full transition-transform duration-150 ${
                  speaking ? "bg-emerald-deep/25 animate-pulse" : "bg-gold/30"
                }`}
                style={{ transform: `scale(${1 + ring * 0.35})` }}
              />
              <div className="relative w-28 h-28 rounded-full bg-gradient-to-br from-emerald-deep to-emerald-dark text-white flex items-center justify-center text-5xl font-arabic shadow-lg">
                ج
              </div>
            </div>
            <div className="mt-3 text-[14px] font-extrabold">
              {state === "connecting"
                ? "Ulanmoqda…"
                : speaking
                  ? "Ustoz gapirmoqda…"
                  : "Sizni tinglayapman — gapiring 🎤"}
            </div>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 space-y-2 pb-3">
            {[...lines, ...(partial ? [partial] : [])].map((l, i) => (
              <div key={i} className={`flex ${l.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  dir="auto"
                  className={`max-w-[85%] rounded-2xl px-3 py-2 text-[15px] font-semibold leading-snug ${
                    l.role === "user"
                      ? "bg-emerald-deep text-white rounded-tr-md"
                      : "bg-card border border-cardline rounded-tl-md"
                  } ${partial === l ? "opacity-80" : ""}`}
                >
                  {l.text}
                </div>
              </div>
            ))}
          </div>

          <div className="p-3 border-t border-cardline bg-card grid grid-cols-2 gap-2">
            <button
              onClick={() => call.current?.interrupt()}
              disabled={!speaking}
              className="rounded-2xl bg-gold-soft border border-gold/40 py-3.5 text-sm font-extrabold active:scale-95 transition-transform disabled:opacity-40"
            >
              ✋ Gapini bo'lish
            </button>
            <button
              onClick={() => call.current?.end()}
              className="rounded-2xl bg-terracotta py-3.5 text-sm font-extrabold text-white active:scale-95 transition-transform"
            >
              ⏹ Yakunlash
            </button>
          </div>
        </>
      )}

      {/* Xato */}
      {error && (
        <div className="flex-1 p-5 flex flex-col items-center justify-center text-center">
          <div className="text-4xl">📵</div>
          <div className="mt-3 font-extrabold">{error}</div>
          <button
            onClick={begin}
            className="mt-5 w-full rounded-2xl bg-emerald-deep py-3.5 text-white font-extrabold active:scale-[0.98] transition-transform"
          >
            🔁 Qayta urinish
          </button>
          <button onClick={onClose} className="mt-2 text-sm font-bold text-ink-soft underline underline-offset-4">
            Yopish
          </button>
        </div>
      )}

      {/* Yakun va tahlil */}
      {ended && (
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          <div className="rounded-3xl bg-gradient-to-br from-emerald-deep to-emerald-dark p-5 text-white shadow-lg">
            <div className="text-[11px] font-extrabold tracking-[0.14em] text-gold-soft">📞 SUHBAT YAKUNLANDI</div>
            <div className="mt-1 text-2xl font-extrabold">{mmss(ended.seconds || elapsed)}</div>
            <div className="text-[13px] font-semibold text-white/85">
              {END_TEXT[ended.reason] ?? "Barakalla! Har kungi jonli suhbat — eng tez yo'l."}
              {review && review.xp > 0 ? ` · +${review.xp} XP` : ""}
            </div>
          </div>

          {!review && !reviewErr && ended.sessionId > 0 && (
            <div className="rounded-2xl bg-card border border-cardline p-4 text-sm font-semibold text-ink-soft">
              ⏳ Ustoz suhbatni tahlil qilmoqda…
            </div>
          )}
          {reviewErr && (
            <div className="rounded-2xl bg-gold-soft border border-gold/30 p-4 text-sm font-semibold">{reviewErr}</div>
          )}

          {review && (
            <>
              {review.summary_uz && (
                <div className="rounded-2xl bg-card border border-cardline p-4 text-[14px] font-semibold leading-relaxed">
                  {review.summary_uz}
                </div>
              )}
              {review.mistakes.length > 0 && (
                <section className="rounded-3xl bg-card border border-cardline p-4">
                  <div className="text-[11px] font-extrabold tracking-[0.12em] mb-2">✏️ TUZATISHLAR (xatolar daftariga qo'shildi)</div>
                  <div className="space-y-2">
                    {review.mistakes.map((m, i) => (
                      <div key={i} className="rounded-2xl bg-sand border border-cardline p-3">
                        <div dir="rtl" className="font-arabic text-lg text-ink-soft line-through decoration-terracotta/60">
                          {m.said}
                        </div>
                        <div dir="rtl" className="font-arabic text-xl font-bold text-emerald-dark">
                          {m.fixed_ar}
                        </div>
                        <div className="text-[12px] font-semibold mt-0.5">{m.note_uz}</div>
                      </div>
                    ))}
                  </div>
                </section>
              )}
              {review.words.length > 0 && (
                <section className="rounded-3xl bg-card border border-cardline p-4">
                  <div className="text-[11px] font-extrabold tracking-[0.12em] mb-2">📚 SUHBATDAGI SO'ZLAR</div>
                  <div className="space-y-1.5">
                    {review.words.map((w) => (
                      <div key={w.ar} className="flex items-center gap-3 rounded-2xl bg-sand border border-cardline px-3 py-2">
                        <span dir="rtl" className="font-arabic text-xl">
                          {w.ar}
                        </span>
                        <span className="min-w-0 flex-1 text-[12px] font-semibold text-ink-soft">
                          {w.translit} — {w.uz}
                        </span>
                        <button
                          onClick={() => saveWord(w.ar, w.uz)}
                          className="shrink-0 rounded-xl bg-emerald-deep/10 px-2.5 py-1.5 text-[11px] font-extrabold text-emerald-dark"
                        >
                          {saved.has(w.ar) ? "✓" : "+ Lug'at"}
                        </button>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}

          {lines.length > 0 && (
            <details className="rounded-2xl bg-card border border-cardline p-4">
              <summary className="text-[12px] font-extrabold cursor-pointer">💬 Suhbat matni</summary>
              <div className="mt-2 space-y-1.5">
                {lines.map((l, i) => (
                  <div key={i} dir="auto" className="text-[13px] font-semibold">
                    <span className="text-ink-soft">{l.role === "user" ? "Siz: " : "Jamal: "}</span>
                    {l.text}
                  </div>
                ))}
              </div>
            </details>
          )}

          <button
            onClick={begin}
            className="w-full rounded-2xl bg-emerald-deep py-3.5 text-white font-extrabold active:scale-[0.98] transition-transform"
          >
            📞 Yana gaplashish
          </button>
          <button onClick={onClose} className="w-full py-2 text-sm font-bold text-ink-soft underline underline-offset-4">
            Yopish
          </button>
        </div>
      )}
    </div>
  );
}
