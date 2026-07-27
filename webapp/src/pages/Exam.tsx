/** Daraja imtihoni (spec §12): 4 bo'lim, timer, umumiy 80%+ qoidasi, sertifikat. */

import { useEffect, useRef, useState } from "react";
import {
  api,
  type ExamData,
  type ExamInfo,
  type ExamResult,
} from "../lib/api";
import { playAudio } from "../lib/audio";
import { QuizRunner } from "./v2/exercises";

const tg = () => window.Telegram?.WebApp;

type Stage =
  | { k: "info" }
  | { k: "name" }
  | { k: "reading" }
  | { k: "listening" }
  | { k: "writing"; i: number }
  | { k: "speaking"; i: number }
  | { k: "passage"; i: number }
  | { k: "result" };

const SECTION_TITLES: Record<string, string> = {
  reading: "📖 O'QISH",
  listening: "🎧 TINGLASH",
};

export default function Exam({ onClose }: { onClose: () => void }) {
  const [info, setInfo] = useState<ExamInfo | null>(null);
  const [active, setActive] = useState<string>("");
  const [exam, setExam] = useState<ExamData | null>(null);
  const [stage, setStage] = useState<Stage>({ k: "info" });
  const [holderName, setHolderName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExamResult | null>(null);
  const [deadline, setDeadline] = useState<number | null>(null);
  const [leftSec, setLeftSec] = useState(0);

  const scores = useRef({
    reading: 0,
    listening: 0,
    writing: 0,
    speakingDone: 0,
    passage: 0,
  });
  const writingTexts = useRef<string[]>([]);
  const submitted = useRef(false);

  useEffect(() => {
    api
      .getExamInfo()
      .then((d) => {
        setInfo(d);
        setActive(d.user_level || d.level); // ochilganda joriy daraja tanlangan
      })
      .catch(() => setError("Ma'lumot yuklanmadi"));
  }, []);

  // Tanlangan daraja holati (eski javob kelsa — joriy darajaga qaytamiz)
  const sel = info?.levels?.find((l) => l.level === active) ?? info;

  // Timer
  useEffect(() => {
    if (!deadline) return;
    const t = setInterval(() => {
      const left = Math.max(0, Math.round((deadline - Date.now()) / 1000));
      setLeftSec(left);
      if (left === 0) {
        clearInterval(t);
        finish(); // vaqt tugadi — bor natija bilan topshiriladi
      }
    }, 1000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deadline]);

  const start = async () => {
    try {
      const e = await api.startExam(sel?.level || "");
      setExam(e);
      setDeadline(Date.now() + e.minutes * 60_000);
      setStage({ k: "reading" });
    } catch (err) {
      const msg = String(err);
      setError(
        msg.includes("429")
          ? "24 soat kutish kerak — yaqinda urinib ko'rgansiz. Ertaga qayta keling!"
          : "Imtihonni boshlab bo'lmadi"
      );
    }
  };

  const finish = async () => {
    if (!exam || submitted.current) return;
    submitted.current = true;
    const sp = exam.speaking.length
      ? Math.round((100 * scores.current.speakingDone) / exam.speaking.length)
      : 100;
    const wr = exam.writing.length
      ? Math.round(
          (100 *
            writingTexts.current.filter((t) => (t || "").trim().length >= 3)
              .length) /
            exam.writing.length
        )
      : 100;
    try {
      const r = await api.submitExam({
        attempt_id: exam.attempt_id,
        reading_correct: scores.current.reading,
        listening_correct: scores.current.listening,
        writing_score: wr,
        speaking_score: sp,
        passage_correct: scores.current.passage,
        holder_name: holderName,
      });
      setResult(r);
      setStage({ k: "result" });
      tg()?.HapticFeedback?.notificationOccurred(r.passed ? "success" : "error");
    } catch {
      setError("Topshirishda xatolik");
    }
  };

  /** Yozishdan keyingi 4-bo'lim: A2+ da matn o'qish, pastda gapirish */
  const afterWriting = (e: ExamData) => {
    if (e.passages?.length) setStage({ k: "passage", i: 0 });
    else if (e.speaking.length) setStage({ k: "speaking", i: 0 });
    else finish();
  };

  const mm = Math.floor(leftSec / 60);
  const ss = String(leftSec % 60).padStart(2, "0");

  return (
    <div className="fixed inset-0 z-30 bg-sand overflow-y-auto">
      <div className="max-w-md mx-auto px-5 pt-5 pb-28">
        {/* Yuqori panel */}
        <div className="flex items-center gap-3">
          <button
            onClick={onClose}
            className="text-2xl text-ink-soft font-bold leading-none active:opacity-60"
          >
            ✕
          </button>
          <div className="flex-1 font-extrabold">
            Imtihon {info ? `· ${info.level}` : ""}
          </div>
          {deadline && stage.k !== "result" && (
            <div
              className={`rounded-full px-3 py-1 text-sm font-extrabold ${
                leftSec < 120 ? "bg-terracotta text-white" : "bg-gold-soft"
              }`}
            >
              ⏱ {mm}:{ss}
            </div>
          )}
        </div>

        {error && (
          <div className="mt-6 rounded-2xl bg-terracotta/10 border border-terracotta/40 p-4 text-sm font-bold text-center">
            {error}
          </div>
        )}

        {/* INFO — daraja tablari + tanlangan daraja holati */}
        {stage.k === "info" && info && sel && !error && (
          <div className="pt-4">
            {/* Daraja tanlagichi — Darslar sahifasidagi kabi */}
            {info.levels?.length > 0 && (
              <div className="grid grid-cols-4 gap-2">
                {info.levels.map((lvl) => {
                  const isActive = lvl.level === sel.level;
                  return (
                    <button
                      key={lvl.level}
                      onClick={() => setActive(lvl.level)}
                      className={`relative rounded-2xl py-2.5 px-1 text-center transition-transform active:scale-95 border ${
                        isActive
                          ? "bg-emerald-deep text-white border-emerald-deep shadow-md"
                          : "bg-card text-ink border-cardline"
                      }`}
                    >
                      <div className="text-base font-extrabold leading-none">
                        {lvl.level}
                      </div>
                      <div
                        className={`text-[10px] font-bold mt-1 ${
                          isActive ? "text-gold-soft" : "text-ink-soft"
                        }`}
                      >
                        {lvl.already_passed
                          ? "✅"
                          : lvl.unlocked
                            ? "ochiq"
                            : "🔒"}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}

            <div className="pt-5 text-center">
              <div className="text-5xl">📋</div>
              <h1 className="mt-2 text-2xl font-extrabold">
                {sel.level} kursi yakuniy imtihoni
              </h1>
              {sel.level !== info.user_level && (
                <p className="mt-1 text-xs text-ink-soft font-semibold">
                  Sizning darajangiz: {info.user_level}
                </p>
              )}
              {sel.already_passed && (
                <p className="mt-2 text-sm font-bold text-emerald-deep">
                  ✅ Siz bu imtihondan o'tgansiz — qayta topshirish ixtiyoriy
                </p>
              )}

              {!sel.available ? (
                <p className="mt-4 text-ink-soft font-semibold">
                  Bu daraja uchun imtihon tez orada qo'shiladi.
                </p>
              ) : !sel.unlocked ? (
                <div className="mt-5 rounded-2xl bg-card border border-cardline p-5">
                  <div className="text-4xl">🔒</div>
                  {sel.locked_reason === "above" ? (
                    <>
                      <p className="mt-2 font-extrabold">
                        {sel.level} imtihoni hali ochilmagan
                      </p>
                      <p className="mt-1 text-sm text-ink-soft font-semibold">
                        Avval <b>{info.user_level}</b> darajasini tugatib,
                        uning imtihonidan o'ting.
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="mt-2 font-extrabold">Imtihon hali ochilmagan</p>
                      <p className="mt-1 text-sm text-ink-soft font-semibold">
                        {sel.level} darajasining kamida{" "}
                        <b>{sel.lessons_needed} ta darsini</b> tugatish kerak.
                      </p>
                      <div className="mt-4 h-3 rounded-full bg-cardline overflow-hidden">
                        <div
                          className="h-full rounded-full bg-emerald-deep transition-all duration-500"
                          style={{
                            width: `${Math.min(100, Math.round((sel.lessons_done / Math.max(1, sel.lessons_needed)) * 100))}%`,
                          }}
                        />
                      </div>
                      <p className="mt-2 text-sm font-bold">
                        {sel.lessons_done} / {sel.lessons_total} dars tugatildi
                      </p>
                      <p className="mt-1 text-xs text-ink-soft font-semibold">
                        Imtihonga{" "}
                        {Math.max(0, sel.lessons_needed - sel.lessons_done)} ta dars
                        qoldi
                      </p>
                    </>
                  )}
                </div>
              ) : (
                <>
                  <div className="mt-5 rounded-2xl bg-card border border-cardline p-4 text-left text-sm font-semibold space-y-1.5">
                    <p>⏱ Vaqt: <b>{sel.minutes} daqiqa</b></p>
                    <p>📖 O'qish: {sel.counts.reading} savol · 25%</p>
                    <p>🎧 Tinglash: {sel.counts.listening} savol · 25%</p>
                    <p>✍️ Yozish: {sel.counts.writing} topshiriq · 25%</p>
                    {sel.counts.passages ? (
                      <p>
                        📚 Matn o'qish: {sel.counts.passages} ta matn · 25%
                      </p>
                    ) : (
                      <p>🗣 Gapirish: {sel.counts.speaking} topshiriq · 25%</p>
                    )}
                    <p className="pt-1 text-ink-soft">
                      O'tish uchun umumiy <b>80%+</b> yetarli.
                      Yiqilsangiz — 24 soatdan keyin yangi savollar bilan.
                    </p>
                  </div>
                  {sel.cooldown_until ? (
                    <p className="mt-4 text-sm font-bold text-terracotta">
                      ⏳ Qayta topshirish uchun 24 soat kutish kerak
                    </p>
                  ) : (
                    <button
                      onClick={() => setStage({ k: "name" })}
                      className="mt-6 w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg active:scale-[0.98] transition-transform"
                    >
                      Imtihonni boshlash
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        )}

        {/* ISM (sertifikat uchun) */}
        {stage.k === "name" && (
          <div className="pt-8">
            <h2 className="text-xl font-extrabold">Sertifikatga yoziladigan ism</h2>
            <p className="mt-1 text-sm text-ink-soft font-semibold">
              To'liq ism-familiyangizni kiriting (sertifikatda shu ko'rinadi)
            </p>
            <input
              value={holderName}
              onChange={(e) => setHolderName(e.target.value)}
              maxLength={60}
              placeholder="Ism Familiya"
              className="mt-4 w-full rounded-2xl border-2 border-emerald-deep/50 bg-card px-4 py-4 text-lg font-bold outline-none focus:border-emerald-deep"
            />
            <button
              onClick={start}
              disabled={!holderName.trim()}
              className="mt-4 w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg disabled:opacity-40 active:scale-[0.98] transition-transform"
            >
              Boshladik! ⏱
            </button>
          </div>
        )}

        {/* O'QISH / TINGLASH — QuizRunner */}
        {(stage.k === "reading" || stage.k === "listening") && exam && (
          <div className="pt-4">
            <QuizRunner
              key={stage.k}
              items={stage.k === "reading" ? exam.reading : exam.listening}
              label={SECTION_TITLES[stage.k]}
              onFinish={(correct) => {
                if (stage.k === "reading") {
                  scores.current.reading = correct;
                  setStage({ k: "listening" });
                } else {
                  scores.current.listening = correct;
                  if (exam.writing.length) setStage({ k: "writing", i: 0 });
                  else afterWriting(exam);
                }
              }}
            />
          </div>
        )}

        {/* YOZISH */}
        {stage.k === "writing" && exam && (
          <div className="pt-4">
            <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-1">
              ✍️ YOZISH · {stage.i + 1}/{exam.writing.length}
            </div>
            <p className="font-bold">{exam.writing[stage.i].task_uz}</p>
            <textarea
              key={stage.i}
              defaultValue={writingTexts.current[stage.i] || ""}
              onChange={(e) => (writingTexts.current[stage.i] = e.target.value)}
              dir="auto"
              rows={4}
              className="mt-3 w-full rounded-2xl border-2 border-emerald-deep/50 bg-card px-4 py-3 text-xl font-bold outline-none font-arabic"
              placeholder="Shu yerga yozing..."
            />
            <button
              onClick={() => {
                if (stage.i + 1 < exam.writing.length)
                  setStage({ k: "writing", i: stage.i + 1 });
                else afterWriting(exam);
              }}
              className="mt-4 w-full rounded-2xl bg-emerald-deep py-3.5 text-white font-extrabold active:scale-[0.98] transition-transform"
            >
              Keyingi
            </button>
          </div>
        )}

        {/* MATN O'QISH (A2+) — matn tepada, savollar tagida */}
        {stage.k === "passage" && exam && exam.passages[stage.i] && (
          <div className="pt-4">
            <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-1">
              📚 MATN · {stage.i + 1}/{exam.passages.length}
            </div>
            <div className="rounded-2xl bg-card border border-cardline p-4">
              <div className="text-sm font-extrabold text-emerald-deep">
                {exam.passages[stage.i].title_uz}
              </div>
              <p
                dir="rtl"
                className="mt-2 font-arabic text-[22px] leading-[2.1] text-right"
              >
                {exam.passages[stage.i].text_ar}
              </p>
            </div>
            <p className="mt-3 text-xs text-ink-soft font-semibold">
              Matnni o'qing va quyidagi savollarga javob bering:
            </p>
            <div className="mt-2">
              <QuizRunner
                key={`p${stage.i}`}
                items={exam.passages[stage.i].questions}
                label="SAVOL"
                onFinish={(correct) => {
                  scores.current.passage += correct;
                  if (stage.i + 1 < exam.passages.length)
                    setStage({ k: "passage", i: stage.i + 1 });
                  else finish();
                }}
              />
            </div>
          </div>
        )}

        {/* GAPIRISH */}
        {stage.k === "speaking" && exam && (
          <div className="pt-4 text-center">
            <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-1 text-left">
              🗣 GAPIRISH · {stage.i + 1}/{exam.speaking.length}
            </div>
            <p className="text-sm font-semibold text-left">
              Eshiting va ovoz chiqarib takrorlang:
            </p>
            <div className="my-6 font-arabic text-5xl leading-snug" dir="rtl">
              {exam.speaking[stage.i].q_ar}
            </div>
            <button
              onClick={() => playAudio(exam.speaking[stage.i].audio)}
              className="mx-auto w-16 h-16 rounded-full bg-emerald-deep text-white text-2xl flex items-center justify-center active:scale-90 transition-transform"
            >
              🔊
            </button>
            <div className="mt-6 grid grid-cols-2 gap-3">
              <button
                onClick={() => playAudio(exam.speaking[stage.i].audio)}
                className="rounded-2xl bg-card border border-cardline py-3.5 font-extrabold"
              >
                🔁 Yana
              </button>
              <button
                onClick={() => {
                  scores.current.speakingDone += 1;
                  if (stage.i + 1 < exam.speaking.length)
                    setStage({ k: "speaking", i: stage.i + 1 });
                  else finish();
                }}
                className="rounded-2xl bg-emerald-deep text-white py-3.5 font-extrabold"
              >
                ✓ Aytdim
              </button>
            </div>
          </div>
        )}

        {/* NATIJA */}
        {stage.k === "result" && result && (
          <div className="pt-6 text-center">
            <div className="text-6xl">{result.passed ? "🏅" : "📚"}</div>
            <h1 className="mt-2 text-2xl font-extrabold">
              {result.passed
                ? "Tabriklaymiz — o'tdingiz!"
                : result.timed_out
                  ? "Vaqt tugadi"
                  : "Bu safar bo'lmadi"}
            </h1>
            <div className="mt-2 text-4xl font-extrabold text-emerald-deep">
              {result.total}/100
            </div>
            {result.promoted_to && (
              <div className="mt-4 rounded-2xl bg-gold-soft border border-gold/40 px-5 py-4">
                <div className="text-3xl">🎉</div>
                <p className="mt-1 font-extrabold text-emerald-dark">
                  {result.promoted_to} darajasi ochildi!
                </p>
                <p className="mt-1 text-xs font-semibold text-ink-soft">
                  Endi darslar va imtihon {result.promoted_to} darajasidan davom etadi
                </p>
              </div>
            )}
            <div className="mt-4 space-y-2 text-left">
              {(
                [
                  ["📖 O'qish", result.reading],
                  ["🎧 Tinglash", result.listening],
                  ["✍️ Yozish", result.writing],
                  [
                    result.fourth === "passage" ? "📚 Matn" : "🗣 Gapirish",
                    result.speaking,
                  ],
                ] as const
              ).map(([label, val]) => (
                <div key={label} className="rounded-xl bg-card border border-cardline p-2.5">
                  <div className="flex justify-between text-xs font-extrabold mb-1">
                    <span>{label}</span>
                    <span className={val < 60 ? "text-terracotta" : "text-emerald-deep"}>
                      {val}%
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-cardline overflow-hidden">
                    <div
                      className={`h-full rounded-full ${val < 60 ? "bg-terracotta" : "bg-emerald-deep"}`}
                      style={{ width: `${val}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>

            {result.passed && result.certificate && (
              <div className="mt-5">
                <img
                  src={result.certificate.png_url}
                  alt="Sertifikat"
                  className="rounded-2xl border-2 border-gold shadow-lg"
                />
                <p className="mt-2 text-xs text-ink-soft font-semibold">
                  🏅 Sertifikat botga ham yuborildi — u yerdan ulashing!
                </p>
              </div>
            )}
            {!result.passed && (
              <p className="mt-4 text-sm text-ink-soft font-semibold px-4">
                24 soatdan keyin yangi savollar bilan qayta topshirishingiz
                mumkin. Darslar va takror bilan tayyorlaning! 💪
              </p>
            )}
            <button
              onClick={onClose}
              className="mt-6 w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg"
            >
              Yakunlash
            </button>
          </div>
        )}

        {stage.k === "info" && !info && !error && (
          <div className="min-h-[50vh] flex items-center justify-center">
            <div className="w-10 h-10 rounded-xl bg-emerald-deep animate-pulse" />
          </div>
        )}
      </div>
    </div>
  );
}
