import type { WeekDay } from "../lib/api";

/** «So'nggi 7 kun» diagrammasi (K19.1): kunlik XP ustunlari, ustida tugatilgan
 *  darslar soni, chiziq — kunlik XP maqsadi. Bugun yashil, o'tgan kunlar och
 *  yashil, bo'sh kunlar kulrang. Faqat CSS/div — kutubxonasiz. */

const WD = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"];

function weekday(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return WD[(d.getDay() + 6) % 7];
}

export default function WeekChart({ week, xpGoal, onShare }: { week: WeekDay[]; xpGoal: number; onShare?: () => void }) {
  if (!week?.length) return null;
  const max = Math.max(xpGoal, ...week.map((d) => d.xp), 1);
  const lessons = week.reduce((s, d) => s + d.lessons, 0);
  const xp = week.reduce((s, d) => s + d.xp, 0);
  const active = week.filter((d) => d.xp > 0).length;
  const goalPct = Math.min((xpGoal / max) * 100, 100);
  const H = 72; // ustunlar maydoni balandligi (px)

  return (
    <section className="rounded-3xl bg-card border border-cardline p-4">
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">SO'NGGI 7 KUN</div>
        <div className="flex items-center gap-2">
          <div className="text-[11px] font-extrabold text-ink-soft">
            {lessons} dars · {xp} XP · {active}/7 kun
          </div>
          {onShare && (
            <button
              onClick={onShare}
              className="rounded-lg bg-gold-soft px-2 py-1 text-[11px] font-extrabold text-emerald-dark active:scale-95 transition-transform"
              title="Natijani ulashish"
            >
              📤
            </button>
          )}
        </div>
      </div>

      <div className="relative mt-3">
        {/* Maqsad chizig'i */}
        <div
          className="absolute left-0 right-0 border-t-2 border-dashed border-gold pointer-events-none"
          style={{ bottom: `${(goalPct / 100) * H + 22}px` }}
          aria-hidden
        >
          <span className="absolute right-0 -top-4 rounded bg-gold-soft px-1 text-[9px] font-extrabold text-ink">
            maqsad {xpGoal}
          </span>
        </div>
        <div className="grid grid-cols-7 gap-1.5 items-end">
          {week.map((d, i) => {
            const isToday = i === week.length - 1;
            const h = Math.max(Math.round((d.xp / max) * H), d.xp > 0 ? 6 : 3);
            const color = isToday ? "bg-emerald-deep" : d.xp > 0 ? "bg-emerald-deep/45" : "bg-cardline";
            return (
              <div key={d.day} className="flex flex-col items-center gap-1" title={`${d.day}: ${d.xp} XP, ${d.lessons} dars`}>
                <span className={`h-4 text-[10px] font-extrabold leading-4 ${d.lessons ? "text-emerald-dark" : "text-transparent"}`}>
                  {d.lessons ? `${d.lessons}📖` : "·"}
                </span>
                <div className="w-full flex items-end" style={{ height: `${H}px` }}>
                  <div className={`w-full rounded-t-md ${color} transition-[height] duration-500`} style={{ height: `${h}px` }} />
                </div>
                <span className={`text-[10px] font-extrabold ${isToday ? "text-emerald-dark" : "text-ink-soft"}`}>
                  {isToday ? "Bugun" : weekday(d.day)}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
