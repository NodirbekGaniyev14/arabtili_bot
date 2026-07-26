/** Haftalik chellenj — har dushanba yangilanadigan aralash test.
 *
 * Savollar foydalanuvchi TUGATGAN darslardan yig'iladi. ≥80% da bir marta
 * XP beriladi (o'sha hafta uchun).
 */

import { useEffect, useState } from "react";
import { api, type ChallengeData, type ChallengeResult } from "../lib/api";
import { QuizRunner } from "./v2/exercises";

export default function Challenge({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<ChallengeData | null>(null);
  const [result, setResult] = useState<ChallengeResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .startChallenge()
      .then(setData)
      .catch(() =>
        setError(
          "Chellenj uchun avval kamida bitta darsni tugating — savollar shu darslardan tuziladi."
        )
      );
  }, []);

  const finish = (correct: number, total: number, wrong: string[]) => {
    if (!data) return;
    api
      .submitChallenge({
        attempt_id: data.attempt_id,
        correct,
        total,
        wrong_words: wrong,
      })
      .then(setResult)
      .catch(() => setError("Natijani yuborib bo'lmadi"));
  };

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
          <div className="font-extrabold">🔥 Haftalik chellenj</div>
        </div>

        {error && (
          <div className="min-h-[60vh] flex flex-col items-center justify-center gap-3 text-center px-6">
            <div className="text-5xl">🔥</div>
            <p className="text-sm text-ink-soft font-semibold">{error}</p>
            <button
              onClick={onClose}
              className="w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold"
            >
              Yopish
            </button>
          </div>
        )}

        {!error && !data && (
          <div className="min-h-[60vh] flex items-center justify-center text-ink-soft font-semibold">
            Bu haftaning savollari tayyorlanmoqda…
          </div>
        )}

        {data && !result && (
          <div className="pt-2">
            <p className="mb-3 text-xs text-ink-soft font-semibold">
              {data.week_label} haftasi · {data.lessons_pool} ta o'tilgan darsdan ·{" "}
              {data.pass_score}% da +{data.xp_reward} XP
            </p>
            <QuizRunner
              items={data.items}
              label="HAFTALIK CHELLENJ"
              onFinish={finish}
            />
          </div>
        )}

        {result && (
          <div className="min-h-[60vh] flex flex-col items-center justify-center gap-3 text-center">
            <div className="text-6xl">{result.passed ? "🔥" : "💪"}</div>
            <h1 className="text-2xl font-extrabold">
              {result.passed ? "Chellenj bajarildi!" : "Bu safar bo'lmadi"}
            </h1>
            <div
              className={`rounded-2xl px-8 py-4 border ${
                result.passed
                  ? "bg-gold-soft border-gold/30"
                  : "bg-card border-cardline"
              }`}
            >
              <span
                className={`text-3xl font-extrabold ${
                  result.passed ? "text-emerald-dark" : "text-ink"
                }`}
              >
                {result.score}%
              </span>
            </div>
            <p className="text-ink-soft font-semibold">
              {result.correct}/{result.total} to'g'ri
            </p>

            {result.xp_earned > 0 && (
              <p className="text-sm font-extrabold text-emerald-deep">
                +{result.xp_earned} XP
              </p>
            )}
            {result.passed && result.xp_already_claimed && (
              <p className="text-xs text-ink-soft font-semibold">
                Bu hafta XP allaqachon olingan — keyingi dushanba yangi chellenj.
              </p>
            )}

            <p className="text-xs text-ink-soft font-semibold px-8">
              {result.passed
                ? "Keyingi dushanba yangi savollar bilan qaytadi!"
                : "Xato so'zlar takrorga qaytarildi. Yana urinib ko'ring — urinishlar cheklanmagan."}
            </p>

            <button
              onClick={onClose}
              className="w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg mt-2"
            >
              Yakunlash
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
