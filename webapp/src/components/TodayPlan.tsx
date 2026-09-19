import { useEffect, useRef, useState } from "react";
import XPRing from "./XPRing";
import type { Stats } from "../lib/api";

/** Bosh sahifa «Bugun» kartasi (K19.1): kunlik XP halqasi + 4 vazifa ro'yxati.
 *
 *  Vazifalar HAQIQIY faollikdan belgilanadi (stats.today — XpLog/UserWord bugun):
 *  keyingi dars, takrorlash, kunlik speaking savoli, yangi so'zlar. Har qator
 *  o'z bo'limini ochadi; pastdagi tugma — birinchi bajarilmagan vazifa.
 *  Kirishda (kuniga bir marta, bugun hech narsa qilinmagan bo'lsa) yumshoq
 *  eslatma chiqadi — «Vazifalar» tugmasi shu kartaga olib keladi. */

const tg = () => window.Telegram?.WebApp;

export interface TodayActions {
  onStartLesson: () => void;
  onGoReview: () => void;
  onOpenDaily?: () => void;
  onOpenVocab: () => void;
  onOpenWriting?: () => void;
}

export interface WritingTodo {
  title: string;
  kind: string;
  done: boolean;
  score: number;
}

interface Task {
  id: "lesson" | "review" | "daily" | "words" | "writing";
  icon: string;
  title: string;
  hint: string;
  done: boolean;
  go: () => void;
}

export function buildTasks(stats: Stats, dailyDone: boolean, a: TodayActions, writing?: WritingTodo): Task[] {
  const t = stats.today;
  const next = stats.next_lesson;
  const words = t?.new_words ?? 0;
  const goal = t?.new_words_goal ?? 5;
  const tasks: Task[] = [
    {
      id: "lesson",
      icon: "📖",
      title: next ? `Dars: ${next.title}` : "Barcha darslar tugatilgan",
      hint: next ? `${next.module_title} · ${next.pos}/${next.count}` : "yangi modullar tez orada",
      done: !!t?.lesson_done || !next,
      go: a.onStartLesson,
    },
    {
      id: "review",
      icon: "🔁",
      title: stats.due_count > 0 ? `Takrorlash: ${stats.due_count} ta karta` : "Takrorlash",
      hint: stats.due_count > 0 ? "SRS — unutishdan oldin" : "bugungi kartalar tugadi",
      done: !!t?.review_done,
      go: a.onGoReview,
    },
    {
      id: "daily",
      icon: "🎙",
      title: "Kunlik speaking savoli",
      hint: "1 daqiqa · ovozli javob · bepul",
      done: dailyDone,
      go: a.onOpenDaily ?? a.onGoReview,
    },
    {
      id: "words",
      icon: "🆕",
      title: `Yangi so'zlar: ${Math.min(words, goal)}/${goal}`,
      hint: words >= goal ? "bugungi me'yor bajarildi" : "lug'at bo'limi yoki darsdan",
      done: words >= goal,
      go: a.onOpenVocab,
    },
  ];
  if (writing && a.onOpenWriting) {
    tasks.push({
      id: "writing",
      icon: "✍️",
      title: `Yozuv: ${writing.title}`,
      hint: writing.done ? `tekshirildi · ${writing.score}%` : "qog'ozga yozing, suratga oling — 2 kunda bir",
      done: writing.done,
      go: a.onOpenWriting,
    });
  }
  return tasks;
}

const NUDGE_KEY = "arabiy_nudge_day";

