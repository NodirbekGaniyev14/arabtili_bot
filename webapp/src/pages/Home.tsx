import Header from "../components/Header";
import XPRing from "../components/XPRing";
import type { Stats } from "../lib/api";

interface HomeProps {
  name: string;
  xpGoal: number;
  stats: Stats;
  onStartLesson: (lessonId: string) => void;
  onGoReview: () => void;
}

const MODES: Array<{ ar: string; label: string; desc: string }> = [
  { ar: "حروف", label: "Alifbo mashqi", desc: "Harflar" },
  { ar: "استمع", label: "Tinglash", desc: "Talaffuz" },
  { ar: "بطاقات", label: "Lug'at kartalari", desc: "So'zlar" },
  { ar: "تكرار", label: "Tez takror", desc: "5 daqiqa" },
];

function greeting(): string {
  const h = new Date().getHours();
  if (h >= 5 && h < 11) return "Xayrli tong";
  if (h >= 11 && h < 17) return "Xayrli kun";
  if (h >= 17 && h < 22) return "Xayrli kech";
  return "Xayrli tun";
}

export default function Home({
  name,
  xpGoal,
  stats,
  onStartLesson,
  onGoReview,
}: HomeProps) {
  const next = stats.next_lesson;
  const remaining = Math.max(xpGoal - stats.xp_today, 0);

  return (
    <div className="px-4 pt-4 space-y-4">
      <Header streak={stats.streak} />

      <h1 className="text-[26px] font-extrabold leading-tight pt-1">
        {greeting()}
        {name ? `, ${name}` : ""}!
      </h1>

      {/* Bugungi maqsad */}
      <section className="flex items-center gap-4 rounded-3xl bg-card border border-cardline p-4 shadow-sm">
        <XPRing value={stats.xp_today} goal={xpGoal} />
        <div>
          <div className="text-base font-extrabold">Bugungi maqsad</div>
          <div className="text-sm text-ink-soft font-semibold">
            {remaining > 0
              ? `Bugun ${remaining} XP qoldi`
              : "Maqsad bajarildi! 🌟"}
          </div>
        </div>
      </section>

      {/* Statistika */}
      <section className="grid grid-cols-3 gap-3">
        {[
          { value: String(stats.words), label: "so'z" },
          { value: String(stats.lessons), label: "dars" },
          { value: `${stats.accuracy}%`, label: "aniqlik" },
        ].map((s) => (
          <div
            key={s.label}
            className="rounded-2xl bg-card border border-cardline py-3 text-center"
          >
            <div className="text-xl font-extrabold">{s.value}</div>
            <div className="text-xs text-ink-soft font-semibold">{s.label}</div>
          </div>
        ))}
      </section>

      {/* Takrorlash vaqti */}
      {stats.due_count > 0 && (
        <button
          onClick={onGoReview}
          className="w-full flex items-center justify-between rounded-2xl bg-gold-soft border border-gold/30 px-4 py-3.5 active:scale-[0.98] transition-transform"
        >
          <span className="font-bold text-[15px]">
            🔁 Takrorlash vaqti: {stats.due_count} ta karta
          </span>
          <span className="text-emerald-dark font-extrabold text-xl leading-none">
            ›
          </span>
        </button>
      )}

      {/* Keyingi dars */}
      {next ? (
        <section className="pulse-ring relative overflow-hidden rounded-3xl bg-gradient-to-br from-emerald-deep to-emerald-dark p-5 text-white shadow-lg">
          <span
            className="absolute -right-3 -bottom-8 font-arabic text-[110px] leading-none text-white/15 select-none pointer-events-none"
            aria-hidden
          >
            {next.module_ar || "سَلام"}
          </span>
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-gold-soft">
            KEYINGI DARS · {next.pos}/{next.count} · {next.module_title.toUpperCase()}
          </div>
          <div className="mt-1 font-arabic text-[32px] leading-tight">
            {next.title}
          </div>
          <button
            onClick={() => onStartLesson(next.id)}
            className="mt-4 rounded-xl bg-white px-5 py-2.5 text-sm font-extrabold text-emerald-deep active:scale-95 transition-transform"
          >
            Boshlash ›
          </button>
        </section>
      ) : (
        <section className="rounded-3xl bg-gradient-to-br from-gold to-terracotta p-5 text-white shadow-lg text-center">
          <div className="text-3xl mb-1">🏆</div>
          <div className="font-extrabold text-lg">
            Barcha darslar tugatildi!
          </div>
          <div className="text-sm text-white/80 font-semibold">
            Yangi modullar tez orada qo'shiladi.
          </div>
        </section>
      )}

      {/* Rejimlar */}
      <section>
        <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2">
          REJIMLAR
        </div>
        <div className="grid grid-cols-2 gap-3">
          {MODES.map((m) => (
            <button
              key={m.label}
              className="flex items-center gap-3 rounded-2xl bg-card border border-cardline p-3 text-left active:scale-95 transition-transform opacity-70"
            >
              <div className="w-11 h-11 shrink-0 rounded-xl bg-gold-soft flex items-center justify-center">
                <span className="font-arabic text-lg text-emerald-dark leading-none pt-0.5">
                  {m.ar}
                </span>
              </div>
              <div className="min-w-0">
                <div className="text-[13px] font-extrabold leading-tight">
                  {m.label}
                </div>
                <div className="text-[11px] text-ink-soft font-semibold truncate">
                  Tez orada
                </div>
              </div>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
