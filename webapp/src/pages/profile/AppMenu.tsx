/** Profil pastidagi «Ilovam» bo'limi (K26): Fikr bildirish · Ilova qanday ishlaydi · Sozlamalar.
 *
 *  Har biri to'liq ekranli ichki sahifa (SubPage) — orqaga tugmasi bilan. Sozlamalar ichida: mavzu
 *  (kunduzgi/tungi/avto), ovoz, kunlik maqsad, bildirishnomalar (bot xabarlari turlari), reja. */

import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { api, type NotifyItem, type NotifySettings } from "../../lib/api";
import { isSoundOn, setSoundOn } from "../../lib/audio";
import { getMode, setMode, type ThemeMode } from "../../lib/theme";

const tg = () => window.Telegram?.WebApp;
const tap = () => tg()?.HapticFeedback?.impactOccurred("light");

export const GOAL_OPTIONS = [
  { minutes: 10, label: "10 daqiqa", xp: 20 },
  { minutes: 20, label: "20 daqiqa", xp: 30 },
  { minutes: 30, label: "30 daqiqa", xp: 50 },
  { minutes: 60, label: "1 soat", xp: 80 },
];

type Page = "feedback" | "help" | "settings" | "notifications" | null;

export default function AppMenu({
  dailyMinutes,
  savingGoal,
  onGoal,
  onOpenPlacement,
  onResetPlan,
  resetting,
  memberSince,
}: {
  dailyMinutes: number;
  savingGoal: boolean;
  onGoal: (minutes: number) => void;
  onOpenPlacement?: () => void;
  onResetPlan: () => void;
  resetting: boolean;
  memberSince?: string;
}) {
  const [page, setPage] = useState<Page>(null);
  const open = (p: Page) => {
    tap();
    setPage(p);
  };

  return (
    <section>
      <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2.5">ILOVAM</div>
      <div className="rounded-2xl bg-card border border-cardline divide-y divide-cardline overflow-hidden">
        <MenuRow icon="💬" title="Fikr bildirish" onClick={() => open("feedback")} />
        <MenuRow icon="ℹ️" title="Ilova qanday ishlaydi" onClick={() => open("help")} />
      </div>
      <div className="mt-3 rounded-2xl bg-card border border-cardline overflow-hidden">
        <MenuRow icon="⚙️" title="Sozlamalar" sub="Mavzu, bildirishnomalar, ovoz, maqsad" onClick={() => open("settings")} />
      </div>

      <div className="mt-4 text-center text-[11px] font-semibold text-ink-soft/80">
        <span className="font-arabic text-[13px]">عَرَبِيّ</span> · Arabiy v{__APP_VERSION__}
        {memberSince ? <div className="mt-0.5">A'zo bo'lgan sana: {memberSince}</div> : null}
      </div>

      {page === "feedback" && (
        <SubPage title="Fikr bildirish" onBack={() => setPage(null)}>
          <FeedbackBody />
        </SubPage>
      )}
      {page === "help" && (
        <SubPage title="Ilova qanday ishlaydi" onBack={() => setPage(null)}>
          <HelpBody />
        </SubPage>
      )}
      {page === "settings" && (
        <SubPage title="Sozlamalar" onBack={() => setPage(null)}>
          <SettingsBody
            dailyMinutes={dailyMinutes}
            savingGoal={savingGoal}
            onGoal={onGoal}
            onNotifications={() => open("notifications")}
            onOpenPlacement={onOpenPlacement}
            onResetPlan={onResetPlan}
            resetting={resetting}
          />
        </SubPage>
      )}
      {page === "notifications" && (
        <SubPage title="Bildirishnomalar" onBack={() => setPage("settings")}>
          <NotificationsBody />
        </SubPage>
      )}
    </section>
  );
}

// ───────────────────────── umumiy qismlar ─────────────────────────

function IconTile({ icon }: { icon: string }) {
  return (
    <span className="w-10 h-10 shrink-0 rounded-xl bg-emerald-deep/10 flex items-center justify-center text-[18px]">{icon}</span>
  );
}

function MenuRow({ icon, title, sub, onClick }: { icon: string; title: string; sub?: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-full flex items-center gap-3 px-4 py-3.5 text-left active:bg-cardline/40 transition-colors">
      <IconTile icon={icon} />
      <span className="min-w-0 flex-1">
        <span className="block text-[15px] font-extrabold">{title}</span>
        {sub && <span className="block text-[11px] font-semibold text-ink-soft truncate">{sub}</span>}
      </span>
      <span className="text-xl text-ink-soft/70 leading-none">›</span>
    </button>
  );
}

