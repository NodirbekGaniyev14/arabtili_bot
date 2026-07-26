import { useEffect, useState } from "react";
import {
  api,
  type CheckpointInfo,
  type LevelSection,
  type LevelsResponse,
  type ModuleInfo,
} from "../lib/api";

interface LessonsProps {
  onOpen: (lessonId: string) => void;
  onOpenCheckpoint: (percent: number) => void;
}

export default function Lessons({ onOpen, onOpenCheckpoint }: LessonsProps) {
  const [data, setData] = useState<LevelsResponse | null>(null);
  const [cp, setCp] = useState<CheckpointInfo | null>(null);
  const [active, setActive] = useState<string>("A0");
  const [error, setError] = useState(false);

  useEffect(() => {
    api
      .getModules()
      .then((r) => {
        setData(r);
        setActive(r.current_level || "A0");
      })
      .catch(() => setError(true));
    api.getCheckpointInfo().then(setCp).catch(() => {});
  }, []);

  if (error) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center text-ink-soft font-semibold">
        Yuklashda xatolik. Qayta urinib ko'ring.
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="w-10 h-10 rounded-xl bg-emerald-deep animate-pulse" />
      </div>
    );
  }

  const activeLevel =
    data.levels.find((l) => l.level === active) ?? data.levels[0];

  return (
    <div className="px-4 pt-4 space-y-4">
      <h1 className="text-[26px] font-extrabold">Darslar</h1>

      {/* Daraja tanlagichi — A0 / A1 / A2 / B1 */}
      <div className="grid grid-cols-4 gap-2">
        {data.levels.map((lvl) => {
          const isActive = lvl.level === active;
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
                {lvl.available ? `${lvl.percent}%` : "🔒"}
              </div>
            </button>
          );
        })}
      </div>

      <LevelView
        level={activeLevel}
        onOpen={onOpen}
        cp={cp && cp.level === activeLevel.level ? cp : null}
        onOpenCheckpoint={onOpenCheckpoint}
      />
    </div>
  );
}

function LevelView({
  level,
  onOpen,
  cp,
  onOpenCheckpoint,
}: {
  level: LevelSection;
  onOpen: (lessonId: string) => void;
  cp: CheckpointInfo | null;
  onOpenCheckpoint: (percent: number) => void;
}) {
  if (!level.available) {
    return (
      <div className="rounded-3xl bg-card border border-cardline border-dashed p-8 text-center space-y-2">
        <div className="text-4xl">🔜</div>
        <div className="font-extrabold text-lg">
          {level.level} — {level.name}
        </div>
        <p className="text-sm text-ink-soft font-semibold">
          Bu daraja darslari tayyorlanmoqda. Tez orada ochiladi!
        </p>
      </div>
    );
  }

  return (
    <>
      {/* Daraja sarlavhasi */}
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
          {level.level} · {level.name.toUpperCase()}
        </div>
        <div className="text-[11px] font-bold text-ink-soft">
          {level.done}/{level.total} dars
        </div>
      </div>

      {cp && cp.checkpoints.length > 0 && (
        <CheckpointStrip cp={cp} onOpen={onOpenCheckpoint} />
      )}

      {level.modules.map((mod) => (
        <ModuleCard key={mod.id} mod={mod} onOpen={onOpen} />
      ))}

      {/* Daraja progressi — pastki qismda */}
      <ProgressFooter level={level} />
    </>
  );
}

