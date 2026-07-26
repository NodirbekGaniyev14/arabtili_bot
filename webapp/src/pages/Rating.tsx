/** Reyting — Haftalik / Oylik / Hammasi yorliqlari, top-3 podium, daraja belgisi. */

import { useEffect, useState } from "react";
import {
  api,
  type LeaderboardData,
  type LeaderboardEntry,
  type LeaderPeriod,
} from "../lib/api";

const tg = () => window.Telegram?.WebApp;

const PERIODS: { id: LeaderPeriod; label: string }[] = [
  { id: "week", label: "Haftalik" },
  { id: "month", label: "Oylik" },
  { id: "all", label: "Hammasi" },
];

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

/** Ism ostidagi kichik belgi: daraja + streak — ismga nisbatan ochroq */
function LevelTag({ level, streak }: { level: string; streak: number }) {
  return (
    <span className="text-[11px] font-bold text-ink-soft/70">
      {level} daraja
      {streak > 0 && <> · 🔥 {streak} kun</>}
    </span>
  );
}

/** Top-3 poydevor: 1-o'rin o'rtada baland */
function Podium({ top }: { top: LeaderboardEntry[] }) {
  const byRank = (r: number) => top.find((e) => e.rank === r);
  const slots: { entry?: LeaderboardEntry; h: string; medal: string; bar: string }[] = [
    { entry: byRank(2), h: "h-20", medal: "🥈", bar: "bg-gradient-to-b from-fuchsia-500 to-purple-600" },
    { entry: byRank(1), h: "h-28", medal: "🥇", bar: "bg-gradient-to-b from-orange-400 to-red-500" },
    { entry: byRank(3), h: "h-14", medal: "🥉", bar: "bg-gradient-to-b from-sky-400 to-blue-600" },
  ];

  return (
    <div className="grid grid-cols-3 gap-2 items-end">
      {slots.map((s, i) => (
        <div key={i} className="flex flex-col items-center">
          {s.entry ? (
            <>
              <div className="relative">
                <div
                  className={`w-14 h-14 rounded-full flex items-center justify-center font-extrabold text-white text-lg ${
                    s.entry.is_me ? "bg-emerald-deep" : "bg-gold/70"
                  }`}
                >
                  {s.entry.name.charAt(0).toUpperCase()}
                </div>
                <span className="absolute -bottom-1 -right-1 text-lg">{s.medal}</span>
              </div>
              <div className="mt-1.5 text-xs font-extrabold truncate max-w-full px-1">
                {s.entry.name.split(" ")[0]}
              </div>
              <div className="text-[10px] font-bold text-ink-soft/70">
                {s.entry.level}
                {s.entry.streak > 0 && ` · 🔥${s.entry.streak}`}
              </div>
              <div className="text-xs font-extrabold text-emerald-dark">
                {s.entry.xp} XP
              </div>
            </>
          ) : (
            <div className="text-xs text-ink-soft font-semibold pb-2">—</div>
          )}
          <div className={`w-full ${s.h} mt-2 rounded-t-xl ${s.bar}`} />
        </div>
      ))}
    </div>
  );
}

