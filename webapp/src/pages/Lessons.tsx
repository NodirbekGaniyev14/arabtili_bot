import { useEffect, useState } from "react";
import {
  api,
  type ComingSoonModule,
  type ModuleInfo,
} from "../lib/api";

interface LessonsProps {
  onOpen: (lessonId: string) => void;
}

export default function Lessons({ onOpen }: LessonsProps) {
  const [modules, setModules] = useState<ModuleInfo[] | null>(null);
  const [comingSoon, setComingSoon] = useState<ComingSoonModule[]>([]);
  const [error, setError] = useState(false);

  useEffect(() => {
    api
      .getModules()
      .then((r) => {
        setModules(r.modules);
        setComingSoon(r.coming_soon);
      })
      .catch(() => setError(true));
  }, []);

  if (error) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center text-ink-soft font-semibold">
        Yuklashda xatolik. Qayta urinib ko'ring.
      </div>
    );
  }

  if (!modules) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="w-10 h-10 rounded-xl bg-emerald-deep animate-pulse" />
      </div>
    );
  }

  return (
    <div className="px-4 pt-4 space-y-4">
      <h1 className="text-[26px] font-extrabold">Darslar</h1>

      {modules.map((mod) => (
        <section
          key={mod.id}
          className="rounded-3xl bg-card border border-cardline p-4"
        >
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

          {/* Joriy dars nomi */}
          {(() => {
            const current = mod.lessons.find((l) => l.unlocked && !l.done);
            return current ? (
              <button
                onClick={() => onOpen(current.id)}
                className="mt-3 w-full rounded-xl bg-emerald-deep/10 text-emerald-dark font-bold text-sm py-2.5 active:scale-[0.98] transition-transform"
              >
                ▶ {current.title}
              </button>
            ) : null;
          })()}
        </section>
      ))}

      {comingSoon.length > 0 && (
        <section>
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2">
            TEZ ORADA
          </div>
          <div className="space-y-2">
            {comingSoon.map((m) => (
              <div
                key={m.id}
                className="rounded-2xl bg-card/60 border border-cardline border-dashed p-3.5 flex items-center justify-between opacity-70"
              >
                <span className="font-bold text-ink-soft">{m.title}</span>
                <span className="text-xs font-bold text-ink-soft">🔒</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
