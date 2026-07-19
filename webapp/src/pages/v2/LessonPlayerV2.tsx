/** Dars playeri v2 — spec §2.1 anatomiyasi:
 * hook → grammatika → o'zaklar → lug'at → 🇸🇦 hejazi → 4 ko'nikma → mikro-test → natija
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type CheckpointData,
  type CompleteV2Response,
  type LessonV2Data,
  type Stats,
} from "../../lib/api";
import { playAudio } from "../../lib/audio";
import ArabicText, { buildLookup } from "./ArabicText";
import { QuizRunner } from "./exercises";

const tg = () => window.Telegram?.WebApp;

type Phase =
  | { k: "hook" }
  | { k: "grammar" }
  | { k: "roots" }
  | { k: "vocab"; i: number }
  | { k: "hejazi" }
  | { k: "skill"; i: number } // 0 reading · 1 listening · 2 speaking · 3 writing
  | { k: "test" }
  | { k: "result" }
  | { k: "cp" }
  | { k: "cpresult" };

interface Props {
  lessonId: string;
  onClose: () => void;
  onFinish: (stats: Stats) => void;
}

export default function LessonPlayerV2({ lessonId, onClose, onFinish }: Props) {
  const [lesson, setLesson] = useState<LessonV2Data | null>(null);
  const [phase, setPhase] = useState<Phase>({ k: "hook" });
  const [error, setError] = useState(false);
  const [testResult, setTestResult] = useState<{
    correct: number;
    total: number;
    wrong: string[];
  } | null>(null);
  const [reward, setReward] = useState<CompleteV2Response | null>(null);
  const [cp, setCp] = useState<CheckpointData | null>(null);
  const [cpResult, setCpResult] = useState<{
    score: number;
    passed: boolean;
    xp_earned: number;
  } | null>(null);
  const submitted = useRef(false);
  const [rated, setRated] = useState<1 | -1 | 0>(0);

  useEffect(() => {
    api.getLessonV2(lessonId).then(setLesson).catch(() => setError(true));
  }, [lessonId]);

  const lookup = useMemo(
    () => (lesson ? buildLookup(lesson) : new Map()),
    [lesson]
  );

  // Fazalar ro'yxati (dars tarkibiga qarab)
  const phases = useMemo<Phase[]>(() => {
    if (!lesson) return [];
    const list: Phase[] = [{ k: "hook" }];
    if (lesson.grammar?.point_ar) list.push({ k: "grammar" });
    if (lesson.roots.length) list.push({ k: "roots" });
    lesson.vocabulary.forEach((_, i) => list.push({ k: "vocab", i }));
    if (lesson.hejazi.length) list.push({ k: "hejazi" });
    const s = lesson.skills;
    if (s?.reading?.text_ar) list.push({ k: "skill", i: 0 });
    if (s?.listening?.audio) list.push({ k: "skill", i: 1 });
    if (s?.speaking?.task_uz) list.push({ k: "skill", i: 2 });
    if (s?.writing?.task_uz) list.push({ k: "skill", i: 3 });
    if (lesson.micro_test.length) list.push({ k: "test" });
    return list;
  }, [lesson]);

  const phaseIdx = phases.findIndex((p) => JSON.stringify(p) === JSON.stringify(phase));
  const progress =
    phase.k === "result" || phase.k === "cp" || phase.k === "cpresult"
      ? 1
      : Math.max(0, phaseIdx) / Math.max(1, phases.length);

  const next = () => {
    const i = phases.findIndex((p) => JSON.stringify(p) === JSON.stringify(phase));
    if (i >= 0 && i + 1 < phases.length) setPhase(phases[i + 1]);
    else setPhase({ k: "result" });
  };

  // Vocab kartada audio avtomatik
  useEffect(() => {
    if (lesson && phase.k === "vocab") {
      playAudio(lesson.vocabulary[phase.i]?.audio);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase]);

  // Natija: serverga yuborish
  useEffect(() => {
    if (phase.k !== "result" || !lesson || !testResult || submitted.current) return;
    submitted.current = true;
    api
      .completeLessonV2(lesson.id, testResult.correct, testResult.total, testResult.wrong)
      .then(setReward)
      .catch(() => setError(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase]);

  if (error) {
    return (
      <Shell onClose={onClose} progress={0}>
        <div className="min-h-[60vh] flex flex-col items-center justify-center gap-4 text-center">
          <div className="text-4xl">😔</div>
          <p className="font-bold">Xatolik yuz berdi. Qayta urinib ko'ring.</p>
          <button onClick={onClose} className="rounded-2xl bg-emerald-deep px-8 py-3 text-white font-extrabold">
            Yopish
          </button>
        </div>
      </Shell>
    );
  }

  if (!lesson) {
    return (
      <Shell onClose={onClose} progress={0}>
        <div className="min-h-[60vh] flex items-center justify-center">
          <div className="w-10 h-10 rounded-xl bg-emerald-deep animate-pulse" />
        </div>
      </Shell>
    );
  }

  return (
    <Shell onClose={onClose} progress={progress} hideBar={phase.k === "result" || phase.k === "cpresult"}>
      {/* ── HOOK ── */}
      {phase.k === "hook" && (
        <div className="pt-6">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
            {lesson.meta.level} · {lesson.meta.order}-DARS
          </div>
          <h1 className="mt-1 text-2xl font-extrabold leading-snug">{lesson.title_uz}</h1>
          {lesson.title_ar && (
            <div className="mt-2 font-arabic text-4xl text-emerald-deep" dir="rtl">
              {lesson.title_ar}
            </div>
          )}
          <div className="mt-4 rounded-2xl bg-gold-soft/60 border border-gold/30 p-4 text-sm font-semibold leading-relaxed">
            💡 {lesson.hook_uz}
          </div>
          <div className="mt-3 rounded-2xl bg-card border border-cardline p-4">
            <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-1">
              BU DARSDAN KEYIN
            </div>
            <p className="text-sm font-bold">✅ {lesson.can_do_uz}</p>
          </div>
          <button onClick={next} className="mt-6 w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg active:scale-[0.98] transition-transform">
            Boshlash
          </button>
        </div>
      )}

      {/* ── GRAMMATIKA ── */}
      {phase.k === "grammar" && (
        <div className="pt-4">
          <SectionLabel text="GRAMMATIKA" />
          <div className="font-arabic text-3xl text-emerald-deep" dir="rtl">
            {lesson.grammar.point_ar}
          </div>
          <p className="mt-3 text-sm font-semibold leading-relaxed">
            {lesson.grammar.explanation_uz}
          </p>
          {lesson.grammar.table.length > 0 && (
            <div className="mt-4 rounded-2xl bg-card border border-cardline overflow-hidden">
              {lesson.grammar.table.map((row, i) => (
                <div key={i} className={`flex items-center gap-3 px-4 py-2.5 ${i ? "border-t border-cardline" : ""}`}>
                  <span className="font-arabic text-2xl min-w-24 text-emerald-deep" dir="rtl">
                    {row.ar}
                  </span>
                  <span className="flex-1 text-sm font-bold">{row.uz}</span>
                  {row.form && (
                    <span className="font-arabic text-sm text-ink-soft">{row.form}</span>
                  )}
                </div>
              ))}
            </div>
          )}
          {lesson.grammar.common_mistakes_uz.length > 0 && (
            <div className="mt-4 rounded-2xl bg-terracotta/8 border border-terracotta/30 p-4">
              <div className="text-[11px] font-extrabold tracking-[0.14em] text-terracotta mb-1.5">
                ⚠️ KENG TARQALGAN XATOLAR
              </div>
              {lesson.grammar.common_mistakes_uz.map((m, i) => (
                <p key={i} className="text-[13px] font-semibold leading-relaxed">• {m}</p>
              ))}
            </div>
          )}
          <NextBtn onClick={next} />
        </div>
      )}

      {/* ── O'ZAKLAR ── */}
      {phase.k === "roots" && (
        <div className="pt-4">
          <SectionLabel text="O'ZAK KO'PRIGI 🔬" />
          {lesson.roots.map((r) => (
            <div key={r.root} className="mb-4 rounded-2xl bg-gradient-to-br from-emerald-deep to-emerald-dark p-4 text-white">
              <div className="flex items-center justify-between">
                <span className="font-arabic text-3xl tracking-[0.15em]">{r.root}</span>
                <span className="font-bold text-gold-soft">{r.meaning_uz}</span>
              </div>
              {r.uz_cognates.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {r.uz_cognates.map((c) => (
                    <span key={c} className="rounded-full bg-white/15 px-2.5 py-0.5 text-[11px] font-bold">
                      {c}
                    </span>
                  ))}
                </div>
              )}
              <div className="mt-3 space-y-1.5">
                {r.derived.map((d) => (
                  <div key={d.ar} className="flex items-center gap-2 rounded-xl bg-white/10 px-3 py-1.5">
                    <span className="font-arabic text-xl min-w-20" dir="rtl">{d.ar}</span>
                    <span className="flex-1 text-xs font-semibold">{d.uz}</span>
                    <span className="font-arabic text-xs opacity-70">{d.pattern}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
          <NextBtn onClick={next} />
        </div>
      )}

      {/* ── LUG'AT ── */}
      {phase.k === "vocab" && (() => {
        const v = lesson.vocabulary[phase.i];
        return (
          <div className="pt-4 text-center">
            <SectionLabel
              text={`${v.pos === "harf" ? "YANGI HARF" : "YANGI SO'Z"} · ${phase.i + 1}/${lesson.vocabulary.length}`}
              center
            />
            <div className="mt-4 rounded-3xl bg-card border border-cardline p-7">
              <div className="font-arabic text-6xl leading-tight" dir="rtl">{v.ar}</div>
              <div className="mt-3 text-lg font-extrabold text-emerald-deep italic">{v.translit}</div>
              <div className="mt-1 font-semibold">{v.uz}</div>
              {(v.root || v.pattern) && (
                <div className="mt-3 flex justify-center gap-2 flex-wrap">
                  {v.root && (
                    <span className="rounded-full bg-gold-soft px-3 py-1 text-xs font-bold">
                      o'zak: <span className="font-arabic">{v.root}</span>
                    </span>
                  )}
                  {v.pattern && (
                    <span className="rounded-full bg-emerald-deep/10 px-3 py-1 text-xs font-bold text-emerald-dark">
                      vazn: <span className="font-arabic">{v.pattern}</span>
                    </span>
                  )}
                </div>
              )}
              {v.audio && (
                <button
                  onClick={() => playAudio(v.audio)}
                  className="mt-4 w-14 h-14 rounded-full bg-emerald-deep text-white text-xl mx-auto flex items-center justify-center active:scale-90 transition-transform"
                >
                  🔊
                </button>
              )}
              {v.example_ar && (
                <div className="mt-4 pt-4 border-t border-cardline text-sm">
                  <ArabicText text={v.example_ar} lookup={lookup} className="text-2xl" />
                  <div className="mt-1 text-ink-soft font-semibold">{v.example_uz}</div>
                </div>
              )}
            </div>
            <NextBtn onClick={next} />
          </div>
        );
      })()}

      {/* ── HEJAZI 🇸🇦 ── */}
      {phase.k === "hejazi" && (
        <div className="pt-4">
          <SectionLabel text="🇸🇦 SAUDIYADA SHUNDAY DEYILADI" />
          <p className="text-xs text-ink-soft font-semibold mb-3">
            Kitobda — rasmiy (فصحى), ko'chada — Hijoziy. Ikkalasini bilib qo'ying:
          </p>
          <div className="space-y-2.5">
            {lesson.hejazi.map((h, i) => (
              <button
                key={i}
                onClick={() => playAudio(h.audio)}
                className="w-full rounded-2xl bg-card border border-cardline p-3.5 text-left active:scale-[0.99] transition-transform"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-extrabold text-ink-soft">📖 RASMIY</span>
                  <span className="font-arabic text-xl" dir="rtl">{h.msa_ar}</span>
                </div>
                <div className="mt-1.5 flex items-center justify-between gap-2">
                  <span className="text-[10px] font-extrabold text-emerald-deep">🇸🇦 HIJOZIY</span>
                  <span className="font-arabic text-2xl text-emerald-deep" dir="rtl">{h.hejazi_ar}</span>
                </div>
                <div className="mt-1 text-xs font-semibold text-ink-soft text-right">
                  {h.translit} — {h.uz}
                </div>
              </button>
            ))}
          </div>
          <NextBtn onClick={next} />
        </div>
      )}

      {/* ── KO'NIKMALAR ── */}
      {phase.k === "skill" && (
        <SkillPhase
          key={phase.i}
          lesson={lesson}
          which={phase.i}
          lookup={lookup}
          onNext={next}
        />
      )}

      {/* ── MIKRO-TEST ── */}
      {phase.k === "test" && (
        <div className="pt-4">
          <QuizRunner
            items={lesson.micro_test}
            rootPool={lesson.roots.map((r) => r.root)}
            label="MIKRO-TEST"
            onFinish={(correct, total, wrong) => {
              setTestResult({ correct, total, wrong });
              setPhase({ k: "result" });
            }}
          />
        </div>
      )}

      {/* ── NATIJA ── */}
      {phase.k === "result" && (
        <div className="min-h-[75vh] flex flex-col items-center justify-center text-center gap-3">
          <div className="text-6xl">{reward?.perfect ? "🌟" : reward?.passed !== false ? "🎉" : "💪"}</div>
          <h1 className="text-2xl font-extrabold">
            {reward?.perfect ? "Mukammal!" : "Dars tugadi!"}
          </h1>
          {testResult && (
            <p className="text-ink-soft font-semibold">
              {testResult.correct}/{testResult.total} to'g'ri
              {reward && ` · ${reward.score}%`}
            </p>
          )}
          {reward ? (
            <>
              {!reward.passed && (
                <p className="text-sm text-terracotta font-bold px-8">
                  60% dan past — darsni keyinroq qayta o'tish tavsiya etiladi
                </p>
              )}
              <div className="rounded-2xl bg-gold-soft border border-gold/30 px-8 py-4">
                <span className="text-3xl font-extrabold text-emerald-dark">
                  +{reward.xp_earned} XP
                </span>
              </div>
              {reward.srs_added > 0 && (
                <p className="text-xs text-ink-soft font-semibold">
                  🔁 {reward.srs_added} ta yangi karta takror kartotekasiga qo'shildi
                </p>
              )}
              {reward.new_badges.map((b) => (
                <div key={b.id} className="flex items-center gap-3 rounded-2xl bg-card border border-gold/40 p-3 w-full text-left">
                  <span className="text-3xl">{b.icon}</span>
                  <div>
                    <div className="font-extrabold text-[15px]">{b.title}</div>
                    <div className="text-xs text-ink-soft font-semibold">{b.desc}</div>
                  </div>
                </div>
              ))}
              {/* Dars bahosi — 1 bosishli 👍/👎 */}
              <div className="w-full rounded-2xl bg-card border border-cardline px-4 py-3 flex items-center justify-between">
                {rated === 0 ? (
                  <>
                    <span className="text-sm font-bold text-ink-soft">
                      Dars yoqdimi?
                    </span>
                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          setRated(1);
                          api.rateLesson(lesson.id, 1).catch(() => {});
                        }}
                        className="w-11 h-11 rounded-xl bg-emerald-deep/10 text-2xl active:scale-90 transition-transform"
                        aria-label="Yoqdi"
                      >
                        👍
                      </button>
                      <button
                        onClick={() => {
                          setRated(-1);
                          api.rateLesson(lesson.id, -1).catch(() => {});
                        }}
                        className="w-11 h-11 rounded-xl bg-terracotta/10 text-2xl active:scale-90 transition-transform"
                        aria-label="Yoqmadi"
                      >
                        👎
                      </button>
                    </div>
                  </>
                ) : (
                  <span className="text-sm font-bold text-emerald-dark mx-auto">
                    {rated === 1 ? "Rahmat! 🌟" : "Rahmat, yaxshilaymiz! 🛠"}
                  </span>
                )}
              </div>
              {reward.checkpoint_available && (
                <button
                  onClick={() => {
                    api.getCheckpoint(lesson.id).then((c) => {
                      setCp(c);
                      setPhase({ k: "cp" });
                    }).catch(() => {});
                  }}
                  className="w-full rounded-2xl bg-gold-soft border border-gold/40 py-3.5 font-extrabold active:scale-[0.98] transition-transform"
                >
                  📋 Nazorat testi (oxirgi 5 dars)
                </button>
              )}
              <button
                onClick={() => onFinish(reward.stats)}
                className="w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg active:scale-[0.98] transition-transform"
              >
                Davom etish
              </button>
            </>
          ) : (
            <div className="w-8 h-8 rounded-lg bg-emerald-deep animate-pulse" />
          )}
        </div>
      )}

      {/* ── NAZORAT TESTI ── */}
      {phase.k === "cp" && cp && (
        <div className="pt-4">
          <QuizRunner
            items={cp.questions}
            rootPool={lesson.roots.map((r) => r.root)}
            label="NAZORAT TESTI"
            onFinish={(correct, total, wrong) => {
              api
                .completeCheckpoint(lesson.id, correct, total, wrong)
                .then((r) => {
                  setCpResult(r);
                  setPhase({ k: "cpresult" });
                })
                .catch(() => setError(true));
            }}
          />
        </div>
      )}

      {phase.k === "cpresult" && cpResult && (
        <div className="min-h-[70vh] flex flex-col items-center justify-center text-center gap-3">
          <div className="text-6xl">{cpResult.passed ? "🏆" : "📚"}</div>
          <h1 className="text-2xl font-extrabold">
            {cpResult.passed ? "Nazorat testi o'tildi!" : "Yana mashq kerak"}
          </h1>
          <p className="text-ink-soft font-semibold">Natija: {cpResult.score}%</p>
          {!cpResult.passed && (
            <p className="text-sm text-ink-soft font-semibold px-8">
              Xato so'zlar takror kartotekasiga qaytarildi — SRS orqali mustahkamlang
            </p>
          )}
          <div className="rounded-2xl bg-gold-soft border border-gold/30 px-8 py-4">
            <span className="text-3xl font-extrabold text-emerald-dark">
              +{cpResult.xp_earned} XP
            </span>
          </div>
          <button
            onClick={() => reward && onFinish(reward.stats)}
            className="w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg"
          >
            Yakunlash
          </button>
        </div>
      )}
    </Shell>
  );
}

/* ── Ko'nikma fazasi ── */

function SkillPhase({
  lesson,
  which,
  lookup,
  onNext,
}: {
  lesson: LessonV2Data;
  which: number;
  lookup: Map<string, { ar: string; uz: string }>;
  onNext: () => void;
}) {
  const s = lesson.skills;
  const [revealed, setRevealed] = useState<Set<number>>(new Set());
  const [writing, setWriting] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);

  useEffect(() => {
    if (which === 1) playAudio(s.listening.audio);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [which]);

  if (which === 0) {
    return (
      <div className="pt-4">
        <SectionLabel text="📖 O'QISH" />
        <div className="rounded-2xl bg-card border border-cardline p-5 text-2xl leading-loose">
          <ArabicText text={s.reading.text_ar} lookup={lookup} />
        </div>
        <p className="mt-2 text-[11px] text-ink-soft font-semibold">
          💡 Har so'zga bosib ma'nosini ko'ring
        </p>
        {s.reading.questions.map((q, i) => (
          <div key={i} className="mt-3 rounded-2xl bg-card border border-cardline p-4">
            <p className="text-sm font-bold">{q.q_uz}</p>
            {revealed.has(i) ? (
              <p className="mt-2 text-sm font-extrabold text-emerald-deep">→ {q.a}</p>
            ) : (
              <button
                onClick={() => setRevealed((r) => new Set(r).add(i))}
                className="mt-2 text-xs font-extrabold text-emerald-deep underline underline-offset-4"
              >
                Javobni ko'rish
              </button>
            )}
          </div>
        ))}
        <NextBtn onClick={onNext} />
      </div>
    );
  }

  if (which === 1) {
    return (
      <div className="pt-4">
        <SectionLabel text="🎧 TINGLASH" />
        <button
          onClick={() => playAudio(s.listening.audio)}
          className="mx-auto my-5 w-16 h-16 rounded-full bg-emerald-deep text-white text-2xl flex items-center justify-center active:scale-90 transition-transform"
        >
          🔊
        </button>
        {s.listening.questions.map((q, i) => (
          <div key={i} className="mt-2 rounded-2xl bg-card border border-cardline p-4">
            <p className="text-sm font-bold">{q.q_uz}</p>
            {revealed.has(i) ? (
              <p className="mt-2 text-sm font-extrabold text-emerald-deep">→ {q.a}</p>
            ) : (
              <button
                onClick={() => setRevealed((r) => new Set(r).add(i))}
                className="mt-2 text-xs font-extrabold text-emerald-deep underline underline-offset-4"
              >
                Javobni ko'rish
              </button>
            )}
          </div>
        ))}
        {s.listening.transcript_ar && (
          <div className="mt-3 rounded-2xl bg-card border border-cardline p-4">
            {revealed.has(-1) ? (
              <div className="font-arabic text-2xl" dir="rtl">{s.listening.transcript_ar}</div>
            ) : (
              <button
                onClick={() => setRevealed((r) => new Set(r).add(-1))}
                className="text-xs font-extrabold text-ink-soft underline underline-offset-4"
              >
                Matnni ko'rish
              </button>
            )}
          </div>
        )}
        <NextBtn onClick={onNext} />
      </div>
    );
  }

  if (which === 2) {
    return (
      <div className="pt-4">
        <SectionLabel text="🗣 GAPIRISH" />
        <p className="text-sm font-semibold">{s.speaking.task_uz}</p>
        <div className="mt-3 space-y-2">
          {s.speaking.target_ar.map((t, i) => (
            <div key={i} className="rounded-2xl bg-card border border-cardline p-4 text-center">
              <ArabicText text={t} lookup={lookup} className="text-3xl" />
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-ink-soft font-semibold text-center">
          Ovoz chiqarib o'qing — talaffuzga e'tibor bering
        </p>
        <NextBtn onClick={onNext} label="✓ O'qib chiqdim" />
      </div>
    );
  }

  // writing
  return (
    <div className="pt-4">
      <SectionLabel text="✍️ YOZISH" />
      <p className="text-sm font-semibold">{s.writing.task_uz}</p>
      <textarea
        value={writing}
        onChange={(e) => setWriting(e.target.value)}
        dir="auto"
        rows={3}
        className="mt-3 w-full rounded-2xl border-2 border-emerald-deep/50 bg-card px-4 py-3 text-xl font-bold outline-none focus:border-emerald-deep font-arabic"
        placeholder="Shu yerga yozing..."
      />
      {feedback ? (
        <div className="mt-3 rounded-2xl bg-gold-soft/60 border border-gold/30 p-4 text-sm font-semibold leading-relaxed">
          🐪 {feedback}
        </div>
      ) : (
        <button
          onClick={() => {
            setEvaluating(true);
            api
              .evalWriting(lesson.id, writing)
              .then((r) => setFeedback(r.feedback_uz))
              .catch(() => setFeedback("Baholashda xatolik — davom etavering."))
              .finally(() => setEvaluating(false));
          }}
          disabled={!writing.trim() || evaluating}
          className="mt-3 w-full rounded-2xl bg-card border border-cardline py-3 font-extrabold disabled:opacity-40"
        >
          {evaluating ? "Baholanmoqda..." : "🤖 AI bahosi"}
        </button>
      )}
      <NextBtn onClick={onNext} />
    </div>
  );
}

/* ── Yordamchilar ── */

function Shell({
  children,
  onClose,
  progress,
  hideBar,
}: {
  children: React.ReactNode;
  onClose: () => void;
  progress: number;
  hideBar?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-30 bg-sand overflow-y-auto">
      <div className="max-w-md mx-auto px-5 pt-5 pb-32">
        {!hideBar && (
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="text-2xl text-ink-soft font-bold leading-none active:opacity-60"
            >
              ✕
            </button>
            <div className="flex-1 h-2.5 rounded-full bg-cardline overflow-hidden">
              <div
                className="h-full rounded-full bg-emerald-deep transition-all duration-500"
                style={{ width: `${Math.round(progress * 100)}%` }}
              />
            </div>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}

function SectionLabel({ text, center }: { text: string; center?: boolean }) {
  return (
    <div
      className={`text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2 ${
        center ? "text-center" : ""
      }`}
    >
      {text}
    </div>
  );
}

function NextBtn({ onClick, label = "Keyingi" }: { onClick: () => void; label?: string }) {
  return (
    <button
      onClick={() => {
        tg()?.HapticFeedback?.impactOccurred("light");
        onClick();
      }}
      className="mt-6 w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg active:scale-[0.98] transition-transform"
    >
      {label}
    </button>
  );
}
