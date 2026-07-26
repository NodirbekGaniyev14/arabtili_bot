import { useEffect, useState } from "react";
import { api, type MyCertificate, type ProfileData } from "../lib/api";
import { isSoundOn, setSoundOn } from "../lib/audio";
import { formatTargetDate, GOALS, DURATIONS } from "./onboarding/data";

const tg = () => window.Telegram?.WebApp;

function StatRow({
  icon,
  label,
  value,
  accent,
}: {
  icon: string;
  label: string;
  value: string | number;
  accent?: "red" | "green";
}) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5">
      <span className="text-sm font-semibold">
        {icon} {label}
      </span>
      <span
        className={`text-sm font-extrabold ${
          accent === "red"
            ? "text-terracotta"
            : accent === "green"
              ? "text-emerald-deep"
              : ""
        }`}
      >
        {value}
      </span>
    </div>
  );
}

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

export default function Profile({
  onOpenPlacement,
}: {
  onOpenPlacement?: () => void;
} = {}) {
  const [data, setData] = useState<ProfileData | null>(null);
  const [error, setError] = useState(false);
  const [savingGoal, setSavingGoal] = useState(false);
  const [sound, setSound] = useState(isSoundOn());
  const [resetting, setResetting] = useState(false);
  const [fb, setFb] = useState("");
  const [fbState, setFbState] = useState<"idle" | "sending" | "sent">("idle");

  const sendFeedback = async () => {
    const text = fb.trim();
    if (!text || fbState === "sending") return;
    setFbState("sending");
    try {
      await api.submitFeedback(text, "profil");
      setFbState("sent");
      setFb("");
      tg()?.HapticFeedback?.notificationOccurred?.("success");
    } catch {
      setFbState("idle");
    }
  };

  const toggleSound = () => {
    const next = !sound;
    setSound(next);
    setSoundOn(next);
    tg()?.HapticFeedback?.impactOccurred("light");
  };

  const resetPlan = async () => {
    const doReset = async () => {
      setResetting(true);
      try {
        await api.resetPlan();
        window.location.reload(); // onboarding qayta ochiladi
      } catch {
        setResetting(false);
      }
    };
    const t = tg() as unknown as {
      showConfirm?: (msg: string, cb: (ok: boolean) => void) => void;
    };
    const msg =
      "Rejani tozalab, onboardingdan qayta o'tasiz. XP, streak va o'rganilgan so'zlar saqlanadi. Davom etasizmi?";
    if (t?.showConfirm) t.showConfirm(msg, (ok) => ok && doReset());
    else if (window.confirm(msg)) doReset();
  };

  const [certs, setCerts] = useState<MyCertificate[]>([]);

  useEffect(() => {
    api.getProfile().then(setData).catch(() => setError(true));
    api
      .getMyCertificates()
      .then((r) => setCerts(r.certificates))
      .catch(() => {});
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

      {/* Sertifikatlar */}
      {certs.length > 0 && (
        <section>
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2.5">
            SERTIFIKATLARIM
          </div>
          <div className="flex gap-3 overflow-x-auto pb-1 -mx-4 px-4">
            {certs.map((c) => {
              const weekly = c.kind === "weekly";
              const rank = weekly ? c.level.replace("W", "") : "";
              return (
                <a
                  key={c.cert_id}
                  href={c.png_url}
                  target="_blank"
                  rel="noreferrer"
                  className="shrink-0 w-40 rounded-2xl bg-card border border-gold/40 p-3 text-center active:scale-[0.98] transition-transform"
                >
                  <div className="text-3xl">
                    {weekly ? (rank === "1" ? "🥇" : rank === "2" ? "🥈" : "🥉") : "🎓"}
                  </div>
                  <div className="mt-1 text-sm font-extrabold leading-tight">
                    {weekly ? `Haftalik ${rank}-o'rin` : `${c.level} kursi`}
                  </div>
                  <div className="text-[11px] text-ink-soft font-semibold">
                    {weekly ? `${c.score} XP` : `${c.score}/100`} · {c.issued_at}
                  </div>
                </a>
              );
            })}
          </div>
        </section>
      )}

      {/* STATISTIKA (Hanyu uslubi) */}
      <section>
        <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2.5">
          STATISTIKA
        </div>
        <div className="rounded-2xl bg-card border border-cardline divide-y divide-cardline">
          <StatRow icon="✅" label="Imtihondan o'tildi" value={`${data.exams_passed} marta`} />
          <StatRow icon="🎯" label="Eng yaxshi imtihon" value={`${data.best_exam}/100`} />
          <StatRow icon="🃏" label="Takror kartalari" value={`${data.cards_total} ta`} />
          <StatRow icon="📊" label="Umumiy aniqlik" value={`${data.stats.accuracy}%`} accent="green" />
          <StatRow
            icon="❗"
            label="Joriy xatolar"
            value={`${data.mistakes_now} ta`}
            accent={data.mistakes_now > 0 ? "red" : undefined}
          />
        </div>
      </section>

      {/* REJAM */}
      <section>
        <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2.5">
          REJAM
        </div>
        <div className="rounded-2xl bg-card border border-cardline divide-y divide-cardline">
          <StatRow icon="📍" label="Hozirgi daraja" value={data.level} />
          <StatRow icon="🏔" label="Maqsad" value={data.target_level || "—"} />
          <StatRow
            icon="📅"
            label="Muddat"
            value={data.target_date ? `${formatTargetDate(data.target_date)} gacha` : "—"}
          />
          <StatRow
            icon="💬"
            label="Sabab"
            value={GOALS.find((g) => g.id === data.goal)?.label || DURATIONS.find((d) => d.id === data.goal)?.label || data.goal || "—"}
          />
        </div>
      </section>

      {/* Sozlamalar — ovoz */}
      <section>
        <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2.5">
          SOZLAMALAR
        </div>
        <button
          onClick={toggleSound}
          className="w-full flex items-center justify-between rounded-2xl bg-card border border-cardline px-4 py-3.5 active:scale-[0.99] transition-transform"
        >
          <span className="text-sm font-semibold">🔊 Ovoz (talaffuz)</span>
          <span
            className={`rounded-full px-3.5 py-1 text-xs font-extrabold ${
              sound
                ? "bg-emerald-deep/10 text-emerald-deep border border-emerald-deep/40"
                : "bg-cardline text-ink-soft"
            }`}
          >
            {sound ? "Yoniq" : "O'chiq"}
          </span>
        </button>
      </section>

      {/* Kunlik maqsad */}
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

      {/* Fikr bildirish */}
      <section className="rounded-3xl bg-card border border-cardline p-4 space-y-3">
        <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
          FIKR BILDIRISH
        </div>
        {fbState === "sent" ? (
          <div className="text-center py-3">
            <div className="text-3xl mb-1">🌟</div>
            <p className="font-extrabold text-emerald-dark">Rahmat!</p>
            <p className="text-xs text-ink-soft font-semibold">
              Fikringiz qabul qilindi
            </p>
            <button
              onClick={() => setFbState("idle")}
              className="mt-2 text-xs font-bold text-emerald-dark underline"
            >
              Yana yozish
            </button>
          </div>
        ) : (
          <>
            <p className="text-xs text-ink-soft font-semibold">
              Taklif, xato yoki nima yoqqani — hammasi botni yaxshilashga yordam
              beradi.
            </p>
            <textarea
              value={fb}
              onChange={(e) => setFb(e.target.value.slice(0, 2000))}
              placeholder="Fikringizni shu yerga yozing..."
              rows={3}
              className="w-full rounded-xl bg-sand/60 border border-cardline px-3 py-2.5 text-sm font-semibold resize-none outline-none focus:border-emerald-deep/40"
            />
            <button
              onClick={sendFeedback}
              disabled={!fb.trim() || fbState === "sending"}
              className="w-full rounded-xl bg-emerald-deep py-3 text-white font-extrabold active:scale-[0.98] transition-transform disabled:opacity-40"
            >
              {fbState === "sending" ? "Yuborilmoqda..." : "✉️ Yuborish"}
            </button>
          </>
        )}
      </section>

      {/* Darajani qayta aniqlash — IXTIYORIY */}
      {onOpenPlacement && (
        <>
          <button
            onClick={onOpenPlacement}
            className="w-full rounded-2xl border-2 border-emerald-deep/40 bg-emerald-deep/8 py-3.5 font-extrabold text-emerald-deep active:scale-[0.98] transition-transform"
          >
            🎯 Darajani qayta aniqlash
          </button>
          <p className="text-center text-[11px] text-ink-soft font-semibold -mt-2">
            Qisqa test · darslaringiz va XP saqlanadi
          </p>
        </>
      )}

      {/* Rejani tozalash */}
      <button
        onClick={resetPlan}
        disabled={resetting}
        className="w-full rounded-2xl border-2 border-terracotta/50 bg-terracotta/8 py-3.5 font-extrabold text-terracotta active:scale-[0.98] transition-transform disabled:opacity-50"
      >
        {resetting ? "Tozalanmoqda..." : "🗑 Rejani tozalash"}
      </button>
      <p className="text-center text-[11px] text-ink-soft font-semibold -mt-2">
        Onboardingdan qayta o'tasiz · XP va so'zlaringiz saqlanadi
      </p>

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
