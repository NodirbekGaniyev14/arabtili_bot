/** Dars testi yurgizuvchisi (K33.2): har javob SERVERda qulflanadi, to'g'ri javob shundan keyin ochiladi.
 *
 *  QuizRunner o'rnida (dars mikro-testi, o'qish matni, nazorat testi, zaif so'zlar): o'quvchi tanlaydi/yozadi →
 *  «Tekshirish» → server baholaydi va javobni qulflaydi → to'g'ri javob + izoh bilan feedback paneli.
 *  Ball mijoz raqamidan emas — serverdagi qulflangan javoblardan hisoblanadi; tugagach `onFinish()` (parametrsiz). */

import { useEffect, useState } from "react";
import { api, type QuizQuestion, type RunAnswerResult } from "../../lib/api";
import { playAudio } from "../../lib/audio";
import ReportIssue, { rememberWrong } from "../../components/ReportIssue";
import { Harakat, Options, Order, SELF_DONE, Self, Typed, heading, kindOf } from "../quizInputs";
import { Feedback, FeedbackReport } from "./exercises";
import { localVerdict } from "./verdict";

const tg = () => window.Telegram?.WebApp;

export default function RunQuiz({
  runId,
  items,
  offset = 0,
  label,
  context,
  onProgress,
  onFinish,
}: {
  runId: number;
  items: QuizQuestion[];
  /** Urinishdagi savollar tartibida bu ro'yxat qaysi indeksdan boshlanadi (o'qish matni savollari) */
  offset?: number;
  label: string;
  /** «Xatolik bormi?» xabari uchun manba (dars id…) */
  context?: string;
  /** Test ichidagi ilgarilash (0..1) — yuqoridagi umumiy chiziq uchun */
  onProgress?: (frac: number) => void;
  onFinish: () => void;
}) {
  const [idx, setIdx] = useState(0);
  const [given, setGiven] = useState<string | null>(null);
  const [reveal, setReveal] = useState<RunAnswerResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [netErr, setNetErr] = useState(false);
  const q = items[idx];

  useEffect(() => {
    onProgress?.(items.length ? idx / items.length : 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx, items.length]);

  useEffect(() => {
    if (q?.audio && (q.type === "dictation" || q.type === "shadowing")) playAudio(q.audio);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx]);

  if (!q) return null;
  const kind = kindOf(q);
  const { prompt, big } = heading(q);

  const submit = async (value: string) => {
    if (busy || reveal) return;
    setBusy(true);
    setNetErr(false);
    try {
      const r = await api.runAnswer(runId, offset + idx, value);
      setReveal(r);
      if (kind === "self") {
        advance(); // «Aytdim» — feedback paneli yo'q (avvalgidek)
      } else {
        tg()?.HapticFeedback?.notificationOccurred(r.ok ? "success" : "error");
        if (!r.ok) rememberWrong({ ...issueCtx(r), given: r.given });
      }
    } catch {
      setNetErr(true); // javob qulflanmadi — qayta urinish xavfsiz (server avvalgisini qaytaradi)
    } finally {
      setBusy(false);
    }
  };

  const advance = () => {
    setGiven(null);
    setReveal(null);
    if (idx + 1 < items.length) setIdx(idx + 1);
    else onFinish();
  };

  const issueCtx = (r: RunAnswerResult) => ({
    context: (context || label).slice(0, 64),
    label: `${label} · ${idx + 1}/${items.length}`,
    ex_type: q.type,
    q: q.q_uz || q.q_ar,
    q_ar: q.q_ar,
    options: q.options,
    answer: r.answer,
    given: r.given,
    audio: q.audio,
  });

  // Feedback matni: server hukmi (✓/✗); imlo izohi va «Namuna» belgisi — mahalliy qoidalardan (faqat ko'rsatish)
  const verdict = reveal
    ? localVerdict({ type: q.type, q_uz: q.q_uz, q_ar: q.q_ar, answer: reveal.answer, accept: reveal.accept }, kind, reveal.given)
    : null;
  const note = reveal
    ? !reveal.ok && reveal.note
      ? `Siz tanlagan «${reveal.given}» = ${reveal.note}`
      : verdict?.note
    : undefined;

  const locked = reveal !== null;
  return (
    <div>
      <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-1">
        {label} · {idx + 1}/{items.length}
      </div>
      <div className="font-bold text-lg">{prompt}</div>
      {big && (
        <div className="my-5 text-center font-arabic text-5xl leading-snug" dir="rtl">
          {big}
        </div>
      )}
      {q.audio && kind !== "self" && (
        <button
          onClick={() => playAudio(q.audio)}
          className="mx-auto my-4 w-14 h-14 rounded-full bg-emerald-deep text-white text-xl flex items-center justify-center active:scale-90 transition-transform"
        >
          🔊
        </button>
      )}

      {/* key — har savolda holat yangidan boshlanadi */}
      {kind === "options" && (
        <Options key={idx} q={q} onGiven={setGiven} reveal={reveal ? { answer: reveal.answer, given: reveal.given } : undefined} />
      )}
      {(kind === "ar" || kind === "lat") && <Typed key={idx} arabic={kind === "ar"} onGiven={setGiven} disabled={locked} />}
      {kind === "harakat" && <Harakat key={idx} base={q.base ?? ""} onGiven={setGiven} disabled={locked} />}
      {kind === "order" && <Order key={idx} words={q.words ?? []} onGiven={setGiven} disabled={locked} />}
      {kind === "self" && <Self key={idx} audio={q.audio} onConfirm={() => submit(SELF_DONE)} disabled={busy} />}

      {kind !== "self" && !locked && (
        <button
          onClick={() => given !== null && submit(given)}
          disabled={given === null || busy}
          className="mt-3 w-full rounded-2xl bg-emerald-deep py-3.5 text-white font-extrabold disabled:opacity-40 active:scale-[0.98] transition-transform"
        >
          {busy ? "Tekshirilmoqda…" : "Tekshirish"}
        </button>
      )}
      {netErr && (
        <p className="mt-2 text-center text-xs font-bold text-terracotta">
          Internet bilan muammo — qayta urinib ko'ring.
        </p>
      )}

      {reveal && kind !== "self" && (
        <FeedbackReport.Provider value={<ReportIssue key={`fb-${idx}`} className="mt-1" tone="dark" ctx={issueCtx(reveal)} />}>
          <Feedback
            correct={reveal.ok}
            correctAnswer={reveal.answer}
            explain={reveal.explain_uz}
            note={note}
            showSample={reveal.ok && verdict?.exact === false}
            onNext={advance}
          />
        </FeedbackReport.Provider>
      )}
      {/* K26: har savol ostida — adminga savol surati bilan xabar (javob ochilgach to'g'ri javob ham biriktiriladi) */}
      {reveal && kind !== "self" && <ReportIssue key={`issue-${idx}`} className="mt-3" ctx={issueCtx(reveal)} />}
    </div>
  );
}