function SubPage({ title, onBack, children }: { title: string; onBack: () => void; children: ReactNode }) {
  useEffect(() => {
    const t = tg();
    const back = () => onBack();
    t?.BackButton?.show?.();
    t?.BackButton?.onClick?.(back);
    return () => {
      t?.BackButton?.offClick?.(back);
      t?.BackButton?.hide?.();
    };
  }, [onBack]);
  return createPortal(
    <div className="fixed inset-0 z-50 bg-sand flex flex-col max-w-md mx-auto">
      <div className="flex items-center gap-3 px-4 pt-3 pb-2">
        <button
          onClick={onBack}
          className="w-10 h-10 rounded-xl bg-card border border-cardline flex items-center justify-center text-xl font-extrabold text-ink active:scale-95"
          aria-label="Orqaga"
        >
          ‹
        </button>
        <h2 className="text-xl font-extrabold">{title}</h2>
      </div>
      <div className="flex-1 overflow-y-auto px-4 pb-8" style={{ paddingBottom: "max(2rem, env(safe-area-inset-bottom))" }}>
        {children}
      </div>
    </div>,
    document.body
  );
}

function GroupTitle({ text }: { text: string }) {
  return <div className="mt-5 mb-2 text-[13px] font-extrabold text-ink-soft">{text}</div>;
}

function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={() => onChange(!on)}
      className={`relative w-12 h-7 shrink-0 rounded-full transition-colors ${on ? "bg-emerald-deep" : "bg-cardline"}`}
    >
      <span
        className={`absolute top-0.5 left-0.5 w-6 h-6 rounded-full bg-white shadow transition-transform ${on ? "translate-x-5" : ""}`}
      />
    </button>
  );
}

// ───────────────────────── Sozlamalar ─────────────────────────

