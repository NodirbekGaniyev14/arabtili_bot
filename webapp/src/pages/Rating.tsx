import { useEffect, useState } from "react";
import { api, type LeaderboardData } from "../lib/api";

const tg = () => window.Telegram?.WebApp;

function inviteFriend() {
  const bot = "JamalArabiy_bot";
  const user = tg()?.initDataUnsafe.user?.id ?? "";
  const link = `https://t.me/${bot}?start=ref${user}`;
  const text = "Men bilan arab tilini o'rganing! 🕌";
  const share = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`;
  if (tg()) {
    (tg() as unknown as { openTelegramLink?: (u: string) => void }).openTelegramLink?.(share);
  } else {
    window.open(share, "_blank");
  }
}

export default function Rating() {
  const [data, setData] = useState<LeaderboardData | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.getLeaderboard().then(setData).catch(() => setError(true));
  }, []);

  if (error) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center text-ink-soft font-semibold px-8 text-center">
        Reytingni yuklashda xatolik.
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

  const league = data.league;

  return (
    <div className="px-4 pt-4 pb-6 space-y-4">
      <h1 className="text-[26px] font-extrabold">Reyting</h1>

      {/* Liga banneri */}
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-emerald-deep to-emerald-dark p-5 text-white text-center shadow-lg">
        <div className="text-5xl">{league.icon}</div>
        <div className="mt-1 font-extrabold text-xl">{league.name} ligasi</div>
        <div className="text-sm text-gold-soft font-semibold">
          Bu hafta {data.my_weekly_xp} XP · {data.my_rank}-o'rin
        </div>

        {/* Liga darajalari chizig'i */}
        <div className="mt-4 flex items-center justify-center gap-2">
          {data.all_leagues.map((lg) => (
            <div
              key={lg.id}
              className={`flex flex-col items-center transition-opacity ${
                lg.id === league.id ? "opacity-100 scale-110" : "opacity-40"
              }`}
            >
              <span className="text-2xl">{lg.icon}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Haftalik izoh */}
      <div className="text-center text-xs text-ink-soft font-semibold">
        Har hafta XP bo'yicha bellashuv · dushanbada yangilanadi
      </div>

      {/* Reyting ro'yxati */}
      <section className="rounded-3xl bg-card border border-cardline overflow-hidden">
        {data.entries.map((e, i) => {
          const medal = e.rank === 1 ? "🥇" : e.rank === 2 ? "🥈" : e.rank === 3 ? "🥉" : null;
          return (
            <div
              key={`${e.rank}-${e.name}-${i}`}
              className={`flex items-center gap-3 px-4 py-3 ${
                i > 0 ? "border-t border-cardline" : ""
              } ${e.is_me ? "bg-emerald-deep/8" : ""}`}
            >
              <div className="w-7 text-center font-extrabold text-ink-soft">
                {medal ?? e.rank}
              </div>
              <div
                className={`w-9 h-9 rounded-full flex items-center justify-center font-extrabold text-white ${
                  e.is_me ? "bg-emerald-deep" : "bg-gold/70"
                }`}
              >
                {e.name.charAt(0).toUpperCase()}
              </div>
              <div className="flex-1 font-bold truncate">
                {e.name}
                {e.is_me && (
                  <span className="ml-1.5 text-xs text-emerald-deep font-extrabold">
                    (Siz)
                  </span>
                )}
              </div>
              <div className="font-extrabold text-emerald-dark">{e.xp} XP</div>
            </div>
          );
        })}
      </section>

      {/* Do'st taklif qilish */}
      <button
        onClick={inviteFriend}
        className="w-full rounded-2xl bg-gold-soft border border-gold/30 py-3.5 font-extrabold text-ink active:scale-[0.98] transition-transform"
      >
        👥 Do'stlarni taklif qilish
      </button>
    </div>
  );
}
