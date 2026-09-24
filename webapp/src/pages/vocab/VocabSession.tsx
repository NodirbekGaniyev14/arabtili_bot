/** Lug'at 2.0 sessiyasi (K24): 10 so'z → 2 × 5 fleshkarta → 10 savollik test → natija + XP.
 *
 *  Har 5 talik qism:
 *    1) Tanishuv — «YANGI SO'Z»: arabcha, tarjima, audio (o'zi o'qiladi), kitobdan misol.
 *    2) Eslash — arabcha o'zi; «Javobni ko'rish» → «Bilmadim / Bildim». Bilmagani 2 kartadan keyin
 *       qaytadi — hammasi «Bildim» bo'lguncha (mustahkamlash).
 *  So'ng test (arabcha→ma'no, eshitib→ma'no, ma'no→arabcha) va natija: foiz, xato so'zlar, XP. */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type Badge,
  type VocabCard,
  type VocabExamQ,
  type VocabExamType,
  type VocabSessionData,
  type VocabSessionResult,
} from "../../lib/api";
import BadgeToast from "../../components/BadgeToast";
import MashaAllah from "../../components/MashaAllah";
import {
  AudioPill,
  HighlightAr,
  HighlightUz,
  ProgressBar,
  haptic,
  playWord,
  saveLast,
} from "./vocabUi";

type RunMode = "new" | "review" | "retry";

interface Run {
  mode: RunMode;
  words: VocabCard[];
  exam: VocabExamQ[];
}

type Phase =
  | { k: "loading" }
  | { k: "error"; msg: string; resend?: boolean }
  | { k: "intro"; b: number; i: number }
  | { k: "recall"; b: number }
  | { k: "batchDone"; b: number }
  | { k: "test"; qi: number }
  | { k: "sending" }
  | { k: "result" };

interface Props {
  level: string;
  topic: string;
  onClose: (changed: boolean) => void;
}

const BATCH = 5;

function shuffle<T>(a: T[]): T[] {
  const b = [...a];
  for (let i = b.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [b[i], b[j]] = [b[j], b[i]];
  }
  return b;
}

const TEST_LABEL: Record<VocabExamType, string> = {
  ar_uz: "Ma'nosini toping",
  audio_uz: "Eshiting va ma'nosini toping",
  uz_ar: "Arabchasini toping",
};

