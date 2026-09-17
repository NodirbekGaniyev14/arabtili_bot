import { useEffect, useRef, useState } from "react";
import {
  api,
  wordClass,
  type ListenAnswer,
  type ListenFinish,
  type ListenStart,
  type TutorTopic,
} from "../lib/api";
import { playUrl } from "../lib/audio";
import RateBar from "../components/RateBar";

/** Tinglab tushunish — AI'siz, bepul: mavzu bo'yicha 10 ta jumla.
 *
 *  Matn OLDINDAN ko'rinmaydi — faqat 🔊. Tanlash: 4 tarjimadan birini bosing;
 *  diktant: eshitganingizni yozing (o'xshashlik bali, aytilmagan so'zlar qizil).
 *  Javobdan keyin arabcha matn + translit ochiladi. XP: kamida 5 jumla,
 *  mavzu+rejim uchun kuniga bir marta.
 */

const tg = () => window.Telegram?.WebApp;

interface Props {
  topic: TutorTopic;
  kind: "choice" | "dictation";
  onClose: () => void;
  onFinished?: () => void;
}

function scoreColor(s: number) {
  return s >= 80 ? "bg-emerald-deep text-white" : s >= 50 ? "bg-gold text-white" : "bg-terracotta text-white";
}

export default function Listening({ topic, kind, onClose, onFinished }: Props) {
  const [data, setData] = useState<ListenStart | null>(null);
  const [error, setError] = useState("");
  const [idx, setIdx] = useState(0);
  const [results, setResults] = useState<Record<number, ListenAnswer & { picked?: number }>>({});
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [finish, setFinish] = useState<ListenFinish | null>(null);
  const [finishing, setFinishing] = useState(false);
  const [notice, setNotice] = useState("");
  const [plays, setPlays] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = () => {
    setData(null);
    setError("");
    setIdx(0);
    setResults({});
    setFinish(null);
    setText("");
    api
      .tutorListen(topic.id, kind)
      .then((d) => {
        setData(d);
        // Birinchi jumla — tugma bosilgan kontekstda avtoijro
        playUrl(d.items[0]?.audio_url);
      })
      .catch(() => setError("Jumlalar yuklanmadi. Qayta urinib ko'ring."));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topic.id, kind]);

  const item = data?.items[idx];
  const total = data?.items.length ?? 0;
  const result = results[idx];
  const scoredCount = Object.keys(results).length;
  const isLast = idx >= total - 1;

  const play = () => {
    if (!item) return;
    setPlays((n) => n + 1);
    playUrl(item.audio_url);
  };

  const goTo = (i: number) => {
    setIdx(i);
    setText("");
    setNotice("");
    const it = data?.items[i];
    if (it) playUrl(it.audio_url);
  };

  const submit = async (choice?: number) => {
    if (!data || !item || busy || result) return;
    if (kind === "dictation" && !text.trim()) return;
    setBusy(true);
    try {
      const r = await api.tutorListenAnswer({
        key: data.key,
        idx: item.idx,
        choice,
        text: kind === "dictation" ? text.trim() : "",
      });
      setResults((rs) => ({ ...rs, [item.idx]: { ...r, picked: choice } }));
      tg()?.HapticFeedback?.notificationOccurred(r.correct ? "success" : "warning");
    } catch (e) {
      const err = e as { status?: number; detail?: string };
      setNotice(err?.status === 404 ? "Mashq muddati tugadi — qaytadan boshlang." : err?.detail || "Xatolik.");
    } finally {
      setBusy(false);
    }
  };

  const finishAll = async () => {
    if (!data || finishing) return;
    setFinishing(true);
    try {
      const f = await api.tutorListenFinish(data.key);
      setFinish(f);
      if (f.xp > 0) tg()?.HapticFeedback?.notificationOccurred("success");
      onFinished?.();
    } catch {
      setNotice("Natija saqlanmadi. Qayta urinib ko'ring.");
    } finally {
      setFinishing(false);
    }
  };

  // ── Yakun ──
  if (finish && data) {
    const rows = finish.items
      .map((it, i) => ({ ...it, score: finish.scores[i] }))
      .sort((a, b) => (a.score < 0 ? 1 : b.score < 0 ? -1 : a.score - b.score));
    return (
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <div className="rounded-3xl bg-gradient-to-br from-emerald-deep to-emerald-dark p-5 text-white text-center shadow-lg">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-gold-soft">
            🎧 TINGLASH · {topic.title_uz.toUpperCase()} · {kind === "dictation" ? "DIKTANT" : "TANLASH"}
          </div>
          <div className="text-5xl font-extrabold mt-1">{finish.score}%</div>
          <div className="text-sm font-semibold text-white/85 mt-1">
            {finish.count}/{finish.total} jumla
            {finish.xp > 0 ? ` · +${finish.xp} XP` : finish.count < 5 ? " · XP uchun kamida 5 ta" : ""}
          </div>
          {finish.xp === 0 && finish.count >= 5 && (
            <div className="text-[11px] text-white/70 mt-1">Bu mavzu uchun bugungi XP allaqachon olingan</div>
          )}
        </div>

        <RateBar sessionKey={data.key} mode="listen" topic={topic.id} question="Tinglash mashqi foydali bo'ldimi?" />

        <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">JUMLALAR (avval qiyinlari)</div>
        {rows.map((r, i) => (
          <div key={i} className="rounded-2xl bg-card border border-cardline px-4 py-3 flex items-start gap-2">
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
              <div className="text-[11px] text-ink-soft font-semibold italic">{r.translit}</div>
              <div className="text-xs text-ink-soft font-semibold">{r.uz}</div>
            </div>
          </div>
        ))}

        <div className="grid grid-cols-2 gap-2 pt-1">
          <button
            onClick={load}
            className="rounded-2xl bg-emerald-deep py-3 text-sm font-extrabold text-white active:scale-95 transition-transform"
          >
            🔁 Yana
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
                    : s >= 80
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
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {/* Audio kartasi — matn javobgacha yashirin */}
        <div className="rounded-3xl bg-card border border-cardline p-5 shadow-sm text-center">
          <button
            onClick={play}
            className="mx-auto w-24 h-24 rounded-full bg-emerald-deep text-white text-4xl shadow-lg active:scale-95 transition-transform"
            aria-label="Eshitish"
          >
            🔊
          </button>
          <div className="mt-3 text-xs font-bold text-ink-soft">
            {result ? "Javob berildi" : plays > 1 ? `Yana eshitish (${plays})` : "Eshiting, keyin javob bering"}
          </div>

          {result && (
            <div className="mt-3 rounded-2xl bg-sand px-4 py-3 text-left">
              <div className="font-arabic text-2xl leading-relaxed" dir="rtl">
                {kind === "dictation" && result.words
                  ? result.words.map((w, i) => (
                      <span key={i} className={wordClass(w)}>
                        {w.ar}{" "}
                      </span>
                    ))
                  : result.ar}
              </div>
              <div className="text-xs text-ink-soft font-semibold italic mt-1">{result.translit}</div>
              <div className="text-sm font-semibold mt-1">{result.uz}</div>
              <div className="mt-2 inline-flex items-center gap-2">
                <span className={`rounded-lg px-2.5 py-1 text-xs font-extrabold ${scoreColor(result.score)}`}>
                  {kind === "dictation" ? `🎯 ${result.score}%` : result.correct ? "✅ To'g'ri" : "❌ Noto'g'ri"}
                </span>
                {result.word && (
                  <span className="rounded-lg bg-card border border-cardline px-2 py-1 text-[11px] font-bold">
                    <span className="font-arabic text-sm">{result.word.ar}</span> · {result.word.uz}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Javob */}
        {kind === "choice" && item.options && (
          <div className="space-y-2">
            {item.options.map((opt, i) => {
              const answered = !!result;
              const isCorrect = answered && result.answer === i;
              const isPicked = answered && result.picked === i;
              return (
                <button
                  key={i}
                  onClick={() => submit(i)}
                  disabled={answered || busy}
                  className={`w-full text-left rounded-2xl px-4 py-3 text-sm font-bold border transition-colors ${
                    isCorrect
                      ? "bg-emerald-deep text-white border-emerald-deep"
                      : isPicked
                        ? "bg-terracotta text-white border-terracotta"
                        : "bg-card border-cardline active:bg-sand"
                  } disabled:opacity-90`}
                >
                  <span className="mr-2 text-ink-soft/70">{"ABCD"[i]}.</span>
                  {opt}
                </button>
              );
            })}
          </div>
        )}

        {kind === "dictation" && !result && (
          <div className="rounded-2xl bg-card border border-cardline p-3 space-y-2">
            <input
              ref={inputRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              dir="rtl"
              placeholder="اكتب ما سمعت…"
              className="w-full rounded-xl bg-sand border border-cardline px-3 py-2.5 font-arabic text-xl outline-none focus:border-emerald-deep/40"
            />
            <div className="text-[11px] text-ink-soft font-semibold">
              Harakatsiz yozsangiz ham bo'ladi — so'zlar solishtiriladi.
            </div>
          </div>
        )}

        {notice && (
          <div className="rounded-2xl bg-gold-soft border border-gold/30 p-3 text-sm font-semibold">{notice}</div>
        )}
      </div>

      <div className="p-3 border-t border-cardline bg-card space-y-2">
        <div className="flex items-center gap-2">
          {kind === "dictation" && !result && (
            <button
              onClick={() => submit()}
              disabled={busy || !text.trim()}
              className="flex-1 h-12 rounded-2xl bg-emerald-deep text-white text-sm font-extrabold active:scale-[0.98] transition-transform disabled:opacity-50"
            >
              {busy ? "…" : "Tekshirish"}
            </button>
          )}
          <button
            onClick={() => (isLast ? finishAll() : goTo(idx + 1))}
            disabled={busy || finishing}
            className={`h-12 px-4 rounded-2xl text-sm font-extrabold active:scale-[0.98] transition-transform disabled:opacity-50 ${
              kind === "choice" || result ? "flex-1" : ""
            } ${result ? "bg-gold-soft text-ink" : "bg-card border border-cardline text-ink-soft"}`}
          >
            {isLast ? (finishing ? "…" : "Yakunlash ✓") : result ? "Keyingi →" : "O'tkazish →"}
          </button>
        </div>
        <div className="flex items-center justify-between text-[11px] font-bold text-ink-soft px-0.5">
          <span>{scoredCount} ta javob · XP uchun kamida 5</span>
          {scoredCount > 0 && !isLast && (
            <button
              onClick={finishAll}
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
