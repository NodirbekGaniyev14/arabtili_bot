import { useEffect, useMemo, useState } from "react";
import {
  api,
  type Insight,
  type InsightAction,
  type SkillId,
  type SkillStat,
  type StatsData,
  type StatsPeriod,
} from "../lib/api";

/** K31 «📊 Statistika» — ko'nikmalar qanday o'smoqda + VIP «Shaxsiy tahlil» (services/insights.py).
 *
 *  Bepul: streak, taxminiy daraja (A0→B2 zinapoyasi), maqsad, 4 ko'nikma, lug'at, tarix.
 *  VIP: 5 tahlildan 4 tasi (zaif ko'nikma, arabchaga xos xatolar, prognoz, haftalik reja) — bepul
 *  foydalanuvchi qiymatni emas, xira «skelet» va 👑 ni ko'radi (server qiymatni yubormaydi).
 *  Ranglar: ko'nikma — kategorik (--color-sk-*), lug'at darajalari — tartibli bir rang (--color-lv-*),
 *  ikkalasi ham validate_palette.js dan o'tgan; rang doim yozuv/ikonka bilan birga. */

const tg = () => window.Telegram?.WebApp;

export const SKILLS: { id: SkillId; uz: string; ar: string; icon: string; color: string }[] = [
  { id: "reading", uz: "O'qish", ar: "قِرَاءَة", icon: "📖", color: "var(--color-sk-reading)" },
  { id: "listening", uz: "Tinglash", ar: "اِسْتِمَاع", icon: "🎧", color: "var(--color-sk-listening)" },
  { id: "writing", uz: "Yozish", ar: "كِتَابَة", icon: "✍️", color: "var(--color-sk-writing)" },
  { id: "speaking", uz: "Gapirish", ar: "مُحَادَثَة", icon: "🎙️", color: "var(--color-sk-speaking)" },
];
const SKILL_BY_ID = Object.fromEntries(SKILLS.map((s) => [s.id, s])) as Record<SkillId, (typeof SKILLS)[number]>;

const LEVELS = ["A0", "A1", "A2", "B1", "B2"];
/** Tailwind v4 faqat matnda TO'LIQ yozilgan var(--color-…) larni chiqaradi — shablon satr bilan yig'ilmaydi */
const LEVEL_COLORS = ["var(--color-lv-0)", "var(--color-lv-1)", "var(--color-lv-2)", "var(--color-lv-3)", "var(--color-lv-4)"];
const LEVEL_NAME: Record<string, string> = {
  A0: "Boshlang'ich",
  A1: "Elementar",
  A2: "O'rta-quyi",
  B1: "O'rta",
  B2: "O'rta-yuqori",
};

const PERIODS: { id: StatsPeriod; label: string }[] = [
  { id: "week", label: "Hafta" },
  { id: "month", label: "Oy" },
  { id: "3m", label: "3 oy" },
  { id: "all", label: "Hammasi" },
];

type TabId = "overview" | SkillId | "vocab" | "history";
const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: "overview", label: "Umumiy", icon: "◎" },
  ...SKILLS.map((s) => ({ id: s.id as TabId, label: s.uz, icon: s.icon })),
  { id: "vocab", label: "Lug'at", icon: "📚" },
  { id: "history", label: "Tarix", icon: "🕘" },
];

const SKILL_ACTION: Record<SkillId, InsightAction> = {
  reading: "lesson",
  listening: "listen",
  writing: "writing",
  speaking: "live",
};
const ACTION_LABEL: Record<string, string> = {
  lesson: "Darsni boshlash",
  listen: "Tinglash mashqi",
  writing: "Yozuv mashqi",
  live: "Jonli AI suhbat",
  mistakes: "Xatolar daftari",
  review: "Takrorlash",
};

const MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"];
const WD = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"];

function dayLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const y = new Date();
  y.setDate(today.getDate() - 1);
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (same(d, today)) return "Bugun";
  if (same(d, y)) return "Kecha";
  return `${d.getDate()}-${MONTHS[d.getMonth()]}`;
}

function longDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return isNaN(d.getTime()) ? iso : `${d.getDate()}-${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

function time(iso: string): string {
  return iso.slice(11, 16);
}

/** Ball rangi — holat (yaxshi/o'rta/past), doim raqam bilan birga ko'rsatiladi */
function scoreTone(s: number | null): string {
  if (s === null) return "bg-cardline text-ink-soft";
  if (s >= 80) return "bg-emerald-deep/12 text-emerald-dark";
  if (s >= 50) return "bg-gold-soft text-ink";
  return "bg-terracotta/12 text-terracotta";
}

function Delta({ d }: { d: number | null }) {
  if (d === null || d === 0) return null;
  const up = d > 0;
  return (
    <span
      className={`inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[10px] font-extrabold ${
        up ? "bg-emerald-deep/12 text-emerald-dark" : "bg-terracotta/12 text-terracotta"
      }`}
    >
      {up ? "▲" : "▼"} {up ? "+" : ""}
      {d}
    </span>
  );
}

function Skeleton({ w }: { w: number }) {
  return (
    <span aria-hidden className="inline-block h-3 rounded-full bg-ink/25 blur-[3px] align-middle" style={{ width: w }} />
  );
}

// ─────────────────────────── Shaxsiy tahlil kartasi ───────────────────────────

function InsightDetail({ it, onAction }: { it: Insight; onAction?: (a: InsightAction) => void }) {
  if (it.id === "mistakes" && it.top?.length) {
    const max = Math.max(...it.top.map((t) => t.count), 1);
    return (
      <div className="space-y-2.5">
        {it.top.map((t, i) => (
          <div key={t.id} className="rounded-2xl bg-sand border border-cardline p-3">
            <div className="flex items-center gap-2.5">
              <span className="w-9 h-9 shrink-0 rounded-xl bg-emerald-deep/10 text-emerald-dark flex items-center justify-center font-arabic text-lg leading-none">
                {t.mark}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-[13px] font-extrabold leading-tight">
                    {i + 1}. {t.title}
                    {t.pair ? ` · ${t.pair}` : ""}
                  </span>
                  <span className="shrink-0 text-[12px] font-extrabold tabular-nums">{t.count} marta</span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-cardline overflow-hidden">
                  <div className="h-full rounded-full bg-terracotta" style={{ width: `${(t.count / max) * 100}%` }} />
                </div>
              </div>
            </div>
            {t.example?.fixed && (
              <div className="mt-2 rounded-xl bg-card border border-cardline px-3 py-2 space-y-0.5">
                {t.example.said && (
                  <div dir="rtl" className="font-arabic text-[17px] leading-snug text-ink-soft line-through decoration-terracotta/60">
                    {t.example.said}
                  </div>
                )}
                <div dir="rtl" className="font-arabic text-[19px] leading-snug font-bold text-emerald-dark">
                  {t.example.fixed}
                </div>
              </div>
            )}
            <p className="mt-2 text-[12px] font-semibold leading-relaxed">💡 {t.tip}</p>
          </div>
        ))}
        {onAction && (
          <button
            onClick={() => onAction("mistakes")}
            className="w-full rounded-xl bg-emerald-deep py-2.5 text-[13px] font-extrabold text-white active:scale-[0.98] transition-transform"
          >
            📒 Xatolar daftarida mashq qilish
          </button>
        )}
      </div>
    );
  }
  if (it.id === "plan" && it.plan?.length) {
    return (
      <div className="space-y-1.5">
        {it.plan.map((p, i) => (
          <div key={i} className="flex items-center gap-3 rounded-2xl bg-sand border border-cardline px-3 py-2.5">
            <span className="w-8 h-8 shrink-0 rounded-xl bg-gold-soft flex items-center justify-center text-base">{p.icon}</span>
            <span className="min-w-0 flex-1 text-[13px] font-bold leading-snug">{p.text}</span>
            {onAction && p.action && (
              <button
                onClick={() => onAction(p.action)}
                className="shrink-0 rounded-lg bg-emerald-deep/10 px-2.5 py-1.5 text-[11px] font-extrabold text-emerald-dark active:scale-95 transition-transform"
              >
                Boshlash ›
              </button>
            )}
          </div>
        ))}
        <p className="pt-1 text-[11px] font-semibold text-ink-soft">{it.detail}</p>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <p className="text-[13px] font-semibold leading-relaxed">{it.detail}</p>
      {onAction && it.action && (
        <button
          onClick={() => onAction(it.action!)}
          className="w-full rounded-xl bg-emerald-deep py-2.5 text-[13px] font-extrabold text-white active:scale-[0.98] transition-transform"
        >
          {ACTION_LABEL[it.action] ?? "Boshlash"} ›
        </button>
      )}
    </div>
  );
}

function InsightRow({
  it,
  open,
  onToggle,
  onUnlock,
  onAction,
}: {
  it: Insight;
  open: boolean;
  onToggle: () => void;
  onUnlock?: () => void;
  onAction?: (a: InsightAction) => void;
}) {
  const locked = it.state !== "open";
  const click = it.state === "vip" ? onUnlock : it.state === "open" ? onToggle : undefined;
  return (
    <div className={`border-t border-cardline ${open ? "bg-gold-soft/40" : ""}`}>
      <button
        onClick={click}
        disabled={!click}
        className="w-full flex items-center gap-3 px-4 py-3 text-left active:bg-gold-soft/50 transition-colors disabled:active:bg-transparent"
        aria-expanded={it.state === "open" ? open : undefined}
      >
        <span
          className={`w-10 h-10 shrink-0 rounded-2xl flex items-center justify-center text-lg ${
            locked ? "bg-gold-soft" : "bg-emerald-deep/10"
          }`}
        >
          {locked ? "🔒" : it.icon}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[14px] font-extrabold leading-tight">{it.title}</span>
          {it.state === "open" && (
            <span className="block mt-0.5 text-[13px] font-extrabold text-emerald-dark leading-snug">{it.value}</span>
          )}
          {it.state === "vip" && (
            <>
              <span className="block mt-1">
                <Skeleton w={56 + ((it.title.length * 7) % 40)} />
              </span>
              <span className="block mt-1 text-[11px] font-semibold text-ink-soft leading-snug">{it.teaser}</span>
            </>
          )}
          {it.state === "data" && (
            <span className="block mt-0.5">
              <span className="block text-[11px] font-semibold text-ink-soft leading-snug">{it.need}</span>
              {it.want ? (
                <span className="mt-1.5 flex items-center gap-2">
                  <span className="h-1.5 flex-1 max-w-[140px] rounded-full bg-cardline overflow-hidden">
                    <span
                      className="block h-full rounded-full bg-gold"
                      style={{ width: `${Math.round(((it.have ?? 0) / it.want) * 100)}%` }}
                    />
                  </span>
                  <span className="text-[10px] font-extrabold text-ink-soft tabular-nums">
                    {it.have}/{it.want}
                  </span>
                </span>
              ) : null}
            </span>
          )}
        </span>
        {it.state === "vip" && (
          <span className="shrink-0 rounded-full bg-gradient-to-br from-emerald-deep to-emerald-dark px-2 py-1 text-[10px] font-extrabold text-white">
            👑 VIP
          </span>
        )}
        {it.state === "open" && (
          <span className={`shrink-0 text-ink-soft font-extrabold transition-transform ${open ? "rotate-90" : ""}`}>›</span>
        )}
      </button>
      {open && it.state === "open" && (
        <div className="px-4 pb-4 -mt-1">
          <InsightDetail it={it} onAction={onAction} />
        </div>
      )}
    </div>
  );
}

/** Statistika va Paywall'da bir xil karta. `onUnlock` — VIP sahifasi (yoki Paywall ichida — tariflarga). */
export function InsightsCard({
  data,
  onUnlock,
  onAction,
  unlockLabel,
}: {
  data: StatsData;
  onUnlock?: () => void;
  onAction?: (a: InsightAction) => void;
  unlockLabel?: string;
}) {
  const { items, unlocked, total } = data.insights;
  const [openId, setOpenId] = useState<string | null>(null);
  const lockedVip = items.filter((i) => i.state === "vip").length;
  const goal = data.goal;
  return (
    <section className="rounded-3xl bg-card border border-cardline overflow-hidden shadow-sm">
      <div className="bg-gold-soft px-4 pt-4 pb-3.5">
        <div className="flex items-center gap-3">
          <span className="w-11 h-11 shrink-0 rounded-2xl bg-gradient-to-br from-emerald-deep to-emerald-dark text-white flex items-center justify-center font-arabic text-2xl leading-none pt-1 shadow-md">
            ج
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[15px] font-extrabold leading-tight">Shaxsiy tahlilingiz</div>
            <div className="text-[12px] font-semibold text-ink-soft leading-snug">
              {total} tadan {unlocked} tasi ochiq
              {lockedVip > 0 ? " — qolganini VIP ochadi" : unlocked < total ? " — mashq qilgan sari ochiladi" : " — hammasi tayyor ✓"}
            </div>
          </div>
        </div>
        <div className="mt-3 grid gap-1" style={{ gridTemplateColumns: `repeat(${total}, minmax(0, 1fr))` }}>
          {items.map((it) => (
            <span
              key={it.id}
              className={`h-1.5 rounded-full ${it.state === "open" ? "bg-emerald-deep" : "bg-gold/45"}`}
            />
          ))}
        </div>
      </div>

      {items.map((it) => (
        <InsightRow
          key={it.id}
          it={it}
          open={openId === it.id}
          onToggle={() => setOpenId((o) => (o === it.id ? null : it.id))}
          onUnlock={onUnlock}
          onAction={onAction}
        />
      ))}

      {lockedVip > 0 && onUnlock && (
        <div className="border-t border-cardline p-3">
          <button
            onClick={onUnlock}
            className="w-full rounded-2xl bg-gradient-to-br from-emerald-deep to-emerald-dark py-3.5 text-[14px] font-extrabold text-white shadow-md active:scale-[0.98] transition-transform"
          >
            {unlockLabel ?? `👑 ${lockedVip} ta tahlilni VIP bilan ochish`}
          </button>
        </div>
      )}

      <div className="border-t border-cardline px-4 py-2.5 flex items-center gap-2 text-[11px] font-semibold text-ink-soft">
        <span aria-hidden>🗓</span>
        {goal.target_date && goal.days_left !== null ? (
          goal.days_left > 0 ? (
            <span>
              Maqsad: {longDate(goal.target_date)} gacha {goal.target} · <b className="text-ink">{goal.days_left} kun</b> qoldi
            </span>
          ) : (
            <span>Maqsad sanasi o'tdi — Profil'da yangi sana qo'ying</span>
          )
        ) : (
          <span>Maqsad sanasi yo'q — reja uni tanlashga yordam beradi</span>
        )}
      </div>
    </section>
  );
}

// ─────────────────────────── Umumiy ko'rinish bloklari ───────────────────────────

function LevelCard({ data }: { data: StatsData }) {
  const lv = data.level;
  return (
    <section className="relative overflow-hidden rounded-3xl bg-card border border-cardline p-4 shadow-sm">
      <div className="relative flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">TAXMINIY DARAJA</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-[44px] leading-none font-extrabold tracking-tight">{lv.level}</span>
            <span className="text-[13px] font-extrabold text-ink-soft">{LEVEL_NAME[lv.level] ?? ""}</span>
          </div>
        </div>
        <div className="text-right">
          <div dir="rtl" className="font-arabic text-lg text-gold leading-none">المُسْتَوَى</div>
          <div className="mt-1.5 text-[12px] font-extrabold tabular-nums">
            {lv.done}/{lv.total} dars
          </div>
        </div>
      </div>

      {/* A0 → B2 zinapoyasi: o'tilgan — to'liq, joriy — foiz bilan, oldindagi — bo'sh */}
      <div className="relative mt-3 grid grid-cols-5 gap-1">
        {LEVELS.map((l, i) => {
          const fill = i < lv.level_index ? 100 : i === lv.level_index ? lv.percent : 0;
          return (
            <div key={l} className="space-y-1">
              <div className="h-2 rounded-full bg-cardline overflow-hidden">
                <div className="h-full rounded-full bg-emerald-deep" style={{ width: `${fill}%` }} />
              </div>
              <div
                className={`text-center text-[10px] font-extrabold ${
                  i === lv.level_index ? "text-emerald-dark" : "text-ink-soft"
                }`}
              >
                {l}
                {i === lv.level_index ? ` · ${lv.percent}%` : ""}
              </div>
            </div>
          );
        })}
      </div>

      <div className="relative mt-3 grid grid-cols-2 gap-2">
        {SKILLS.map((s) => {
          const v = data.skills_90[s.id];
          return (
            <div key={s.id} className="flex items-center gap-2 rounded-xl border border-cardline bg-sand px-3 py-2">
              <span className="w-2.5 h-2.5 shrink-0 rounded-full" style={{ background: s.color }} />
              <span className="min-w-0 flex-1 text-[12px] font-bold">{s.uz}</span>
              <span className="text-[13px] font-extrabold tabular-nums">{v === null ? "—" : `${v}%`}</span>
            </div>
          );
        })}
      </div>
      <div className="relative mt-2 text-[10px] font-semibold text-ink-soft">Ko'nikma ballari — so'nggi 90 kun o'rtachasi</div>
    </section>
  );
}

function StreakCard({ s }: { s: StatsData["streak"] }) {
  return (
    <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#c9a227] to-[#9a7612] p-4 text-white shadow-md">
      <span aria-hidden className="pointer-events-none absolute -right-2 -top-6 font-arabic text-[96px] leading-none text-white/10">
        ن
      </span>
      <div className="relative text-[10px] font-extrabold tracking-[0.14em] text-white/85">🔥 STREAK</div>
      <div className="relative mt-1">
        <span className="block text-[40px] leading-none font-extrabold tabular-nums">{s.days}</span>
        <span className="block text-[11px] font-extrabold text-white/90">kun ketma-ket</span>
      </div>
      <div className="relative mt-3 grid grid-cols-7 gap-0.5 rounded-2xl bg-black/10 px-1.5 py-2">
        {s.week.map((d, i) => (
          <div key={d.day} className="flex flex-col items-center gap-1">
            <span
              className={`w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-extrabold ${
                d.active ? "bg-white text-[#9a7612]" : d.future ? "bg-white/15" : "bg-white/30"
              } ${d.today ? "ring-2 ring-white ring-offset-1 ring-offset-[#b08c1d]" : ""}`}
            >
              {d.active ? "✓" : ""}
            </span>
            <span className="text-[8px] font-extrabold text-white/85">{WD[i]}</span>
          </div>
        ))}
      </div>
      <div className="relative mt-2 text-[11px] font-bold text-white/90 leading-snug">
        {s.today_done ? "Bugun bajarildi ✓" : s.days ? "Bugun dars qiling — zanjir uzilmasin" : "Bitta dars — streak boshlanadi"}
        {s.freezes > 0 ? ` · 🧊 ${s.freezes}` : ""}
      </div>
    </section>
  );
}

function GoalCard({ g }: { g: StatsData["goal"] }) {
  return (
    <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-terracotta to-[#9b4528] p-4 text-white shadow-md">
      <span aria-hidden className="pointer-events-none absolute -right-1 -bottom-8 font-arabic text-[90px] leading-none text-white/10">
        هـ
      </span>
      <div className="relative flex items-center justify-between">
        <span className="text-[10px] font-extrabold tracking-[0.14em] text-white/85">🎯 MAQSAD</span>
        <span dir="rtl" className="font-arabic text-[15px] leading-none text-white/80">الهَدَف</span>
      </div>
      <div className="relative mt-1">
        <span className="block text-[40px] leading-none font-extrabold">{g.target}</span>
        <span className="block text-[11px] font-extrabold text-white/90">daraja — {LEVEL_NAME[g.target]?.toLowerCase()}</span>
      </div>
      <div className="relative mt-3 h-2 rounded-full bg-white/25 overflow-hidden">
        <div className="h-full rounded-full bg-white" style={{ width: `${Math.max(g.percent, 2)}%` }} />
      </div>
      <div className="relative mt-1 flex justify-between text-[10px] font-extrabold text-white/85">
        <span>{g.current} hozir</span>
        <span>{g.percent}%</span>
      </div>
      <div className="relative mt-1.5 text-[11px] font-bold text-white/90 leading-snug">
        {g.remaining > 0 ? `${g.remaining} ta dars qoldi` : "Maqsadga yetdingiz 🎉"}
      </div>
    </section>
  );
}

function SkillCard({ id, st, onOpen }: { id: SkillId; st: SkillStat; onOpen: () => void }) {
  const s = SKILL_BY_ID[id];
  return (
    <button
      onClick={onOpen}
      className="rounded-2xl bg-card border border-cardline p-3 text-left active:scale-[0.98] transition-transform"
    >
      <span className="flex items-start justify-between gap-2">
        <span
          className="w-10 h-10 shrink-0 rounded-xl flex items-center justify-center text-lg"
          style={{ background: `color-mix(in srgb, ${s.color} 14%, transparent)` }}
        >
          {s.icon}
        </span>
        <span className="text-right">
          <span className="block text-[20px] font-extrabold leading-none tabular-nums">{st.score === null ? "—" : `${st.score}%`}</span>
          <span className="mt-1 flex h-5 items-center justify-end">
            <Delta d={st.delta} />
          </span>
        </span>
      </span>
      <span className="mt-2 flex items-baseline justify-between gap-2">
        <span className="text-[13px] font-extrabold leading-tight">{s.uz}</span>
        <span dir="rtl" className="font-arabic text-[14px] leading-none text-ink-soft">{s.ar}</span>
      </span>
      <span className="mt-0.5 block text-[11px] font-semibold text-ink-soft">{st.count} ta mashq</span>
      <span className="mt-2 block h-1.5 rounded-full bg-cardline overflow-hidden">
        <span className="block h-full rounded-full" style={{ width: `${st.score ?? 0}%`, background: s.color }} />
      </span>
    </button>
  );
}

function LevelBar({ levels }: { levels: StatsData["vocab"]["levels"] }) {
  const total = levels.reduce((s, l) => s + l.count, 0);
  if (!total) return null;
  const color = (lv: string) => {
    const i = LEVELS.indexOf(lv);
    return i >= 0 ? LEVEL_COLORS[i] : "var(--color-cardline)";
  };
  const label = (lv: string) => (lv === "other" ? "Harf/o'zak" : lv);
  return (
    <div>
      {/* 2px oraliq — segmentlar bir-biriga yopishmaydi; uchlari yumaloq */}
      <div className="flex h-3 gap-[2px] rounded-full overflow-hidden" role="img" aria-label="Lug'at darajalar bo'yicha">
        {levels.map((l) => (
          <div
            key={l.level}
            title={`${label(l.level)}: ${l.count}`}
            className="h-full first:rounded-l-full last:rounded-r-full"
            style={{ width: `${(l.count / total) * 100}%`, background: color(l.level), minWidth: 4 }}
          />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
        {levels.map((l) => (
          <span key={l.level} className="inline-flex items-center gap-1.5 text-[11px] font-bold text-ink-soft">
            <span className="w-2 h-2 rounded-full" style={{ background: color(l.level) }} />
            {label(l.level)} ({l.count})
          </span>
        ))}
      </div>
    </div>
  );
}

function VocabCard({ v, onOpen }: { v: StatsData["vocab"]; onOpen: () => void }) {
  return (
    <button
      onClick={onOpen}
      className="w-full rounded-3xl bg-card border border-cardline p-4 text-left active:scale-[0.99] transition-transform"
    >
      <div className="flex items-start gap-3">
        <span className="w-10 h-10 shrink-0 rounded-xl bg-emerald-deep/10 flex items-center justify-center text-lg">📚</span>
        <span className="min-w-0 flex-1">
          <span className="block text-[14px] font-extrabold leading-tight">Lug'at</span>
          <span className="block text-[11px] font-semibold text-ink-soft">{v.total} ta so'z kartotekada</span>
        </span>
        <span className="shrink-0 flex gap-4 text-right">
          <span>
            <span className="block text-[18px] font-extrabold leading-none tabular-nums">
              {v.retention === null ? "—" : `${v.retention}%`}
            </span>
            <span className="block text-[10px] font-semibold text-ink-soft mt-1">eslab qolish</span>
          </span>
          <span>
            <span className="block text-[18px] font-extrabold leading-none tabular-nums text-gold">{v.due}</span>
            <span className="block text-[10px] font-semibold text-ink-soft mt-1">takrorga</span>
          </span>
        </span>
      </div>
      {v.levels.length > 0 && (
        <div className="mt-3">
          <LevelBar levels={v.levels} />
        </div>
      )}
    </button>
  );
}

// ─────────────────────────── Ko'nikma bo'limi ───────────────────────────

type HistoryItem = StatsData["history"][number];

/** Ballar diagrammasi: bir qator (ko'nikma rangi), eskidan yangiga; bosilgan ustun — izoh. */
function ScoreBars({ items, color }: { items: HistoryItem[]; color: string }) {
  const pts = items.filter((h) => h.score !== null).slice(0, 20).reverse();
  const [sel, setSel] = useState<number | null>(null);
  if (pts.length < 2) return null;
  const H = 96;
  const cur = sel !== null ? pts[sel] : pts[pts.length - 1];
  return (
    <div>
      <div className="flex items-baseline justify-between text-[11px] font-semibold text-ink-soft">
        <span className="truncate pr-2">
          {dayLabel(cur.at)}, {time(cur.at)} · {cur.title}
        </span>
        <span className="shrink-0 text-[13px] font-extrabold text-ink tabular-nums">{cur.score}%</span>
      </div>
      <div className="relative mt-2" style={{ height: H }}>
        {[50, 100].map((g) => (
          <div
            key={g}
            className="absolute left-0 right-0 border-t border-cardline"
            style={{ bottom: (g / 100) * H }}
            aria-hidden
          >
            <span className="absolute -top-3 right-0 text-[9px] font-bold text-ink-soft">{g}</span>
          </div>
        ))}
        <div className="absolute inset-0 flex items-end gap-[2px] pr-6">
          {pts.map((p, i) => (
            <button
              key={i}
              onClick={() => setSel(i)}
              onMouseEnter={() => setSel(i)}
              className="relative h-full flex-1 flex items-end"
              aria-label={`${p.title}: ${p.score}%`}
            >
              <span
                className="block w-full rounded-t-[4px] transition-opacity"
                style={{
                  height: Math.max(3, ((p.score ?? 0) / 100) * H),
                  background: color,
                  opacity: sel === null ? (i === pts.length - 1 ? 1 : 0.7) : sel === i ? 1 : 0.45,
                }}
              />
            </button>
          ))}
        </div>
      </div>
      <div className="mt-1 h-px bg-ink-soft/40" aria-hidden />
    </div>
  );
}

function HistoryList({ items }: { items: HistoryItem[] }) {
  const groups = useMemo(() => {
    const out: { label: string; rows: HistoryItem[] }[] = [];
    for (const h of items) {
      const label = dayLabel(h.at);
      const last = out[out.length - 1];
      if (last && last.label === label) last.rows.push(h);
      else out.push({ label, rows: [h] });
    }
    return out;
  }, [items]);
  return (
    <div className="space-y-3">
      {groups.map((g) => (
        <div key={g.label}>
          <div className="px-1 pb-1.5 text-[11px] font-extrabold tracking-[0.12em] text-ink-soft uppercase">{g.label}</div>
          <div className="rounded-2xl bg-card border border-cardline divide-y divide-cardline">
            {g.rows.map((h, i) => {
              const sk = SKILL_BY_ID[h.skill as SkillId];
              const icon = sk?.icon ?? (h.skill === "vocab" ? "⚔️" : "🏅");
              return (
                <div key={i} className="flex items-center gap-3 px-3 py-2.5">
                  <span
                    className="w-8 h-8 shrink-0 rounded-xl flex items-center justify-center text-sm"
                    style={{ background: sk ? `color-mix(in srgb, ${sk.color} 14%, transparent)` : "var(--color-gold-soft)" }}
                  >
                    {icon}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-bold leading-tight truncate">{h.title}</span>
                    <span className="block text-[10px] font-semibold text-ink-soft">
                      {time(h.at)}
                      {sk ? ` · ${sk.uz}` : h.skill === "vocab" ? " · Lug'at" : " · Imtihon"}
                      {h.xp ? ` · +${h.xp} XP` : ""}
                    </span>
                  </span>
                  <span className={`shrink-0 rounded-lg px-2 py-1 text-[12px] font-extrabold tabular-nums ${scoreTone(h.score)}`}>
                    {h.score === null ? "✓" : `${h.score}%`}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

function SkillTab({
  id,
  data,
  onAction,
}: {
  id: SkillId;
  data: StatsData;
  onAction?: (a: InsightAction) => void;
}) {
  const s = SKILL_BY_ID[id];
  const st = data.skills[id];
  const items = data.history.filter((h) => h.skill === id);
  const weak = data.insights.items.find((i) => i.id === "weak");
  const isWeak = weak?.state === "open" && weak.skill === id;
  return (
    <div className="space-y-3">
      <section className="rounded-3xl bg-card border border-cardline p-4 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span
              className="w-12 h-12 rounded-2xl flex items-center justify-center text-2xl"
              style={{ background: `color-mix(in srgb, ${s.color} 14%, transparent)` }}
            >
              {s.icon}
            </span>
            <div>
              <div className="text-[17px] font-extrabold leading-tight">{s.uz}</div>
              <div dir="rtl" className="font-arabic text-[17px] leading-none text-ink-soft mt-1 text-left">
                {s.ar}
              </div>
            </div>
          </div>
          <div className="text-right">
            <div className="text-[32px] leading-none font-extrabold tabular-nums">{st.score === null ? "—" : `${st.score}%`}</div>
            <div className="mt-1 flex justify-end items-center gap-1.5 text-[11px] font-semibold text-ink-soft">
              <Delta d={st.delta} /> {st.count} ta mashq
            </div>
          </div>
        </div>
        {isWeak && (
          <div className="mt-3 rounded-2xl bg-terracotta/10 border border-terracotta/25 px-3 py-2 text-[12px] font-semibold">
            🎯 Eng zaif ko'nikmangiz — {weak?.detail}
          </div>
        )}
        <div className="mt-4">
          <ScoreBars items={items} color={s.color} />
        </div>
        {onAction && (
          <button
            onClick={() => onAction(SKILL_ACTION[id])}
            className="mt-4 w-full rounded-2xl bg-emerald-deep py-3 text-[14px] font-extrabold text-white active:scale-[0.98] transition-transform"
          >
            {s.icon} {ACTION_LABEL[SKILL_ACTION[id]]} ›
          </button>
        )}
      </section>
      {items.length ? (
        <HistoryList items={items} />
      ) : (
        <div className="rounded-2xl bg-card border border-dashed border-cardline p-6 text-center">
          <div className="text-3xl">{s.icon}</div>
          <div className="mt-2 text-[14px] font-extrabold">Bu davrda {s.uz.toLowerCase()} mashqi yo'q</div>
          <div className="mt-1 text-[12px] font-semibold text-ink-soft">Davrni «Hammasi» ga o'zgartiring yoki bitta mashq bajaring.</div>
        </div>
      )}
    </div>
  );
}

function VocabTab({ v, onAction }: { v: StatsData["vocab"]; onAction?: (a: InsightAction) => void }) {
  const stages = [
    { id: "new", label: "Yangi", hint: "hali takrorlanmagan", n: v.stages.new },
    { id: "learning", label: "O'rganilmoqda", hint: "3 haftagacha", n: v.stages.learning },
    { id: "mature", label: "Mustahkam", hint: "3 haftadan uzoq", n: v.stages.mature },
  ];
  return (
    <div className="space-y-3">
      <section className="rounded-3xl bg-card border border-cardline p-4 shadow-sm">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">LUG'AT</div>
            <div className="mt-1 text-[32px] leading-none font-extrabold tabular-nums">{v.total}</div>
            <div className="text-[12px] font-semibold text-ink-soft">so'z va ibora kartotekada</div>
          </div>
          <div dir="rtl" className="font-arabic text-2xl text-gold leading-none">مُفْرَدَات</div>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2">
          {stages.map((s) => (
            <div key={s.id} className="rounded-2xl bg-sand border border-cardline p-2.5 text-center">
              <div className="text-[18px] font-extrabold tabular-nums">{s.n}</div>
              <div className="text-[11px] font-extrabold leading-tight">{s.label}</div>
              <div className="text-[9px] font-semibold text-ink-soft">{s.hint}</div>
            </div>
          ))}
        </div>
        {v.levels.length > 0 && (
          <div className="mt-4">
            <div className="mb-2 text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">DARAJALAR BO'YICHA</div>
            <LevelBar levels={v.levels} />
          </div>
        )}
        <div className="mt-4 grid grid-cols-2 gap-2">
          <div className="rounded-2xl bg-emerald-deep/10 p-3">
            <div className="text-[18px] font-extrabold tabular-nums text-emerald-dark">
              {v.retention === null ? "—" : `${v.retention}%`}
            </div>
            <div className="text-[11px] font-bold">eslab qolish</div>
          </div>
          <div className="rounded-2xl bg-gold-soft p-3">
            <div className="text-[18px] font-extrabold tabular-nums">{v.due}</div>
            <div className="text-[11px] font-bold">bugun takrorga</div>
          </div>
        </div>
        {onAction && v.due > 0 && (
          <button
            onClick={() => onAction("review")}
            className="mt-3 w-full rounded-2xl bg-emerald-deep py-3 text-[14px] font-extrabold text-white active:scale-[0.98] transition-transform"
          >
            🔁 {v.due} ta kartani takrorlash ›
          </button>
        )}
      </section>

      {v.hardest.length > 0 && (
        <section className="rounded-3xl bg-card border border-cardline p-4">
          <div className="text-[11px] font-extrabold tracking-[0.12em] mb-2">🧩 ENG QIYIN SO'ZLARINGIZ</div>
          <div className="space-y-1.5">
            {v.hardest.map((w) => (
              <div key={w.ar} className="flex items-center gap-3 rounded-2xl bg-sand border border-cardline px-3 py-2">
                <span dir="rtl" className="font-arabic text-xl leading-snug">{w.ar}</span>
                <span className="min-w-0 flex-1 text-[12px] font-semibold text-ink-soft truncate">{w.uz}</span>
                <span className="shrink-0 rounded-lg bg-terracotta/12 px-2 py-1 text-[11px] font-extrabold text-terracotta">
                  {w.lapses}× unutilgan
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

// ─────────────────────────── Sahifa ───────────────────────────

export default function Stats({
  onClose,
  onOpenPaywall,
  onAction,
}: {
  onClose: () => void;
  onOpenPaywall: () => void;
  onAction?: (a: InsightAction) => void;
}) {
  const [period, setPeriod] = useState<StatsPeriod>("month");
  const [tab, setTab] = useState<TabId>("overview");
  const [data, setData] = useState<StatsData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setError("");
    api
      .getStats(period)
      .then((d) => alive && setData(d))
      .catch(() => alive && setError("Statistika yuklanmadi. Qayta urinib ko'ring."));
    return () => {
      alive = false;
    };
  }, [period]);

  const pickTab = (t: TabId) => {
    setTab(t);
    tg()?.HapticFeedback?.impactOccurred("light");
  };

  return (
    <div className="fixed inset-0 z-[55] bg-sand flex flex-col max-w-md mx-auto">
      <header className="bg-card border-b border-cardline px-4 pt-3 pb-2.5 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-baseline gap-2">
              <h1 className="text-[24px] leading-none font-extrabold tracking-tight">Statistika</h1>
              <span dir="rtl" className="font-arabic text-[18px] leading-none text-gold">إِحْصَائِيَّات</span>
            </div>
            <p className="mt-1 text-[12px] font-semibold text-ink-soft">Ko'nikmalaringiz qanday o'smoqda</p>
          </div>
          <button onClick={onClose} className="w-9 h-9 shrink-0 rounded-full bg-cardline text-ink-soft font-extrabold" aria-label="Yopish">
            ✕
          </button>
        </div>

        <div className="grid grid-cols-4 gap-1 rounded-full bg-cardline/70 p-1" role="tablist" aria-label="Davr">
          {PERIODS.map((p) => (
            <button
              key={p.id}
              role="tab"
              aria-selected={period === p.id}
              onClick={() => setPeriod(p.id)}
              className={`rounded-full py-1.5 text-[12px] font-extrabold transition-colors ${
                period === p.id ? "bg-emerald-deep text-white shadow-sm" : "text-ink-soft"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <nav className="-mx-4 px-4 flex gap-1.5 overflow-x-auto no-scrollbar" aria-label="Bo'limlar">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => pickTab(t.id)}
              className={`shrink-0 flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-extrabold transition-colors ${
                tab === t.id ? "bg-ink text-sand" : "bg-sand border border-cardline text-ink-soft"
              }`}
            >
              <span aria-hidden>{t.icon}</span>
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      <div className="flex-1 overflow-y-auto p-4 pb-10 space-y-3">
        {!data && !error && (
          <div className="space-y-3" aria-busy>
            {[180, 150, 120].map((h) => (
              <div key={h} className="rounded-3xl bg-card border border-cardline animate-pulse" style={{ height: h }} />
            ))}
          </div>
        )}
        {error && !data && <div className="pt-10 text-center font-semibold text-ink-soft">{error}</div>}

        {data && tab === "overview" && (
          <>
            <InsightsCard data={data} onUnlock={onOpenPaywall} onAction={onAction} />
            <LevelCard data={data} />
            <div className="grid grid-cols-2 gap-3">
              <StreakCard s={data.streak} />
              <GoalCard g={data.goal} />
            </div>
            <div className="pt-1 flex items-center justify-between px-1">
              <span className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">KO'NIKMALAR</span>
              <span className="text-[11px] font-semibold text-ink-soft">{PERIODS.find((p) => p.id === period)?.label.toLowerCase()} bo'yicha</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {SKILLS.map((s) => (
                <SkillCard key={s.id} id={s.id} st={data.skills[s.id]} onOpen={() => pickTab(s.id)} />
              ))}
            </div>
            <VocabCard v={data.vocab} onOpen={() => pickTab("vocab")} />
          </>
        )}

        {data && SKILLS.some((s) => s.id === tab) && <SkillTab id={tab as SkillId} data={data} onAction={onAction} />}
        {data && tab === "vocab" && <VocabTab v={data.vocab} onAction={onAction} />}
        {data && tab === "history" &&
          (data.history.length ? (
            <HistoryList items={data.history} />
          ) : (
            <div className="rounded-2xl bg-card border border-dashed border-cardline p-6 text-center text-[13px] font-semibold text-ink-soft">
              Bu davrda mashq yo'q. Davrni «Hammasi» ga o'zgartiring.
            </div>
          ))}
      </div>
    </div>
  );
}