function SettingsBody({
  dailyMinutes,
  savingGoal,
  onGoal,
  onNotifications,
  onOpenPlacement,
  onResetPlan,
  resetting,
}: {
  dailyMinutes: number;
  savingGoal: boolean;
  onGoal: (minutes: number) => void;
  onNotifications: () => void;
  onOpenPlacement?: () => void;
  onResetPlan: () => void;
  resetting: boolean;
}) {
  const [mode, setModeState] = useState<ThemeMode>(() => getMode());
  const [sound, setSound] = useState(isSoundOn());
  const [notif, setNotif] = useState<NotifySettings | null>(null);
  useEffect(() => {
    api.getNotifications().then(setNotif).catch(() => setNotif(null));
  }, []);
  const onCount = notif ? notif.items.filter((i) => i.on).length : 0;

  const pickMode = (m: ThemeMode) => {
    setMode(m);
    setModeState(m);
    tap();
  };
  const themes: Array<{ id: ThemeMode; icon: string; label: string }> = [
    { id: "light", icon: "☀️", label: "Kunduzgi" },
    { id: "dark", icon: "🌙", label: "Tungi" },
    { id: "auto", icon: "📱", label: "Avto" },
  ];

  return (
    <>
      <p className="text-[13px] font-semibold text-ink-soft">Ilovani o'zingizga moslang — o'zgarishlar darhol qo'llanadi.</p>

      <GroupTitle text="Ko'rinish" />
      <div className="rounded-2xl bg-card border border-cardline p-3">
        <div className="flex items-center gap-3">
          <IconTile icon="🌗" />
          <div className="min-w-0 flex-1">
            <div className="text-[15px] font-extrabold">Tungi / kunduzgi rejim</div>
            <div className="text-[11px] font-semibold text-ink-soft">«Avto» — Telegram mavzusiga ergashadi</div>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-1.5 rounded-xl bg-cardline/50 p-1">
          {themes.map((t) => (
            <button
              key={t.id}
              onClick={() => pickMode(t.id)}
              className={`rounded-lg py-2 text-[12px] font-extrabold transition-colors ${
                mode === t.id ? "bg-card shadow-sm text-ink" : "text-ink-soft"
              }`}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>
      </div>

      <GroupTitle text="Bildirishnomalar va ovoz" />
      <div className="rounded-2xl bg-card border border-cardline divide-y divide-cardline overflow-hidden">
        <MenuRow
          icon="🔔"
          title="Bildirishnomalar"
          sub={notif ? `${onCount} / ${notif.items.length} tur yoqilgan` : "Qaysi bot xabarlari kelsin"}
          onClick={onNotifications}
        />
        <div className="flex items-center gap-3 px-4 py-3.5">
          <IconTile icon="🔊" />
          <div className="min-w-0 flex-1">
            <div className="text-[15px] font-extrabold">Ovoz (talaffuz)</div>
            <div className="text-[11px] font-semibold text-ink-soft">So'zlar ochilganda avtomatik o'qiladi</div>
          </div>
          <Toggle
            on={sound}
            label="Ovoz"
            onChange={(v) => {
              setSound(v);
              setSoundOn(v);
              tap();
            }}
          />
        </div>
      </div>

      <GroupTitle text="Kunlik maqsad" />
      <div className="grid grid-cols-2 gap-2.5">
        {GOAL_OPTIONS.map((g) => {
          const active = g.minutes === dailyMinutes;
          return (
            <button
              key={g.minutes}
              disabled={savingGoal}
              onClick={() => onGoal(g.minutes)}
              className={`rounded-2xl border p-3 text-left transition-all active:scale-[0.98] ${
                active ? "bg-emerald-deep/10 border-emerald-deep" : "bg-card border-cardline"
              }`}
            >
              <div className="font-extrabold text-[15px]">{g.label}</div>
              <div className="text-xs text-ink-soft font-semibold">Kuniga {g.xp} XP</div>
            </button>
          );
        })}
      </div>

      <GroupTitle text="Reja" />
      <div className="space-y-2.5">
        {onOpenPlacement && (
          <button
            onClick={onOpenPlacement}
            className="w-full rounded-2xl border-2 border-emerald-deep/40 bg-emerald-deep/8 py-3.5 font-extrabold text-emerald-deep active:scale-[0.98] transition-transform"
          >
            🎯 Darajani qayta aniqlash
            <span className="block text-[11px] font-semibold text-ink-soft">Qisqa test · darslaringiz va XP saqlanadi</span>
          </button>
        )}
        <button
          onClick={onResetPlan}
          disabled={resetting}
          className="w-full rounded-2xl border-2 border-terracotta/50 bg-terracotta/8 py-3.5 font-extrabold text-terracotta active:scale-[0.98] transition-transform disabled:opacity-50"
        >
          {resetting ? "Tozalanmoqda..." : "🗑 Rejani tozalash"}
          <span className="block text-[11px] font-semibold text-ink-soft">Onboardingdan qayta o'tasiz · XP va so'zlar saqlanadi</span>
        </button>
      </div>
    </>
  );
}

// ───────────────────────── Bildirishnomalar ─────────────────────────

function NotificationsBody() {
  const [data, setData] = useState<NotifySettings | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    api
      .getNotifications()
      .then(setData)
      .catch(() => setError(true));
  }, []);

  const toggle = async (item: NotifyItem, on: boolean) => {
    if (!data) return;
    tap();
    const prev = data;
    setData({ ...data, items: data.items.map((i) => (i.key === item.key ? { ...i, on } : i)) });
    try {
      setData(await api.setNotification(item.key, on));
    } catch {
      setData(prev); // saqlanmadi — qaytaramiz
    }
  };

  if (error) return <div className="py-10 text-center text-ink-soft font-semibold">Yuklanmadi — internetni tekshiring</div>;
  if (!data) return <div className="py-10 text-center text-ink-soft font-semibold">Yuklanmoqda…</div>;

  const group = (g: "types" | "other") => data.items.filter((i) => i.group === g);
  const block = (items: NotifyItem[]) => (
    <div className="rounded-2xl bg-card border border-cardline divide-y divide-cardline overflow-hidden">
      {items.map((i) => (
        <div key={i.key} className="flex items-center gap-3 px-4 py-3.5">
          <IconTile icon={i.icon} />
          <div className="min-w-0 flex-1">
            <div className="text-[15px] font-extrabold">{i.title}</div>
            <div className="text-[11px] font-semibold text-ink-soft leading-snug">{i.desc}</div>
          </div>
          <Toggle on={i.on} label={i.title} onChange={(v) => toggle(i, v)} />
        </div>
      ))}
    </div>
  );

  return (
    <>
      <p className="text-[13px] font-semibold text-ink-soft">
        Qaysi xabarlarni olishni o'zingiz tanlaysiz. Har qanday vaqtda o'chirib qo'yishingiz mumkin.
      </p>
      <GroupTitle text="Turlari" />
      {block(group("types"))}
      <GroupTitle text="Boshqa xabarlar" />
      {block(group("other"))}
      <p className="mt-4 text-[11px] font-semibold text-ink-soft text-center">{data.always}</p>
    </>
  );
}

// ───────────────────────── Fikr bildirish ─────────────────────────

function FeedbackBody() {
  const [text, setText] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const send = async () => {
    const t = text.trim();
    if (!t || state === "sending") return;
    setState("sending");
    try {
      await api.submitFeedback(t, "profil");
      setState("sent");
      setText("");
      tg()?.HapticFeedback?.notificationOccurred?.("success");
    } catch {
      setState("idle");
    }
  };

  if (state === "sent") {
    return (
      <div className="mt-6 rounded-3xl bg-card border border-cardline p-6 text-center">
        <div className="text-4xl">🌟</div>
        <p className="mt-2 text-lg font-extrabold text-emerald-dark">Rahmat!</p>
        <p className="text-[13px] text-ink-soft font-semibold">Fikringiz jamoaga yetdi. Javob bo'lsa, bot orqali yozamiz.</p>
        <button onClick={() => setState("idle")} className="mt-3 text-[13px] font-bold text-emerald-dark underline">
          Yana yozish
        </button>
      </div>
    );
  }
  return (
    <>
      <p className="text-[13px] font-semibold text-ink-soft">
        Taklif, xato yoki nima yoqqani — hammasi ilovani yaxshilashga yordam beradi. Javobni bot orqali olasiz.
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value.slice(0, 2000))}
        placeholder="Fikringizni shu yerga yozing..."
        rows={6}
        className="mt-4 w-full rounded-2xl bg-card border border-cardline px-4 py-3 text-[15px] font-semibold resize-none outline-none focus:border-emerald-deep/50"
      />
      <button
        onClick={send}
        disabled={!text.trim() || state === "sending"}
        className="mt-3 w-full rounded-2xl bg-emerald-deep py-3.5 text-white font-extrabold active:scale-[0.98] transition-transform disabled:opacity-40"
      >
        {state === "sending" ? "Yuborilmoqda..." : "✉️ Yuborish"}
      </button>
      <p className="mt-3 text-[11px] font-semibold text-ink-soft text-center">
        Test savolida xato ko'rsangiz — savol ostidagi «⚠️ Xatolik bormi?» tugmasini bosing, savol o'zi biriktiriladi.
      </p>
    </>
  );
}