export default function TodayPlan({
  stats,
  xpGoal,
  dailyDone,
  actions,
  writing,
}: {
  stats: Stats;
  xpGoal: number;
  dailyDone: boolean;
  actions: TodayActions;
  writing?: WritingTodo;
}) {
  const tasks = buildTasks(stats, dailyDone, actions, writing);
  const done = tasks.filter((t) => t.done).length;
  const first = tasks.find((t) => !t.done);
  const cardRef = useRef<HTMLElement>(null);

  // Kirish eslatmasi: bugun XP yo'q va bugun hali ko'rsatilmagan
  const today = new Date().toISOString().slice(0, 10);
  const [nudge, setNudge] = useState(() => {
    if (stats.xp_today > 0) return false;
    try {
      return localStorage.getItem(NUDGE_KEY) !== today;
    } catch {
      return true;
    }
  });
  useEffect(() => {
    if (stats.xp_today > 0 && nudge) setNudge(false);
  }, [stats.xp_today, nudge]);

  const dismiss = () => {
    setNudge(false);
    try {
      localStorage.setItem(NUDGE_KEY, today);
    } catch {
      /* jim */
    }
  };
  const toTasks = () => {
    dismiss();
    tg()?.HapticFeedback?.impactOccurred("light");
    cardRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <>
      {nudge && (
        <div className="flex items-center gap-3 rounded-2xl bg-gold-soft border border-gold/40 px-4 py-3">
          <div className="text-2xl">👋</div>
          <div className="min-w-0 flex-1">
            <div className="text-[13px] font-extrabold leading-tight">Bugun hali boshlamadingiz</div>
            <div className="text-[11px] text-ink-soft font-semibold">
              Yangi narsa o'rganing — 10 daqiqa yetadi, streak saqlanadi 🔥
            </div>
          </div>
          <button
            onClick={toTasks}
            className="shrink-0 rounded-xl bg-emerald-deep px-3 py-2 text-[12px] font-extrabold text-white active:scale-95 transition-transform"
          >
            Vazifalar ↓
          </button>
          <button onClick={dismiss} aria-label="Yopish" className="shrink-0 text-ink-soft font-extrabold px-1">
            ✕
          </button>
        </div>
      )}

      <section ref={cardRef} className="rounded-3xl bg-card border border-cardline p-4 shadow-sm">
        <div className="flex items-center gap-4">
          <XPRing value={stats.xp_today} goal={xpGoal} size={76} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between">
              <div className="text-base font-extrabold">Bugun</div>
              <span
                className={`rounded-full px-2.5 py-0.5 text-[11px] font-extrabold ${
                  done === tasks.length ? "bg-gold-soft text-ink" : "bg-emerald-deep/10 text-emerald-dark"
                }`}
              >
                {done}/{tasks.length}
              </span>
            </div>
            <div className="text-[12px] text-ink-soft font-semibold">
              {done === tasks.length
                ? "Hammasi bajarildi — zo'r! 🌟"
                : stats.xp_today >= xpGoal
                  ? "XP maqsadi bajarildi, ro'yxatni yakunlang"
                  : `Maqsadga ${Math.max(xpGoal - stats.xp_today, 0)} XP qoldi`}
            </div>
          </div>
        </div>

        <ul className="mt-3 divide-y divide-cardline">
          {tasks.map((t) => (
            <li key={t.id}>
              <button
                onClick={() => {
                  tg()?.HapticFeedback?.impactOccurred("light");
                  t.go();
                }}
                className="w-full flex items-center gap-3 py-2.5 text-left active:opacity-70"
              >
                <span
                  className={`w-6 h-6 shrink-0 rounded-full border-2 flex items-center justify-center text-[12px] font-extrabold ${
                    t.done ? "bg-emerald-deep border-emerald-deep text-white" : "border-cardline text-transparent"
                  }`}
                  aria-hidden
                >
                  ✓
                </span>
                <span className="text-lg" aria-hidden>
                  {t.icon}
                </span>
                <span className="min-w-0 flex-1">
                  <span
                    className={`block text-[13px] font-extrabold leading-tight truncate ${
                      t.done ? "text-ink-soft line-through decoration-ink-soft/50" : ""
                    }`}
                  >
                    {t.title}
                  </span>
                  <span className="block text-[11px] text-ink-soft font-semibold">{t.hint}</span>
                </span>
                <span className="text-ink-soft font-extrabold">›</span>
              </button>
            </li>
          ))}
        </ul>

        {first && (
          <button
            onClick={() => {
              tg()?.HapticFeedback?.impactOccurred("medium");
              first.go();
            }}
            className="mt-2 w-full rounded-xl bg-emerald-deep py-3 text-sm font-extrabold text-white active:scale-[0.98] transition-transform"
          >
            {first.icon} Boshlash: {first.title.split(":")[0]} ›
          </button>
        )}
      </section>
    </>
  );
}