export default function VocabSession({ level, topic, onClose }: Props) {
  const [data, setData] = useState<VocabSessionData | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [phase, setPhase] = useState<Phase>({ k: "loading" });
  const [queue, setQueue] = useState<string[]>([]);
  const [revealed, setRevealed] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  const [result, setResult] = useState<VocabSessionResult | null>(null);
  const [badges, setBadges] = useState<Badge[]>([]);
  const unknown = useRef<Set<string>>(new Set());
  const answers = useRef<{ key: string; type: VocabExamType; chosen: string }[]>([]);
  const changed = useRef(false);

  const batches = useMemo(() => {
    const w = run?.words ?? [];
    const out: VocabCard[][] = [];
    for (let i = 0; i < w.length; i += BATCH) out.push(w.slice(i, i + BATCH));
    return out;
  }, [run]);
  const byKey = useMemo(() => new Map((run?.words ?? []).map((w) => [w.key, w])), [run]);

  const begin = (r: Run) => {
    unknown.current = new Set();
    answers.current = [];
    setRun(r);
    setResult(null);
    setPicked(null);
    setRevealed(false);
    if (r.mode === "review") {
      setQueue(shuffle(r.words.slice(0, BATCH).map((w) => w.key)));
      setPhase({ k: "recall", b: 0 });
    } else {
      setPhase({ k: "intro", b: 0, i: 0 });
    }
  };

  const load = () => {
    setPhase({ k: "loading" });
    api
      .vocabSession(level, topic)
      .then((d) => {
        setData(d);
        saveLast({ level, topic, title: d.topic.title_uz });
        begin({ mode: d.mode, words: d.words, exam: d.exam });
      })
      .catch((e) => setPhase({ k: "error", msg: (e as { detail?: string })?.detail || "Yuklanmadi — internetni tekshiring" }));
  };

  useEffect(load, [level, topic]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Tanishuv ──
  const nextIntro = (b: number, i: number) => {
    haptic.tap();
    if (i + 1 < batches[b].length) {
      setPhase({ k: "intro", b, i: i + 1 });
      return;
    }
    setQueue(shuffle(batches[b].map((w) => w.key)));
    setRevealed(false);
    setPhase({ k: "recall", b });
  };

  // ── Eslash (Bildim / Bilmadim) ──
  const recallAnswer = (b: number, knew: boolean) => {
    const [cur, ...rest] = queue;
    let next = rest;
    if (knew) {
      haptic.ok();
    } else {
      haptic.bad();
      unknown.current.add(cur);
      // 2 ta kartadan keyin qaytadi (oxirgisi bo'lsa — darhol yana)
      next = [...rest.slice(0, 2), cur, ...rest.slice(2)];
    }
    setRevealed(false);
    if (next.length) {
      setQueue(next);
      return;
    }
    setQueue([]);
    setPhase({ k: "batchDone", b });
  };

  const afterBatch = (b: number) => {
    haptic.tap();
    if (b + 1 < batches.length) {
      if (run?.mode === "review") {
        setQueue(shuffle(batches[b + 1].map((w) => w.key)));
        setPhase({ k: "recall", b: b + 1 });
      } else {
        setPhase({ k: "intro", b: b + 1, i: 0 });
      }
      return;
    }
    setPicked(null);
    setPhase({ k: "test", qi: 0 });
  };

  // ── Test ── (to'g'ri javobdan keyin o'zi o'tadi — tezlik; xatoda to'g'risini ko'rib «Davom etish»)
  const autoNext = useRef<number | null>(null);
  const choose = (q: VocabExamQ, qi: number, opt: string) => {
    if (picked !== null) return;
    setPicked(opt);
    answers.current.push({ key: q.key, type: q.type, chosen: opt });
    const w = byKey.get(q.key);
    if (opt === q.answer) {
      haptic.ok();
      if (w && q.type !== "ar_uz") playWord(w);
      autoNext.current = window.setTimeout(() => nextQ(qi), 1000);
    } else {
      haptic.bad();
      if (w) playWord(w);
    }
  };

  useEffect(() => () => {
    if (autoNext.current) window.clearTimeout(autoNext.current);
  }, []);

  const nextQ = (qi: number) => {
    if (autoNext.current) {
      window.clearTimeout(autoNext.current);
      autoNext.current = null;
    }
    if (!run) return;
    if (qi + 1 < run.exam.length) {
      setPicked(null);
      setPhase({ k: "test", qi: qi + 1 });
      return;
    }
    finish();
  };

  const finish = () => {
    if (!run) return;
    setPhase({ k: "sending" });
    api
      .vocabFinish({ level, topic, mode: run.mode, answers: answers.current, unknown: [...unknown.current] })
      .then((r) => {
        changed.current = true;
        setResult(r);
        setBadges(r.new_badges ?? []);
        setPhase({ k: "result" });
        if (r.percent >= 80) haptic.ok();
      })
      .catch((e) =>
        // Javoblar yo'qolmasin — «Qayta urinish» natijani qayta yuboradi (yangi sessiya emas)
        setPhase({
          k: "error",
          msg: (e as { detail?: string })?.detail || "Natija saqlanmadi — internetni tekshirib, qayta urinib ko'ring",
          resend: true,
        })
      );
  };

  const retryWrong = () => {
    if (!result || !run) return;
    const keys = new Set(result.wrong.map((w) => w.key));
    const exam = run.exam.filter((q) => keys.has(q.key)).map((q) => ({ ...q, options: shuffle(q.options) }));
    const words = result.wrong.map(({ type: _t, chosen: _c, ...w }) => w as VocabCard);
    begin({ mode: "retry", words, exam: shuffle(exam) });
  };

  // Tark etish — o'rtada bo'lsa so'raymiz (natija saqlanmaydi)
  const close = () => {
    const midway = phase.k !== "result" && phase.k !== "error" && phase.k !== "loading";
    if (!midway) {
      onClose(changed.current);
      return;
    }
    const msg = "Sessiyani tark etasizmi? Bu 10 so'z natijasi saqlanmaydi.";
    const tgc = window.Telegram?.WebApp;
    if (tgc?.showConfirm && tgc.isVersionAtLeast?.("6.2")) {
      tgc.showConfirm(msg, (ok) => ok && onClose(changed.current));
    } else if (window.confirm(msg)) {
      onClose(changed.current);
    }
  };

  // ── Umumiy progress (sarlavha chizig'i): qism = tanishuv + eslash, keyin test ──
  const n = run?.words.length ?? 0;
  const examN = run?.exam.length ?? 0;
  const per = run?.mode === "review" ? 1 : 2;
  const before = (b: number) => batches.slice(0, b).reduce((s, x) => s + x.length * per, 0);
  const totalSteps = n * per + examN || 1;
  let done = 0;
  if (phase.k === "intro") done = before(phase.b) + phase.i;
  if (phase.k === "recall") {
    const len = batches[phase.b]?.length ?? 0;
    done = before(phase.b) + (per - 1) * len + (len - new Set(queue).size);
  }
  if (phase.k === "batchDone") done = before(phase.b + 1);
  if (phase.k === "test") done = n * per + phase.qi;
  if (phase.k === "sending" || phase.k === "result") done = totalSteps;

  const stepLabel =
    phase.k === "intro"
      ? `📖 Tanishuv · ${phase.b + 1}-qism · ${phase.i + 1}/${batches[phase.b]?.length ?? 0}`
      : phase.k === "recall"
        ? `🧠 Eslash · ${phase.b + 1}-qism · ${new Set(queue).size} ta qoldi`
        : phase.k === "batchDone"
          ? `✅ ${phase.b + 1}-qism tayyor`
          : phase.k === "test"
            ? `🎯 Test · ${phase.qi + 1}/${examN}`
            : phase.k === "result" || phase.k === "sending"
              ? "🏁 Natija"
              : "";

  return (
    <div className="fixed inset-0 z-50 bg-sand flex flex-col max-w-md mx-auto">
      <BadgeToast badges={badges} />
      {/* Sarlavha */}
      <div className="px-4 pt-3 pb-2 bg-sand">
        <div className="flex items-center gap-3">
          <button
            onClick={close}
            className="w-9 h-9 shrink-0 rounded-full bg-card border border-cardline text-ink-soft font-extrabold active:scale-95"
            aria-label="Yopish"
          >
            ✕
          </button>
          <div className="min-w-0 flex-1">
            <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft truncate">
              {level} · {data?.topic.title_uz ?? "Lug'at"}
              {run?.mode === "review" ? " · TAKRORLASH" : run?.mode === "retry" ? " · XATOLAR" : ""}
            </div>
            <div className="text-[13px] font-extrabold truncate">{stepLabel}</div>
          </div>
          {data && (
            <span className="font-arabic text-lg text-emerald-deep/70 shrink-0" dir="rtl">
              {data.topic.title_ar}
            </span>
          )}
        </div>
        <ProgressBar value={done} max={totalSteps} className="mt-2.5 h-2 bg-cardline" fill="bg-emerald-deep" />
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-4">
        {phase.k === "loading" && (
          <div className="h-full flex flex-col items-center justify-center text-ink-soft font-semibold">
            <div className="flex items-end gap-1 h-8 mb-3">
              {[0, 1, 2, 3].map((i) => (
                <span key={i} className="loading-bar w-2 h-8 rounded-full bg-emerald-deep" style={{ animationDelay: `${i * 0.12}s` }} />
              ))}
            </div>
            So'zlar tayyorlanmoqda…
          </div>
        )}

        {phase.k === "error" && (
          <div className="mt-10 rounded-3xl bg-card border border-cardline p-6 text-center">
            <div className="text-4xl">😕</div>
            <p className="mt-2 font-bold">{phase.msg}</p>
            <button
              onClick={phase.resend ? finish : load}
              className="mt-4 rounded-2xl bg-emerald-deep px-6 py-3 text-white font-extrabold"
            >
              {phase.resend ? "Natijani qayta yuborish" : "Qayta urinish"}
            </button>
          </div>
        )}

        {phase.k === "intro" && batches[phase.b]?.[phase.i] && (
          <IntroCard key={batches[phase.b][phase.i].key} w={batches[phase.b][phase.i]} />
        )}

        {phase.k === "recall" && queue[0] && byKey.get(queue[0]) && (
          <RecallCard key={`${queue[0]}-${queue.length}`} w={byKey.get(queue[0])!} revealed={revealed} />
        )}

        {phase.k === "batchDone" && (
          <BatchDone
            words={batches[phase.b] ?? []}
            last={phase.b + 1 >= batches.length}
            testN={examN}
            unknown={unknown.current}
          />
        )}

        {phase.k === "test" && run?.exam[phase.qi] && (
          <TestCard
            key={phase.qi}
            q={run.exam[phase.qi]}
            w={byKey.get(run.exam[phase.qi].key)}
            picked={picked}
            onPick={(o) => choose(run.exam[phase.qi], phase.qi, o)}
          />
        )}

        {phase.k === "sending" && (
          <div className="h-full flex items-center justify-center text-ink-soft font-semibold">Natija hisoblanmoqda…</div>
        )}

        {phase.k === "result" && result && data && <ResultView r={result} level={level} mode={run?.mode ?? "new"} />}
      </div>

      {/* Pastki tugmalar */}
      <div className="px-4 pt-2 pb-4 bg-sand" style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}>
        {phase.k === "intro" && (
          <button onClick={() => nextIntro(phase.b, phase.i)} className={BTN_MAIN}>
            {phase.i + 1 < (batches[phase.b]?.length ?? 0) ? "Keyingi" : "Eslashni boshlash →"}
          </button>
        )}

        {phase.k === "recall" &&
          (!revealed ? (
            <button
              onClick={() => {
                haptic.tap();
                setRevealed(true);
                const w = byKey.get(queue[0]);
                if (w) playWord(w);
              }}
              className="w-full rounded-2xl bg-card border-2 border-emerald-deep py-4 font-extrabold text-emerald-deep active:scale-[0.98] transition-transform"
            >
              👁 Javobni ko'rish
            </button>
          ) : (
            <div className="grid grid-cols-2 gap-2.5">
              <button
                onClick={() => recallAnswer(phase.b, false)}
                className="rounded-2xl bg-terracotta py-4 font-extrabold text-white active:scale-[0.98] transition-transform"
              >
                ✗ Bilmadim
              </button>
              <button onClick={() => recallAnswer(phase.b, true)} className={BTN_MAIN}>
                ✓ Bildim
              </button>
            </div>
          ))}

        {phase.k === "batchDone" && (
          <button onClick={() => afterBatch(phase.b)} className={BTN_MAIN}>
            {phase.b + 1 < batches.length ? "Keyingi 5 ta so'z →" : `🎯 Testni boshlash · ${examN} savol`}
          </button>
        )}

        {phase.k === "test" && picked !== null && run && (
          <button onClick={() => nextQ(phase.qi)} className={BTN_MAIN}>
            {phase.qi + 1 < run.exam.length ? "Davom etish" : "Natijani ko'rish"}
          </button>
        )}

        {phase.k === "result" && result && (
          <div className="space-y-2">
            {result.wrong.length > 0 && (
              <button onClick={retryWrong} className={BTN_MAIN}>
                🔁 Xatolarni mustahkamlash · {result.wrong.length} ta
              </button>
            )}
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => onClose(true)}
                className="rounded-2xl bg-card border border-cardline py-3.5 font-extrabold text-ink-soft active:scale-[0.98]"
              >
                Mavzular
              </button>
              <button
                onClick={load}
                className={
                  result.wrong.length > 0
                    ? "rounded-2xl bg-card border-2 border-emerald-deep py-3.5 font-extrabold text-emerald-deep active:scale-[0.98]"
                    : BTN_MAIN
                }
              >
                {result.remaining > 0 ? "▶ Keyingi 10 so'z" : "🔁 Takrorlash"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const BTN_MAIN =
  "w-full rounded-2xl bg-emerald-deep py-4 font-extrabold text-white shadow-md active:scale-[0.98] transition-transform";

// ───────────────────────── kartalar ─────────────────────────

function WordMeta({ w }: { w: VocabCard }) {
  if (!w.plural_ar && !w.root) return null;
  return (
    <div className="mt-3 flex flex-wrap justify-center gap-1.5 text-[11px] font-bold text-ink-soft">
      {w.plural_ar && (
        <span className="rounded-full bg-sand border border-cardline px-2.5 py-0.5">
          ko'pligi: <span className="font-arabic text-[14px] text-ink">{w.plural_ar}</span>
        </span>
      )}
      {w.root && (
        <span className="rounded-full bg-sand border border-cardline px-2.5 py-0.5">
          o'zak: <span className="font-arabic text-[14px] text-ink">{w.root}</span>
        </span>
      )}
    </div>
  );
}

function Example({ w }: { w: VocabCard }) {
  if (!w.example_ar) return null;
  return (
    <div className="mt-4 border-t border-cardline pt-3">
      <div className="text-[11px] font-bold text-ink-soft">Kitobdan misol</div>
      <HighlightAr text={w.example_ar} word={w.ar} className="mt-1 block font-arabic text-[22px] leading-relaxed" />
      {w.example_uz && <HighlightUz text={w.example_uz} gloss={w.uz} className="mt-0.5 block text-[13px] text-ink-soft font-semibold" />}
    </div>
  );
}

function IntroCard({ w }: { w: VocabCard }) {
  return (
    <div className="mt-2 rounded-3xl bg-card border border-cardline shadow-sm px-5 py-7 text-center girih-bg">
      <div className="text-[11px] font-extrabold tracking-[0.18em] text-emerald-deep">YANGI SO'Z</div>
      <div className="mt-3 font-arabic text-[56px] leading-[1.35] text-ink" dir="rtl">
        {w.ar}
      </div>
      {w.translit && <div className="text-[13px] italic font-semibold text-ink-soft">{w.translit}</div>}
      <div className="mt-2 text-[24px] font-extrabold leading-tight">{w.uz}</div>
      <div className="mt-3">
        <AudioPill word={w} auto />
      </div>
      <WordMeta w={w} />
      <Example w={w} />
      {w.note_uz && (
        <div className="mt-3 rounded-2xl bg-gold-soft/70 border border-gold/30 px-3 py-2 text-left text-[12px] font-semibold">
          💡 {w.note_uz}
        </div>
      )}
    </div>
  );
}

function RecallCard({ w, revealed }: { w: VocabCard; revealed: boolean }) {
  return (
    <div className="mt-2 rounded-3xl bg-card border border-cardline shadow-sm px-5 py-8 text-center">
      <div className="text-[11px] font-extrabold tracking-[0.18em] text-gold">ESLANG — MA'NOSI NIMA?</div>
      <div className="mt-4 font-arabic text-[60px] leading-[1.35] text-ink" dir="rtl">
        {w.ar}
      </div>
      <div className="mt-2">
        <AudioPill word={w} variant="soft" />
      </div>
      {revealed ? (
        <div className="mt-4">
          <div className="text-[24px] font-extrabold leading-tight text-emerald-dark">{w.uz}</div>
          {w.translit && <div className="text-[13px] italic font-semibold text-ink-soft">{w.translit}</div>}
          <Example w={w} />
        </div>
      ) : (
        <div className="mt-6 text-[12px] font-semibold text-ink-soft">Avval o'zingiz eslang, keyin javobni oching</div>
      )}
    </div>
  );
}

function BatchDone({
  words,
  last,
  testN,
  unknown,
}: {
  words: VocabCard[];
  last: boolean;
  testN: number;
  unknown: Set<string>;
}) {
  return (
    <div className="mt-2">
      <div className="rounded-3xl bg-emerald-deep text-white p-5 text-center shadow-md">
        <div className="text-4xl">{last ? "🎯" : "✅"}</div>
        <div className="mt-1 text-lg font-extrabold">{words.length} ta so'z o'zlashtirildi!</div>
        <div className="text-[13px] text-white/80 font-semibold">
          {last ? `Endi test: ${testN} savol — shu so'zlar bo'yicha` : "Zo'r! Keyingi 5 ta so'zga o'tamiz"}
        </div>
      </div>
      <div className="mt-3 space-y-2">
        {words.map((w) => (
          <button
            key={w.key}
            onClick={() => playWord(w)}
            className="w-full flex items-center gap-3 rounded-2xl bg-card border border-cardline px-3.5 py-2.5 text-left active:scale-[0.99]"
          >
            <span className="w-8 h-8 shrink-0 rounded-xl bg-gold-soft flex items-center justify-center text-sm">🔊</span>
            <span className="min-w-0 flex-1 text-[14px] font-extrabold truncate">{w.uz}</span>
            {unknown.has(w.key) && (
              <span className="shrink-0 rounded-full bg-terracotta/10 px-2 py-0.5 text-[10px] font-extrabold text-terracotta">
                mustahkamlandi
              </span>
            )}
            <span className="font-arabic text-2xl shrink-0" dir="rtl">
              {w.ar}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

function TestCard({
  q,
  w,
  picked,
  onPick,
}: {
  q: VocabExamQ;
  w?: VocabCard;
  picked: string | null;
  onPick: (o: string) => void;
}) {
  const answered = picked !== null;
  const arabicOptions = q.type === "uz_ar";
  const [playing, setPlaying] = useState(false);
  const listen = () => {
    if (!w) return;
    setPlaying(true);
    playWord(w, () => setPlaying(false));
  };
  useEffect(() => {
    if (q.type !== "audio_uz") return;
    const t = window.setTimeout(listen, 300);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q.key]);

  return (
    <div className="mt-2">
      <div className="rounded-3xl bg-card border border-cardline shadow-sm px-5 py-6 text-center">
        <div className="text-[11px] font-extrabold tracking-[0.16em] text-emerald-deep">{TEST_LABEL[q.type].toUpperCase()}</div>
        {q.type === "audio_uz" ? (
          <>
            <button
              onClick={listen}
              className={`mt-4 mx-auto w-24 h-24 rounded-full flex items-center justify-center text-4xl text-white shadow-md active:scale-95 transition-transform ${
                playing ? "bg-emerald-dark scale-105" : "bg-emerald-deep"
              }`}
              aria-label="Tinglash"
            >
              🔊
            </button>
            <div className="mt-2 text-[12px] font-semibold text-ink-soft">{playing ? "Chalinmoqda…" : "Qayta eshitish uchun bosing"}</div>
            {answered && (
              <div className="mt-2 font-arabic text-4xl" dir="rtl">
                {q.prompt}
              </div>
            )}
          </>
        ) : q.type === "ar_uz" ? (
          <>
            <div className="mt-3 font-arabic text-[54px] leading-[1.35]" dir="rtl">
              {q.prompt}
            </div>
            {w && (
              <div className="mt-1">
                <AudioPill word={w} variant="soft" />
              </div>
            )}
          </>
        ) : (
          <div className="mt-4 text-[26px] font-extrabold leading-tight">{q.prompt}</div>
        )}
      </div>

      <div className={`mt-3 ${arabicOptions ? "grid grid-cols-2 gap-2.5" : "space-y-2.5"}`}>
        {q.options.map((o) => {
          const isRight = o === q.answer;
          const isPicked = o === picked;
          const state = !answered
            ? "bg-card border-cardline active:scale-[0.98]"
            : isRight
              ? "bg-emerald-deep/10 border-emerald-deep text-emerald-dark"
              : isPicked
                ? "bg-terracotta/10 border-terracotta text-terracotta"
                : "bg-card border-cardline opacity-55";
          return (
            <button
              key={o}
              disabled={answered}
              onClick={() => onPick(o)}
              className={`w-full rounded-2xl border-2 px-4 transition-all ${state} ${
                arabicOptions ? "py-4 font-arabic text-[26px] leading-snug text-center" : "py-3.5 text-left text-[15px] font-bold flex items-center gap-2"
              }`}
              dir={arabicOptions ? "rtl" : undefined}
            >
              {!arabicOptions && answered && (isRight || isPicked) && <span>{isRight ? "✓" : "✗"}</span>}
              <span className={arabicOptions ? "" : "min-w-0 flex-1"}>{o}</span>
            </button>
          );
        })}
      </div>

      {answered && picked !== q.answer && w && (
        <div className="mt-3 rounded-2xl bg-card border border-cardline px-4 py-3 flex items-center gap-3">
          <button onClick={() => playWord(w)} className="w-9 h-9 shrink-0 rounded-xl bg-gold-soft text-sm">
            🔊
          </button>
          <div className="min-w-0 flex-1">
            <div className="text-[11px] font-extrabold text-ink-soft">TO'G'RI JAVOB</div>
            <div className="text-[14px] font-extrabold truncate">{w.uz}</div>
          </div>
          <span className="font-arabic text-3xl shrink-0" dir="rtl">
            {w.ar}
          </span>
        </div>
      )}
    </div>
  );
}

function ResultView({ r, level, mode }: { r: VocabSessionResult; level: string; mode: RunMode }) {
  // Mavzu tokenlari — qorong'i rejimda yorqinroq tuslar avtomatik
  const color =
    r.percent >= 80 ? "var(--color-emerald-deep)" : r.percent >= 50 ? "var(--color-gold)" : "var(--color-terracotta)";
  const R = 52;
  const C = 2 * Math.PI * R;
  const title = r.percent >= 80 ? "Ajoyib natija! 🎉" : r.percent >= 50 ? "Yaxshi, yana ozgina! 💪" : "Qayta mashq qilamiz 🌱";
  return (
    <div className="mt-2 space-y-3">
      <div className="rounded-3xl bg-card border border-cardline shadow-sm p-5 text-center">
        <svg viewBox="0 0 120 120" className="mx-auto w-32 h-32 -rotate-90">
          <circle cx="60" cy="60" r={R} fill="none" stroke="var(--color-cardline)" strokeWidth="10" />
          <circle
            cx="60"
            cy="60"
            r={R}
            fill="none"
            stroke={color}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={C}
            strokeDashoffset={C * (1 - r.percent / 100)}
            style={{ transition: "stroke-dashoffset 0.8s ease" }}
          />
        </svg>
        <div className="-mt-[88px] mb-[52px] text-3xl font-extrabold" style={{ color }}>
          {r.percent}%
        </div>
        <div className="text-lg font-extrabold">{title}</div>
        <div className="text-[13px] text-ink-soft font-semibold">
          {r.correct}/{r.total} to'g'ri{mode === "retry" ? " · xatolar takrori" : mode === "review" ? " · takrorlash" : ""}
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
          <span className="rounded-full bg-gold-soft px-3 py-1 text-[13px] font-extrabold">+{r.xp} XP</span>
          {r.added > 0 && (
            <span className="rounded-full bg-emerald-deep/10 px-3 py-1 text-[12px] font-extrabold text-emerald-dark">
              +{r.added} so'z kartotekada
            </span>
          )}
        </div>
        {r.xp_capped && (
          <div className="mt-1.5 text-[11px] font-semibold text-ink-soft">Bugungi lug'at XP chegarasi to'ldi — mashq baribir foydali!</div>
        )}
        <div className="mt-3 flex justify-center">
          <MashaAllah score={r.percent} />
        </div>
      </div>

      <div className="rounded-2xl bg-card border border-cardline px-4 py-3">
        <div className="flex items-center justify-between text-[12px] font-extrabold">
          <span>Mavzu bo'yicha · {level}</span>
          <span className="text-emerald-dark">
            {r.topic_learned}/{r.topic_total}
          </span>
        </div>
        <ProgressBar value={r.topic_learned} max={r.topic_total} className="mt-2 h-2 bg-cardline" />
        <div className="mt-1.5 text-[11px] font-semibold text-ink-soft">
          {r.remaining > 0 ? `Yana ${r.remaining} ta yangi so'z bor` : "Mavzu to'liq o'rganildi — endi takrorlash rejimi"} · so'zlar «Takror»
          bo'limida qaytadi
        </div>
      </div>

      {r.wrong.length > 0 ? (
        <div className="rounded-2xl bg-card border border-cardline p-3">
          <div className="px-1 text-[11px] font-extrabold tracking-[0.12em] text-terracotta">XATO JAVOBLAR · {r.wrong.length}</div>
          <div className="mt-2 divide-y divide-cardline">
            {r.wrong.map((w) => (
              <button key={w.key} onClick={() => playWord(w)} className="w-full flex items-center gap-3 py-2.5 text-left">
                <span className="w-8 h-8 shrink-0 rounded-xl bg-gold-soft flex items-center justify-center text-sm">🔊</span>
                <div className="min-w-0 flex-1">
                  <div className="text-[14px] font-extrabold truncate">{w.uz}</div>
                  <div className="text-[11px] font-semibold text-terracotta truncate">
                    Siz: <span className={w.type === "uz_ar" ? "font-arabic text-[14px]" : ""}>{w.chosen || "—"}</span>
                  </div>
                </div>
                <span className="font-arabic text-2xl shrink-0" dir="rtl">
                  {w.ar}
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="rounded-2xl bg-emerald-deep/10 border border-emerald-deep/20 px-4 py-3 text-center text-[13px] font-extrabold text-emerald-dark">
          Birorta ham xato yo'q — barakalla! ✨
        </div>
      )}
    </div>
  );
}