// ───────────────────────── Ilova qanday ishlaydi ─────────────────────────

const HELP: Array<{ icon: string; title: string; text: string }> = [
  { icon: "📚", title: "Darslar", text: "A0 dan B2 gacha bosqichma-bosqich. Har dars: yangi so'zlar, mashqlar va mikro-test. 60% dan o'tsangiz, keyingisi ochiladi." },
  { icon: "🔁", title: "Takrorlash", text: "O'rgangan so'zlaringiz aqlli takrorlash (SRS) bilan unutilishidan oldin qaytib keladi. Kuniga bir necha daqiqa yetarli." },
  { icon: "📖", title: "Lug'at", text: "6000 so'z darajalar va mavzular bo'yicha: 5 talik fleshkarta, keyin 10 savollik test va XP." },
  { icon: "🤖", title: "AI ustoz", text: "Darajangizda jonli suhbat, speaking va mock imtihon. Ovozli javobingiz tekshiriladi, xatolar tushuntiriladi." },
  { icon: "⚔️", title: "Oktagon", text: "1v1 lug'at jangi: 10 savol × 10 soniya. Tez va to'g'ri javob — ko'p ball, ligalar va haftalik jadval." },
  { icon: "🔥", title: "Streak va XP", text: "Har kungi mashq streakni oshiradi. Muzlatkich bir kunni o'tkazib yuborsangiz ham streakni saqlaydi." },
  { icon: "🏆", title: "Reyting va sertifikat", text: "Haftalik va oylik reytingda XP bo'yicha bellashasiz. Daraja imtihonidan o'tsangiz — sertifikat." },
  { icon: "⚠️", title: "Xatolik bormi?", text: "Har test savoli ostida bor. Bossangiz, savol jamoaga yetadi. Tuzatilgach, bot sizga xabar beradi." },
];

function HelpBody() {
  return (
    <>
      <p className="text-[13px] font-semibold text-ink-soft">Arabiy — arab tilini kuniga 10 daqiqada o'rganish uchun. Asosiy bo'limlar:</p>
      <div className="mt-4 space-y-2.5">
        {HELP.map((h) => (
          <div key={h.title} className="flex gap-3 rounded-2xl bg-card border border-cardline px-4 py-3.5">
            <IconTile icon={h.icon} />
            <div className="min-w-0">
              <div className="text-[15px] font-extrabold">{h.title}</div>
              <div className="mt-0.5 text-[12px] font-semibold text-ink-soft leading-snug">{h.text}</div>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
