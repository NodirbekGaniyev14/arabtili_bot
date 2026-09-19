import { useEffect, useRef, useState } from "react";
import { api, type DailyInfo, type DailyResult } from "../lib/api";
import { playUrl, speakText } from "../lib/audio";
import { MAX_SECONDS, Recorder, micSupported } from "../lib/recorder";
import RateBar from "../components/RateBar";

/** Kunlik speaking savoli — hamma uchun bepul, kuniga bitta.
 *
 *  Savol darajaga mos (content/daily_speaking.json), 🔊 eshitiladi; javob
 *  🎤 ovoz (STT) yoki matn bilan → ustoz baholaydi (ball, izoh, namunaviy
 *  javob, tuzatilgan shakl) → XP (+2 ovozli). Ketma-ket kunlar — 🔥 streak.
 */

const tg = () => window.Telegram?.WebApp;

interface Props {
  onClose: () => void;
  /** Javob berilgach — bosh sahifa statistikasi (XP, streak) yangilansin */
  onDone?: () => void;
}

export default function DailyTask({ onClose, onDone }: Props) {
  const [info, setInfo] = useState<DailyInfo | null>(null);
  const [error, setError] = useState("");
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<DailyResult | null>(null);
  const [streak, setStreak] = useState(0);
  const [xp, setXp] = useState(0);
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [transcribing, setTranscribing] = useState(false);
  const [notice, setNotice] = useState("");
  const [showHelp, setShowHelp] = useState(true);
  const recorder = useRef(new Recorder());

  useEffect(() => {
    api
      .getDaily()
      .then((d) => {
        setInfo(d);
        setStreak(d.streak);
        if (d.done) setResult(d.done);
        setShowHelp(!["B1", "B2"].includes(d.level));
      })
      .catch(() => setError("Savol yuklanmadi. Qayta urinib ko'ring."));
    const r = recorder.current;
    return () => {
      if (r.active) r.stop();
    };
  }, []);

  useEffect(() => {
    if (!recording) return;
    setSeconds(0);
    const id = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [recording]);

  const canVoice = !!info?.voice && micSupported();
  const q = info?.question;

  const speakQ = () => {
    if (!q) return;
    playUrl(q.audio_url).then((ok) => {
      if (!ok) speakText(q.ar);
    });
  };

  const submit = async (answer: string, voice: boolean) => {
    const clean = answer.trim();
    if (!clean || sending) return;
    setSending(true);
    setNotice("");
    try {
      const r = await api.answerDaily(voice ? `🎤 ${clean}` : clean, voice);
      setResult(r.result);
      setStreak(r.streak);
      setXp(r.xp);
      setText("");
      tg()?.HapticFeedback?.notificationOccurred(r.result.score >= 50 ? "success" : "warning");
      onDone?.();
    } catch (e) {
      const err = e as { status?: number; detail?: string };
      if (err?.status === 409) {
        setNotice("Bugungi savolga javob berilgan — ertaga yangi savol.");
        api.getDaily().then((d) => d.done && setResult(d.done)).catch(() => {});
      } else {
        setNotice(err?.detail || "Ustoz javob bermadi. Qayta urinib ko'ring.");
      }
    } finally {
      setSending(false);
    }
  };

  const startRec = async () => {
    if (recording || sending || transcribing) return;
    try {
      await recorder.current.start(() => stopRec());
      setRecording(true);
      tg()?.HapticFeedback?.impactOccurred("medium");
    } catch {
      setNotice("Mikrofonga ruxsat berilmadi — yozib javob bering.");
    }
  };

  const stopRec = async () => {
    const rec = await recorder.current.stop();
    setRecording(false);
    if (!rec || !q) {
      setNotice("Yozuv juda qisqa. Qayta urinib ko'ring.");
      return;
    }
    setTranscribing(true);
    try {
      const r = await api.tutorTranscribe(rec.blob, rec.filename, q.ar);
      if (!r.text) {
        setNotice("Ovoz tushunilmadi. Mikrofonga yaqinroq, sekinroq va aniqroq gapiring.");
      } else if (r.confidence >= 0 && r.confidence < 45) {
        // Ishonch past — matnni ko'rsatamiz, o'quvchi tuzatib yuboradi (kunlik savol bitta urinish)
        setText(r.text);
        setNotice("Tushunilgan matn pastda — tekshirib yuboring yoki qayta gapiring.");
      } else {
        await submit(r.text, true);
      }
    } catch (e) {
      setNotice((e as { detail?: string })?.detail || "Ovoz xizmati javob bermadi.");
    } finally {
      setTranscribing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-sand flex flex-col max-w-md mx-auto">
      <div className="flex items-center justify-between px-4 py-3 border-b border-cardline bg-card">
        <div className="min-w-0">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
            🎙 KUNLIK SAVOL{info ? ` · ${info.level}` : ""}
          </div>
          <div className="font-extrabold">Bugun bir savol — bir javob</div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="h-9 inline-flex items-center rounded-full bg-gold-soft px-3 text-[12px] font-extrabold">
            🔥 {streak} kun
          </span>
          <button onClick={onClose} className="w-9 h-9 rounded-full bg-cardline text-ink-soft font-extrabold">
            ✕
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {error && <div className="text-center text-ink-soft font-semibold pt-8">{error}</div>}
        {!info && !error && (
          <div className="text-center text-sm text-ink-soft font-semibold pt-8">Savol tayyorlanmoqda…</div>
        )}

        {q && (
          <div className="rounded-3xl bg-card border border-cardline p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">BUGUNGI SAVOL</div>
              <button
                onClick={() => setShowHelp((v) => !v)}
                className={`h-7 px-2.5 rounded-full text-[11px] font-extrabold border ${
                  showHelp ? "bg-emerald-deep text-white border-emerald-deep" : "bg-card text-ink-soft border-cardline"
                }`}
              >
                Aa
              </button>
            </div>
            <div className="font-arabic text-3xl leading-[1.9] mt-2" dir="rtl">
              {q.ar}
            </div>
            {showHelp && (
              <>
                <div className="text-sm text-ink-soft font-semibold italic mt-1">{q.translit}</div>
                <div className="text-sm font-semibold mt-1">{q.uz}</div>
              </>
            )}
            {showHelp && q.hint_uz && !result && (
              <div className="mt-2 rounded-xl bg-emerald-deep/10 px-3 py-2 text-xs font-semibold text-emerald-dark">
                💡 {q.hint_uz}
              </div>
            )}
            <button
              onClick={speakQ}
              className="mt-3 h-10 px-4 rounded-xl bg-gold-soft text-sm font-extrabold active:scale-95 transition-transform"
            >
              🔊 Eshitish
            </button>
          </div>
        )}

        {info && !info.ai && !result && (
          <div className="rounded-2xl bg-gold-soft border border-gold/30 p-3 text-sm font-semibold">
            AI ustoz hozircha o'chiq (server sozlanmoqda). Birozdan keyin qayta kiring.
          </div>
        )}
        {notice && (
          <div className="rounded-2xl bg-gold-soft border border-gold/30 p-3 text-sm font-semibold">{notice}</div>
        )}

        {result && (
          <div className="space-y-3">
            <div className="rounded-3xl bg-gradient-to-br from-emerald-deep to-emerald-dark p-5 text-white text-center shadow-lg">
              <div className="text-3xl">{result.score >= 80 ? "🌟" : result.score >= 50 ? "👏" : "💪"}</div>
              <div className="text-[44px] leading-none font-extrabold mt-1">{result.score}</div>
              <div className="text-sm text-white/80 font-semibold">ball (100 dan)</div>
              <div className="mt-3 inline-block rounded-full bg-white/15 px-4 py-1.5 font-extrabold">
                {xp > 0 ? `+${xp} XP` : `+${result.xp} XP olingan`} · 🔥 {streak} kun
              </div>
            </div>

            <div className="rounded-2xl bg-card border border-cardline p-4 space-y-2">
              <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">SIZNING JAVOBINGIZ</div>
              <div className="font-arabic text-xl leading-relaxed" dir="auto">
                {result.answer}
              </div>
              {result.fixed_ar && (
                <div className="rounded-xl bg-gold-soft border border-gold/30 px-3 py-2">
                  <div className="text-[10px] font-extrabold text-ink-soft">✏️ TUZATILGAN</div>
                  <div className="font-arabic text-xl leading-relaxed" dir="rtl">
                    {result.fixed_ar}
                  </div>
                </div>
              )}
              {result.feedback_uz && <div className="text-sm font-semibold">{result.feedback_uz}</div>}
            </div>

            {result.ideal_ar && (
              <div className="rounded-2xl bg-card border border-emerald-deep/30 p-4">
                <div className="text-[11px] font-extrabold tracking-[0.12em] text-emerald-dark">NAMUNAVIY JAVOB</div>
                <div className="font-arabic text-2xl leading-relaxed mt-1" dir="rtl">
                  {result.ideal_ar}
                </div>
                <button
                  onClick={() =>
                    api
                      .tutorSay(result.ideal_ar)
                      .then((r) => playUrl(r.audio_url).then((ok) => !ok && speakText(result.ideal_ar)))
                      .catch(() => speakText(result.ideal_ar))
                  }
                  className="mt-2 h-9 px-3 rounded-lg bg-gold-soft text-sm font-extrabold active:scale-95 transition-transform"
                >
                  🔊 Eshitish
                </button>
              </div>
            )}

            {info && (
              <RateBar
                sessionKey={`daily-${info.day}`}
                mode="daily"
                topic={info.question.id}
                question="Baho va izoh foydali bo'ldimi?"
              />
            )}

            <p className="text-center text-xs text-ink-soft font-semibold">
              Ertaga yangi savol. Har kuni javob bering — streak o'ssin! 🔥
            </p>
            <button
              onClick={onClose}
              className="w-full rounded-2xl bg-emerald-deep py-3 text-sm font-extrabold text-white active:scale-95 transition-transform"
            >
              Yopish
            </button>
          </div>
        )}
      </div>

      {info && !result && info.ai && (
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
                  disabled={sending || transcribing}
                  className="w-11 h-11 shrink-0 rounded-xl bg-gold-soft text-xl active:scale-90 transition-transform disabled:opacity-40"
                  aria-label="Gapirish"
                >
                  🎤
                </button>
              )}
              <input
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit(text, false)}
                dir="auto"
                placeholder={transcribing ? "🎧 Eshitilmoqda…" : "جوابك هنا… yoki lotincha"}
                disabled={sending || transcribing}
                className="flex-1 min-w-0 rounded-xl bg-sand border border-cardline px-3 py-2.5 font-arabic text-lg outline-none focus:border-emerald-deep/40 disabled:opacity-60"
              />
              <button
                onClick={() => submit(text, false)}
                disabled={!text.trim() || sending || transcribing}
                className="w-11 h-11 shrink-0 rounded-xl bg-emerald-deep text-white text-xl font-extrabold active:scale-90 transition-transform disabled:opacity-40"
              >
                {sending ? "…" : "↑"}
              </button>
            </div>
          )}
          <div className="text-[11px] font-bold text-ink-soft px-0.5">
            {canVoice ? "🎤 ovozli javob +2 XP · " : ""}Bepul · kuniga bitta savol
          </div>
        </div>
      )}
    </div>
  );
}
