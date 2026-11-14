/** Maxsus test — zaif so'zlaringiz (eng ko'p adashilganlar) bo'yicha tez mashq. */

import { useEffect, useState } from "react";
import { api, type QuizQuestion, type RunInfo } from "../lib/api";
import RunQuiz from "./v2/RunQuiz";

export default function WeakPractice({ onClose }: { onClose: () => void }) {
  const [items, setItems] = useState<QuizQuestion[] | null>(null);
  const [run, setRun] = useState<RunInfo | null>(null);
  const [empty, setEmpty] = useState(false);
  const [result, setResult] = useState<{ correct: number; total: number; xp: number } | null>(null);

  useEffect(() => {
    api
      .getWeakPractice()
      .then((r) => {
        if (!r.items.length || !r.run) setEmpty(true);
        else {
          setItems(r.items);
          setRun(r.run);
        }
      })
      .catch(() => setEmpty(true));
  }, []);

  return (
    <div className="fixed inset-0 z-30 bg-sand overflow-y-auto">
      <div className="max-w-md mx-auto px-5 pt-5 pb-28">
        <div className="flex items-center gap-3 mb-2">
          <button
            onClick={onClose}
            className="text-2xl text-ink-soft font-bold leading-none active:opacity-60"
          >
            ✕
          </button>
          <div className="font-extrabold">🎯 Zaif so'zlar</div>
        </div>

        {empty && (
          <div className="min-h-[60vh] flex flex-col items-center justify-center gap-3 text-center px-6">
            <div className="text-5xl">🎯</div>
            <h2 className="text-xl font-extrabold">Hali yetarli so'z yo'q</h2>
            <p className="text-sm text-ink-soft font-semibold">
              Kamida 4 ta so'z o'rgangach, bu rejim zaif joylaringizni aniqlab
              mashq qildiradi.
            </p>
          </div>
        )}

        {items && run && !result && (
          <div className="pt-2">
            <RunQuiz
              runId={run.id}
              items={items}
              label="ZAIF SO'ZLAR TESTI"
              context="weak"
              onFinish={() => {
                api
                  .completeWeakPractice(run.id)
                  .then((r) => setResult({ correct: r.correct, total: r.total, xp: r.xp_earned }))
                  .catch(() => setResult({ correct: 0, total: items.length, xp: 0 }));
              }}
            />
          </div>
        )}

        {result && (
          <div className="min-h-[60vh] flex flex-col items-center justify-center gap-3 text-center">
            <div className="text-6xl">🎯</div>
            <h1 className="text-2xl font-extrabold">Mashq tugadi!</h1>
            <p className="text-ink-soft font-semibold">
              {result.correct}/{result.total} to'g'ri
            </p>
            <div className="rounded-2xl bg-gold-soft border border-gold/30 px-8 py-4">
              <span className="text-3xl font-extrabold text-emerald-dark">
                +{result.xp} XP
              </span>
            </div>
            <p className="text-xs text-ink-soft font-semibold px-8">
              Xato so'zlar takror kartotekasida bugunga qaytarildi
            </p>
            <button
              onClick={onClose}
              className="w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg"
            >
              Yakunlash
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
