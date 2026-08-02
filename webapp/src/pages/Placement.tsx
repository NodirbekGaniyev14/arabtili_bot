/** Daraja aniqlash testi — bosqichli (A0 → B2), AI'siz.
 *
 * Har bosqich 5 savol. Bosqich ≥80% bo'lsa keyingisi beriladi, yiqilsa test
 * to'xtaydi. Daraja = o'tilmagan birinchi bosqich.
 */

import { useEffect, useState } from "react";
import { api, type MicroTestItem, type PlacementResult } from "../lib/api";
import { QuizRunner } from "./v2/exercises";

type Stage =
  | { k: "loading" }
  | { k: "intro"; tier: string; title: string; index: number; count: number; items: MicroTestItem[] }
  | { k: "quiz"; tier: string; title: string; index: number; count: number; items: MicroTestItem[] }
  | { k: "result"; result: PlacementResult }
  | { k: "error" };

export default function Placement({
  onDone,
  onClose,
}: {
  onDone: (result: PlacementResult) => void;
  onClose?: () => void;
}) {
  const [stage, setStage] = useState<Stage>({ k: "loading" });
  const [results, setResults] = useState<Record<string, boolean>>({});

  /** Natijalar satri: "A0:1,A1:0" */
  const encode = (r: Record<string, boolean>) =>
    Object.entries(r)
      .map(([t, ok]) => `${t}:${ok ? 1 : 0}`)
      .join(",");

  const loadStep = async (r: Record<string, boolean>) => {
    try {
      const step = await api.getPlacementStep(encode(r));
      if (step.done) {
        const res = await api.finishPlacement(r);
        setStage({ k: "result", result: res });
      } else {
        setStage({
          k: "intro",
          tier: step.tier,
          title: step.tier_title,
          index: step.tier_index,
          count: step.tier_count,
          items: step.items,
        });
      }
    } catch {
      setStage({ k: "error" });
    }
  };

  useEffect(() => {
    loadStep({});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const finishTier = (tier: string, correct: number, total: number) => {
    const passed = total > 0 && correct / total >= 0.8;
    const next = { ...results, [tier]: passed };
    setResults(next);
    setStage({ k: "loading" });
    loadStep(next);
  };

  return (
    <div className="fixed inset-0 z-40 bg-sand overflow-y-auto">
      <div className="max-w-md mx-auto px-5 pt-5 pb-28">
        {onClose && stage.k !== "result" && (
          <button
            onClick={onClose}
            className="text-2xl text-ink-soft font-bold leading-none active:opacity-60 mb-2"
          >
            ✕
          </button>
        )}

        {stage.k === "loading" && (
          <div className="min-h-[70vh] flex items-center justify-center text-ink-soft font-semibold">
            Tayyorlanmoqda…
          </div>
        )}

        {stage.k === "error" && (
          <div className="min-h-[70vh] flex flex-col items-center justify-center gap-3 text-center px-6">
            <div className="text-5xl">😕</div>
            <p className="text-sm text-ink-soft font-semibold">
              Testni yuklab bo'lmadi. Internetni tekshirib, qayta urinib ko'ring.
            </p>
          </div>
        )}

        {stage.k === "intro" && (
          <div className="min-h-[70vh] flex flex-col items-center justify-center gap-4 text-center px-4">
            <div className="text-[11px] font-extrabold tracking-[0.16em] text-ink-soft">
              BOSQICH {stage.index}/{stage.count}
            </div>
            <div className="text-6xl">
              {stage.tier === "A0" ? "🔤" : stage.tier === "A1" ? "📖" : stage.tier === "A2" ? "🧩" : stage.tier === "B1" ? "🎓" : "🏆"}
            </div>
            <h1 className="text-2xl font-extrabold">{stage.title}</h1>
            <p className="text-sm text-ink-soft font-semibold max-w-72">
              {stage.items.length} ta savol. To'g'ri javob bersangiz keyingi bosqichga
              o'tasiz — shu tarzda haqiqiy darajangiz aniqlanadi.
            </p>
            <button
              onClick={() => setStage({ ...stage, k: "quiz" })}
              className="w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg mt-2"
            >
              Boshlash
            </button>
          </div>
        )}

        {stage.k === "quiz" && (
          <div className="pt-2">
            <p className="mb-3 text-xs text-ink-soft font-semibold">
              Bosqich {stage.index}/{stage.count} · {stage.title}
            </p>
            <QuizRunner
              items={stage.items}
              label={`DARAJA TESTI · ${stage.tier}`}
              onFinish={(correct, total) => finishTier(stage.tier, correct, total)}
            />
          </div>
        )}

        {stage.k === "result" && (
          <div className="min-h-[70vh] flex flex-col items-center justify-center gap-3 text-center">
            <div className="text-6xl">🎯</div>
            <div className="text-[11px] font-extrabold tracking-[0.16em] text-ink-soft">
              SIZNING DARAJANGIZ
            </div>
            <div className="rounded-3xl bg-emerald-deep px-10 py-5">
              <span className="text-4xl font-extrabold text-white">
                {stage.result.level}
              </span>
            </div>
            <p className="text-sm text-ink-soft font-semibold px-6">
              {stage.result.reason}
            </p>
            <button
              onClick={() => onDone(stage.result)}
              className="w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg mt-3"
            >
              Darslarni boshlash
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