export default function Rating() {
  const [period, setPeriod] = useState<LeaderPeriod>("week");
  const [data, setData] = useState<LeaderboardData | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    setData(null);
    api.getLeaderboard(period).then(setData).catch(() => setError(true));
  }, [period]);

  if (error) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center text-ink-soft font-semibold px-8 text-center">
        Reytingni yuklashda xatolik.
      </div>
    );
  }

  const league = data?.league;
  const top3 = (data?.entries ?? []).filter((e) => e.rank <= 3);
  const rest = (data?.entries ?? []).filter((e) => e.rank > 3);

  return (
    <div className="px-4 pt-4 pb-6 space-y-4">
      <h1 className="text-[26px] font-extrabold">Reyting</h1>

      {/* Davr yorliqlari */}
      <div className="grid grid-cols-3 gap-1 rounded-2xl bg-card border border-cardline p-1">
        {PERIODS.map((p) => (
          <button
            key={p.id}
            onClick={() => setPeriod(p.id)}
            className={`rounded-xl py-2.5 text-sm font-extrabold transition-colors ${
              period === p.id
                ? "bg-emerald-deep text-white"
                : "text-ink-soft active:bg-sand"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      {!data ? (
        <div className="min-h-[40vh] flex items-center justify-center">
          <div className="w-10 h-10 rounded-xl bg-emerald-deep animate-pulse" />
        </div>
      ) : (
        <>
          {/* Liga banneri — liga har doim HAFTALIK XP bo'yicha */}
          {league && (
            <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-emerald-deep to-emerald-dark p-5 text-white text-center shadow-lg">
              <div className="text-5xl">{league.icon}</div>
              <div className="mt-1 font-extrabold text-xl">{league.name} ligasi</div>
              <div className="text-sm text-gold-soft font-semibold">
                {period === "week"
                  ? `Bu hafta ${data.my_period_xp} XP`
                  : period === "month"
                    ? `Bu oy ${data.my_period_xp} XP`
                    : `Jami ${data.my_period_xp} XP`}{" "}
                · {data.my_rank}-o'rin
              </div>

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

              {/* Ligadagi o'rin va zona */}
              <div className="mt-3 rounded-2xl bg-white/10 px-3 py-2 text-[13px] font-semibold">
                Ligada: <b>{data.league_rank}</b> / {data.league_size}
                {data.promote_zone && data.next_league && (
                  <div className="mt-1 text-gold-soft font-extrabold">
                    ⬆ Ko'tarilish zonasi — {data.next_league.name} ligasiga
                    chiqyapsiz!
                  </div>
                )}
                {data.relegate_zone && (
                  <div className="mt-1 text-white/90 font-extrabold">
                    ⬇ Tushish zonasi — bu hafta XP to'plang!
                  </div>
                )}
                {!data.promote_zone && !data.relegate_zone && (
                  <div className="mt-1 text-white/70">
                    {data.next_league
                      ? `Top-${data.promote_top} ga kirsangiz ${data.next_league.name} ligasiga ko'tarilasiz`
                      : "Eng yuqori ligadasiz — ushlab turing!"}
                  </div>
                )}
              </div>
            </section>
          )}

          {/* Top-3 podium */}
          {top3.length > 0 && (
            <section className="rounded-3xl bg-card border border-cardline p-4">
              <Podium top={top3} />
            </section>
          )}

          {/* Qolgan ro'yxat */}
          {rest.length > 0 && (
            <section className="rounded-3xl bg-card border border-cardline overflow-hidden">
              {rest.map((e, i) => (
                <div
                  key={`${e.rank}-${e.name}-${i}`}
                  className={`flex items-center gap-3 px-4 py-3 ${
                    i > 0 ? "border-t border-cardline" : ""
                  } ${e.is_me ? "bg-emerald-deep/8" : ""}`}
                >
                  <div className="w-7 text-center font-extrabold text-ink-soft">
                    {e.rank}
                  </div>
                  <div
                    className={`w-9 h-9 rounded-full flex items-center justify-center font-extrabold text-white ${
                      e.is_me ? "bg-emerald-deep" : "bg-gold/70"
                    }`}
                  >
                    {e.name.charAt(0).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-bold truncate">
                      {e.name}
                      {e.is_me && (
                        <span className="ml-1.5 text-xs text-emerald-deep font-extrabold">
                          (Siz)
                        </span>
                      )}
                    </div>
                    <LevelTag level={e.level} streak={e.streak} />
                  </div>
                  <div className="font-extrabold text-emerald-dark">{e.xp} XP</div>
                </div>
              ))}
            </section>
          )}

          {data.entries.length === 0 && (
            <div className="rounded-3xl bg-card border border-cardline border-dashed p-8 text-center space-y-2">
              <div className="text-4xl">🏅</div>
              <p className="text-sm text-ink-soft font-semibold">
                Bu davrda hali XP yig'ilmagan. Dars tugating — reytingda birinchi
                bo'ling!
              </p>
            </div>
          )}

          {period === "week" && (
            <div className="rounded-2xl bg-gold-soft/60 border border-gold/30 px-4 py-3 text-center">
              <p className="text-sm font-extrabold">🏆 Haftalik sovrin</p>
              <p className="mt-0.5 text-xs font-semibold text-ink-soft leading-relaxed">
                Dushanba tongida hafta yakunlanadi — <b>1, 2 va 3-o'rin</b> egalariga
                sertifikat botga yuboriladi va profilda saqlanadi.
              </p>
            </div>
          )}
        </>
      )}

      <button
        onClick={inviteFriend}
        className="w-full rounded-2xl bg-gold-soft border border-gold/30 py-3.5 font-extrabold text-ink active:scale-[0.98] transition-transform"
      >
        👥 Do'stlarni taklif qilish
      </button>
    </div>
  );
}
