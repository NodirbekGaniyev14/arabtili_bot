import { useEffect, useState } from "react";
import { api, type ProfileData } from "../lib/api";
import { formatTargetDate } from "./onboarding/data";

const tg = () => window.Telegram?.WebApp;

const GOAL_OPTIONS = [
  { minutes: 10, label: "10 daqiqa", xp: 20 },
  { minutes: 20, label: "20 daqiqa", xp: 30 },
  { minutes: 30, label: "30 daqiqa", xp: 50 },
  { minutes: 60, label: "1 soat", xp: 80 },
];

function StatCard({
  value,
  label,
  icon,
}: {
  value: string | number;
  label: string;
  icon: string;
}) {
  return (
    <div className="rounded-2xl bg-card border border-cardline p-3.5 text-center">
      <div className="text-2xl">{icon}</div>
      <div className="mt-1 text-xl font-extrabold">{value}</div>
      <div className="text-xs text-ink-soft font-semibold">{label}</div>
    </div>
  );
}

export default function Profile() {
  const [data, setData] = useState<ProfileData | null>(null);
  const [error, setError] = useState(false);
  const [savingGoal, setSavingGoal] = useState(false);

  useEffect(() => {
    api.getProfile().then(setData).catch(() => setError(true));
  }, []);

  const photo = tg()?.initDataUnsafe.user?.photo_url;

  const changeGoal = async (minutes: number) => {
    if (!data || savingGoal || minutes === data.daily_minutes) return;
    setSavingGoal(true);
    tg()?.HapticFeedback?.impactOccurred("light");
    try {
      const res = await api.updateGoal(minutes);
      setData({
        ...data,
        daily_minutes: res.daily_minutes,
        daily_xp_goal: res.daily_xp_goal,
      });
    } catch {
      /* jimgina */
    } finally {
      setSavingGoal(false);
    }
  };

  if (error) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center text-ink-soft font-semibold px-8 text-center">
        Profilni yuklashda xatolik.
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

  const ach = data.achievements;

  return (
    <div className="px-4 pt-4 pb-6 space-y-5">
      {/* Avatar + ism + daraja muhri */}
      <section className="flex flex-col items-center text-center gap-2">
        <div className="relative">
          {photo ? (
            <img
              src={photo}
              alt=""
              className="w-24 h-24 rounded-full object-cover border-4 border-card shadow-md"
            />
          ) : (
            <div className="w-24 h-24 rounded-full bg-emerald-deep flex items-center justify-center text-4xl font-extrabold text-white border-4 border-card shadow-md">
              {(data.name || "?").charAt(0).toUpperCase()}
            </div>
          )}
          <div className="absolute -bottom-1 -right-1 w-10 h-10 rounded-xl -rotate-6 bg-gradient-to-br from-emerald-deep to-emerald-dark flex items-center justify-center text-white font-extrabold text-sm shadow border-2 border-sand">
            {data.level}
          </div>
        </div>
        <h1 className="text-2xl font-extrabold mt-2">{data.name || "Foydalanuvchi"}</h1>
        {data.target_level && (
          <p className="text-sm text-ink-soft font-semibold">
            Maqsad: {formatTargetDate(data.target_date)} gacha {data.target_level}
          </p>
        )}
      </section>

      {/* Statistika */}
      <section className="grid grid-cols-2 gap-3">
        <StatCard icon="💎" value={data.total_xp} label="jami XP" />
        <StatCard icon="🔥" value={`${data.longest_streak} kun`} label="eng uzun streak" />
        <StatCard icon="📖" value={data.stats.words} label="so'z o'rganildi" />
        <StatCard icon="📚" value={data.stats.lessons} label="dars tugatildi" />
      </section>

      {/* Yutuqlar */}
      <section>
        <div className="flex items-center justify-between mb-2.5">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
            YUTUQLAR
          </div>
          <div className="text-xs font-extrabold text-emerald-deep">
            {ach.earned_count}/{ach.total}
          </div>
        </div>
        <div className="grid grid-cols-4 gap-2.5">
          {ach.badges.map((b) => (
            <div
              key={b.id}
              className={`aspect-square rounded-2xl flex flex-col items-center justify-center gap-0.5 p-1 text-center transition-all ${
                b.earned
                  ? "bg-gold-soft border border-gold/40"
                  : "bg-card border border-cardline opacity-40 grayscale"
              }`}
              title={`${b.title} — ${b.desc}`}
            >
              <span className="text-2xl leading-none">
                {b.earned ? b.icon : "🔒"}
              </span>
              <span className="text-[8px] font-bold leading-tight line-clamp-2">
                {b.title}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* Sozlamalar — kunlik maqsad */}
      <section>
        <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2.5">
          KUNLIK MAQSAD
        </div>
        <div className="grid grid-cols-2 gap-2.5">
          {GOAL_OPTIONS.map((g) => {
            const active = g.minutes === data.daily_minutes;
            return (
              <button
                key={g.minutes}
                disabled={savingGoal}
                onClick={() => changeGoal(g.minutes)}
                className={`rounded-2xl border p-3 text-left transition-all active:scale-[0.98] ${
                  active
                    ? "bg-emerald-deep/8 border-emerald-deep"
                    : "bg-card border-cardline"
                }`}
              >
                <div className="font-extrabold text-[15px]">{g.label}</div>
                <div className="text-xs text-ink-soft font-semibold">
                  Kuniga {g.xp} XP
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* Meta */}
      {data.member_since && (
        <p className="text-center text-xs text-ink-soft font-semibold pt-1">
          A'zo bo'lgan sana: {data.member_since}
        </p>
      )}

      <p className="text-center text-[11px] text-ink-soft/70 font-semibold">
        Arabiy · arab tilini bepul o'rganing 🕌
      </p>
    </div>
  );
}