/** Mini-imtihonlar chizig'i — 25% / 50% / 75% nuqtalari. */
function CheckpointStrip({
  cp,
  onOpen,
}: {
  cp: CheckpointInfo;
  onOpen: (percent: number) => void;
}) {
  return (
    <div className="rounded-3xl bg-card border border-cardline p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
          🎯 MINI-IMTIHONLAR
        </div>
        <div className="text-[11px] font-bold text-ink-soft">
          o'tish {cp.pass_score}%
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        {cp.checkpoints.map((c) => {
          const state = c.passed
            ? "passed"
            : c.unlocked
              ? "open"
              : "locked";
          return (
            <button
              key={c.percent}
              disabled={state === "locked"}
              onClick={() => onOpen(c.percent)}
              className={`rounded-2xl py-3 px-2 text-center border transition-transform active:scale-95 ${
                state === "passed"
                  ? "bg-emerald-deep text-white border-emerald-deep"
                  : state === "open"
                    ? "bg-gold-soft border-gold/40 text-ink"
                    : "bg-sand border-cardline text-ink-soft opacity-70"
              }`}
            >
              <div className="text-base font-extrabold leading-none">
                {c.percent}%
              </div>
              <div className="text-[10px] font-bold mt-1">
                {state === "passed"
                  ? `✅ ${c.best_score}%`
                  : state === "open"
                    ? c.attempted
                      ? `↻ ${c.best_score}%`
                      : "Topshirish"
                    : `🔒 ${c.need} dars`}
              </div>
            </button>
          );
        })}
      </div>

      <p className="text-[11px] text-ink-soft font-semibold">
        O'tilgan mavzular bo'yicha qisqa test. Yiqilsangiz darslar qulflanmaydi —
        xato so'zlar takrorga qaytadi.
      </p>
    </div>
  );
}

function ModuleCard({
  mod,
  onOpen,
}: {
  mod: ModuleInfo;
  onOpen: (lessonId: string) => void;
}) {
  const current = mod.lessons.find((l) => l.unlocked && !l.done);
  return (
    <section className="rounded-3xl bg-card border border-cardline p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className="font-arabic text-2xl text-emerald-deep leading-none pt-1">
            {mod.arabic_title}
          </span>
          <div>
            <div className="font-extrabold">{mod.title}</div>
            <div className="text-xs text-ink-soft font-semibold">
              {mod.done_count}/{mod.lessons.length} dars
            </div>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        {mod.lessons.map((lesson, i) => {
          const isCurrent = lesson.unlocked && !lesson.done;
          return (
            <button
              key={lesson.id}
              disabled={!lesson.unlocked}
              onClick={() => onOpen(lesson.id)}
              className={`relative w-13 h-13 min-w-13 rounded-full flex items-center justify-center font-extrabold text-base transition-transform active:scale-95 ${
                lesson.done
                  ? "bg-gold text-white"
                  : isCurrent
                    ? "bg-emerald-deep text-white pulse-ring"
                    : "bg-cardline text-ink-soft"
              }`}
              title={lesson.title}
            >
              {lesson.done ? "✓" : lesson.unlocked ? i + 1 : "🔒"}
            </button>
          );
        })}
      </div>

      {current && (
        <button
          onClick={() => onOpen(current.id)}
          className="mt-3 w-full rounded-xl bg-emerald-deep/10 text-emerald-dark font-bold text-sm py-2.5 active:scale-[0.98] transition-transform"
        >
          ▶ {current.title}
        </button>
      )}
    </section>
  );
}

function ProgressFooter({ level }: { level: LevelSection }) {
  const done = level.percent >= 100;
  return (
    <div className="rounded-2xl bg-card border border-cardline p-4 space-y-2">
      <div className="flex items-center justify-between text-sm font-extrabold">
        <span>{done ? "🏆 Daraja tugatildi!" : "Daraja jarayoni"}</span>
        <span className={done ? "text-gold" : "text-emerald-dark"}>
          {level.percent}% tugatildi
        </span>
      </div>
      <div className="h-2.5 rounded-full bg-cardline overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${
            done ? "bg-gold" : "bg-emerald-deep"
          }`}
          style={{ width: `${level.percent}%` }}
        />
      </div>
      <div className="text-[11px] text-ink-soft font-semibold">
        {level.done} / {level.total} dars tugatildi
      </div>
    </div>
  );
}
