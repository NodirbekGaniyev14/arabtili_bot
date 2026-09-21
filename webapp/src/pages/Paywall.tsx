import { useEffect, useRef, useState } from "react";
import { api, type PayInfo, type PayPlan } from "../lib/api";

/** VIP tarif sahifasi (K17.2, K18.5).
 *
 *  Tepada chegirma taymeri → VIP imkoniyatlari → tarif (1 oy / 3 oy) va narx
 *  → (K18.5) «Karta bilan to'lash» — Telegram'ning o'z to'lov oynasi (Payme/Click),
 *  to'lov o'tishi bilan VIP avtomatik → yoki eski usul: qabul qiluvchi karta
 *  (nusxalash) → 3 qadam → chek rasmini yuklash → admin tasdiqlaydi.
 *  Avto to'lov yoqilgan bo'lsa chek oqimi «boshqa usul» ostida yig'iq turadi.
 */

type PayStatus = "" | "paid" | "pending" | "failed" | "cancelled";

interface PaywallProps {
  onClose: () => void;
  /** Nima uchun ochildi — sarlavha ostidagi qisqa sabab */
  reason?: string;
}

const tg = () => window.Telegram?.WebApp;

function fmt(n: number): string {
  return n.toLocaleString("ru-RU").replace(/,/g, " ");
}

function useCountdown(until: string | null, onExpire: () => void) {
  const [left, setLeft] = useState(0);
  useEffect(() => {
    if (!until) return;
    const end = new Date(until).getTime();
    const tick = () => {
      const ms = end - Date.now();
      setLeft(Math.max(ms, 0));
      if (ms <= 0) onExpire();
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [until]);
  const s = Math.floor(left / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (x: number) => String(x).padStart(2, "0");
  return { left, label: h > 0 ? `${pad(h)}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}` };
}

const FEATURES = [
  {
    icon: "🤖",
    title: "AI ustoz bilan jonli suhbat",
    desc: "11 mavzu, darajangizga mos — har xatoni yumshoq tuzatadi",
  },
  {
    icon: "🎤",
    title: "Speaking — mikrofon orqali",
    desc: "Gapiring, ustoz eshitadi; talaffuz bali va takrorlash mashqi",
  },
  {
    icon: "🎯",
    title: "Mock imtihonlar kasb bo'yicha",
    desc: "Shifokor, haydovchi, sotuvchi… 5 savol, baho va XP",
  },
  {
    icon: "💬",
    title: "O'zbekcha savol-javob",
    desc: "Tushunmagan so'z yoki qoidani istalgan payt so'rang",
  },
  {
    icon: "🔋",
    title: "Kuniga 40 javob",
    desc: "Bepul rejimda kuniga faqat 3 ta",
  },
];

export default function Paywall({ onClose, reason }: PaywallProps) {
  const [info, setInfo] = useState<PayInfo | null>(null);
  const [error, setError] = useState("");
  const [planId, setPlanId] = useState("1oy");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [copied, setCopied] = useState(false);
  const [trialBusy, setTrialBusy] = useState(false);
  const [trialMsg, setTrialMsg] = useState("");
  const [paying, setPaying] = useState(false);
  const [payStatus, setPayStatus] = useState<PayStatus>("");
  const [showReceipt, setShowReceipt] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const startTrial = async () => {
    if (trialBusy) return;
    setTrialBusy(true);
    try {
      const r = await api.startTrial();
      setTrialMsg(`🎁 ${r.days} kunlik VIP sinov boshlandi!`);
      load();
    } catch (e) {
      setTrialMsg((e as { detail?: string })?.detail || "Sinovni yoqib bo'lmadi.");
    } finally {
      setTrialBusy(false);
    }
  };
  const plansRef = useRef<HTMLDivElement>(null);

  const load = () =>
    api
      .getPayInfo()
      .then(setInfo)
      .catch(() => setError("Ma'lumot yuklanmadi. Qayta urinib ko'ring."));

  useEffect(() => {
    load();
  }, []);

  // K18.5: Telegram to'lov oynasi. Karta raqami bizga kelmaydi — Telegram/provayder ichida.
  // «paid» bo'lgach bot polling'iga successful_payment keladi (1–3 s) → VIP; shu
  // orada /api/pay/info ni bir necha marta qayta so'raymiz.
  const payNow = async () => {
    if (paying) return;
    setPaying(true);
    setError("");
    setPayStatus("");
    try {
      const r = await api.createInvoice(planId);
      const t = tg();
      // openInvoice — Bot API 6.1+; eski mijozda shim metod bor, lekin chaqirilsa xato otadi
      if (t?.openInvoice && t.isVersionAtLeast?.("6.1")) {
        try {
          t.openInvoice(r.url, (status) => {
            setPaying(false);
            setPayStatus(status);
            if (status === "paid") {
              t.HapticFeedback?.notificationOccurred("success");
              [1000, 3000, 6000, 10000, 15000].forEach((ms) => window.setTimeout(load, ms));
            } else if (status === "failed") {
              t.HapticFeedback?.notificationOccurred("error");
            }
          });
          return;
        } catch {
          /* qo'llanmadi — pastdagi zaxira yo'l */
        }
      }
      // Eski mijoz / brauzer: havolani Telegram'da ochamiz — to'lov chat ichida bo'ladi
      let opened = false;
      try {
        if (t?.openTelegramLink) {
          t.openTelegramLink(r.url);
          opened = true;
        }
      } catch {
        /* shim: not supported */
      }
      if (!opened) window.open(r.url, "_blank");
      setPayStatus("pending");
      [3000, 8000, 15000, 30000].forEach((ms) => window.setTimeout(load, ms));
    } catch (e) {
      setError((e as { detail?: string })?.detail || "To'lov havolasi ochilmadi. Qayta urinib ko'ring.");
    } finally {
      setPaying(false);
    }
  };

  const countdown = useCountdown(info?.discount.active ? info.discount.until : null, load);

  useEffect(() => {
    if (!file) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const plan: PayPlan | undefined = info?.plans.find((p) => p.id === planId);

  const copyCard = async () => {
    if (!info?.card_number) return;
    const digits = info.card_number.replace(/\s/g, "");
    try {
      await navigator.clipboard.writeText(digits);
    } catch {
      // Eski WebView: vaqtincha textarea orqali
      const ta = document.createElement("textarea");
      ta.value = digits;
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
      } catch {
        /* jim */
      }
      document.body.removeChild(ta);
    }
    setCopied(true);
    tg()?.HapticFeedback?.notificationOccurred("success");
    window.setTimeout(() => setCopied(false), 2000);
  };

  const pickFile = (f: File | null) => {
    if (!f) return;
    if (!f.type.startsWith("image/")) {
      setError("Faqat rasm (JPG/PNG) yuklang");
      return;
    }
    if (f.size > 6 * 1024 * 1024) {
      setError("Rasm juda katta (maks. 6 MB)");
      return;
    }
    setError("");
    setFile(f);
  };

  const submit = async () => {
    if (!file || sending) return;
    setSending(true);
    setError("");
    try {
      await api.submitReceipt(file, planId);
      setSent(true);
      setFile(null);
      tg()?.HapticFeedback?.notificationOccurred("success");
      load();
    } catch (e) {
      const err = e as { detail?: string };
      setError(err?.detail || "Yuborilmadi. Qayta urinib ko'ring.");
    } finally {
      setSending(false);
    }
  };

  const support = info?.support_username ? `@${info.support_username}` : "";

  return (
    <div className="fixed inset-0 z-[60] bg-sand flex flex-col max-w-md mx-auto">
      {/* Chegirma taymeri */}
      {info?.discount.active && countdown.left > 0 && (
        <div className="flex items-center justify-between gap-2 bg-gold-soft border-b border-gold/40 px-4 py-2.5">
          <span className="text-[13px] font-extrabold text-ink">
            🔥 {plan?.discount_percent || info.discount.percent}% chegirma saqlanib qolish
            vaqti:
          </span>
          <span className="shrink-0 rounded-lg bg-gold px-2.5 py-1 text-[13px] font-extrabold text-white tabular-nums">
            {countdown.label}
          </span>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-cardline bg-card">
        <div className="min-w-0">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
            👑 ARABIY VIP
          </div>
          <div className="font-extrabold truncate">
            {info?.vip ? `VIP faol · ${info.vip_days_left} kun qoldi` : "AI ustoz — pullik tarif"}
          </div>
        </div>
        <button
          onClick={onClose}
          className="w-9 h-9 rounded-full bg-cardline text-ink-soft font-extrabold shrink-0"
        >
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4 pb-10">
        {reason && !info?.vip && (
          <div className="rounded-2xl bg-terracotta/10 border border-terracotta/30 px-4 py-3 text-sm font-semibold">
            {reason}
          </div>
        )}

        {trialMsg && (
          <div className="rounded-2xl bg-emerald-deep/10 border border-emerald-deep/30 px-4 py-3 text-sm font-extrabold text-emerald-dark">
            {trialMsg}
          </div>
        )}

        {info && !info.vip && info.trial_available && (
          <section className="rounded-3xl bg-gold-soft border border-gold/40 p-4">
            <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">🎁 AVVAL SINAB KO'RING</div>
            <div className="text-[15px] font-extrabold mt-1">
              {info.trial_days} kun VIP — bepul, karta kerak emas
            </div>
            <div className="text-xs text-ink-soft font-semibold mt-0.5">
              Mock imtihonlar, cheksiz suhbat, talaffuz — bir marta beriladi. Yoqdi — keyin to'lov.
            </div>
            <button
              onClick={startTrial}
              disabled={trialBusy}
              className="mt-3 w-full rounded-xl bg-emerald-deep py-2.5 text-sm font-extrabold text-white active:scale-95 transition-transform disabled:opacity-60"
            >
              {trialBusy ? "…" : `🎁 ${info.trial_days} kunlik sinovni yoqish`}
            </button>
          </section>
        )}

        {info && !info.vip && (
          <div className="rounded-2xl bg-card border border-cardline px-4 py-3 text-xs font-semibold text-ink-soft">
            👥 Do'stingizni taklif qiling — birinchi darsni tugatsa <b className="text-ink">ikkalangizga {info.referral_days} kun VIP</b>.
            Havola: Profil → «Do'st taklif qilish» yoki botda /taklif.
          </div>
        )}

        {info?.vip && (
          <div className="rounded-3xl bg-gradient-to-br from-emerald-deep to-emerald-dark p-5 text-white shadow-lg">
            <div className="text-2xl">👑</div>
            <div className="text-lg font-extrabold mt-1">VIP faol</div>
            <div className="text-sm text-white/80 font-semibold">
              {info.vip_days_left} kun qoldi
              {info.vip_until
                ? ` · ${new Date(info.vip_until).toLocaleDateString("uz-UZ")} gacha`
                : ""}
            </div>
            <button
              onClick={() => plansRef.current?.scrollIntoView({ behavior: "smooth" })}
              className="mt-3 rounded-xl bg-white/15 px-4 py-2 text-sm font-extrabold"
            >
              Muddatni uzaytirish ↓
            </button>
          </div>
        )}

        {payStatus === "paid" && (
          <div className="rounded-2xl bg-emerald-deep/10 border border-emerald-deep/30 p-4">
            <div className="font-extrabold text-emerald-dark">✅ To'lov qabul qilindi!</div>
            <div className="text-sm font-semibold text-ink-soft mt-1">
              {info?.vip
                ? "VIP faol — AI ustoz, speaking va mock imtihonlar ochiq. Omad!"
                : "VIP bir necha soniyada faollashadi… Telegram'da tasdiq xabari keladi."}
            </div>
          </div>
        )}
        {payStatus === "pending" && (
          <div className="rounded-2xl bg-gold-soft border border-gold/40 p-4 text-sm font-semibold">
            ⏳ To'lov tekshirilmoqda. Tasdiqlangach VIP avtomatik yoqiladi — Telegram'da xabar keladi.
          </div>
        )}
        {payStatus === "failed" && (
          <div className="rounded-2xl bg-terracotta/10 border border-terracotta/30 px-4 py-3 text-sm font-semibold">
            ❌ To'lov o'tmadi. Boshqa karta bilan yoki pastdagi chek usuli orqali urinib ko'ring.
          </div>
        )}

        {(sent || info?.pending) && (
          <div className="rounded-2xl bg-emerald-deep/10 border border-emerald-deep/30 p-4">
            <div className="font-extrabold text-emerald-dark">✅ Chek yuborildi!</div>
            <div className="text-sm font-semibold text-ink-soft mt-1">
              Admin chekni tekshirgach, hisobingizga VIP biriktiriladi. Tasdiqlanishi
              bilan Telegram'da xabar keladi.
            </div>
          </div>
        )}

        {/* Imkoniyatlar */}
        <section className="rounded-3xl bg-card border border-cardline p-4">
          <div className="flex items-center justify-between gap-2 mb-3">
            <div className="text-[11px] font-extrabold tracking-[0.12em]">
              👑 VIP BILAN SIZ NIMALARGA EGA BO'LASIZ?
            </div>
            <span className="shrink-0 rounded-full bg-emerald-deep/10 px-2 py-0.5 text-[10px] font-extrabold text-emerald-dark">
              HAMMASI ICHIDA
            </span>
          </div>
          <div className="space-y-2">
            {[
              ...FEATURES,
              // K23.4: VIP suhbat/mock kuchliroq modelda — server sozlagan bo'lsa
              ...(info?.vip_model
                ? [
                    {
                      icon: "🧠",
                      title: `Kuchliroq AI model — ${info.vip_model}`,
                      desc: "VIP suhbat va mock imtihonlar aniqroq tushunadi va tuzatadi",
                    },
                  ]
                : []),
            ].map((f) => (
              <div
                key={f.title}
                className="flex items-start gap-3 rounded-2xl bg-sand border border-cardline px-3 py-2.5"
              >
                <div className="w-9 h-9 shrink-0 rounded-xl bg-gold-soft flex items-center justify-center text-lg">
                  {f.icon}
                </div>
                <div className="min-w-0">
                  <div className="text-[13px] font-extrabold leading-tight">{f.title}</div>
                  <div className="text-[11px] text-ink-soft font-semibold">{f.desc}</div>
                </div>
              </div>
            ))}
          </div>
          {plan && (
            <div className="mt-3 text-center text-[13px] font-bold">
              💡 Bir oy AI ustoz —{" "}
              <span className="text-emerald-dark font-extrabold">
                kuniga atigi {fmt(plan.per_day)} so'm!
              </span>
            </div>
          )}
        </section>

        {/* Tarif va narx */}
        <section ref={plansRef} className="space-y-3">
          {info && (
            <div className="grid grid-cols-2 gap-2 rounded-2xl bg-cardline/60 p-1.5">
              {info.plans.map((p) => (
                <button
                  key={p.id}
                  onClick={() => setPlanId(p.id)}
                  className={`rounded-xl px-2 py-2.5 text-center transition-colors ${
                    p.id === planId
                      ? "bg-card shadow-sm border border-cardline"
                      : "text-ink-soft"
                  }`}
                >
                  <div className="text-[12px] font-extrabold">
                    {p.months === 1 ? "👑" : "💎"} {p.title.toUpperCase()}
                  </div>
                  <div className="text-[13px] font-extrabold text-emerald-dark">
                    {fmt(p.price)} so'm
                  </div>
                </button>
              ))}
            </div>
          )}

          {plan && (
            <div className="rounded-3xl bg-card border border-cardline p-4">
              <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">
                {plan.title.toUpperCase()} · AI USTOZ CHEKSIZ
              </div>
              <div className="mt-1 flex items-end justify-between gap-2">
                <div>
                  <span className="text-[38px] leading-none font-extrabold">
                    {fmt(plan.price)}
                  </span>
                  <span className="ml-1 text-sm font-bold text-ink-soft">so'm</span>
                </div>
                <div className="text-right">
                  {plan.old_price > 0 && (
                    <div className="text-sm font-bold text-ink-soft line-through">
                      {fmt(plan.old_price)} so'm
                    </div>
                  )}
                  {info?.discount.active && plan.discount_percent > 0 && (
                    <span className="inline-block rounded-lg bg-emerald-deep/10 px-2 py-1 text-[11px] font-extrabold text-emerald-dark">
                      {plan.discount_percent}% CHEGIRMA
                    </span>
                  )}
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <span className="rounded-full bg-gold-soft px-2.5 py-1 text-[11px] font-extrabold">
                  ≈ {fmt(plan.per_day)} so'm / kun
                </span>
                {plan.months > 1 && (
                  <span className="rounded-full bg-gold-soft px-2.5 py-1 text-[11px] font-extrabold">
                    oyiga {fmt(plan.per_month)} so'm
                  </span>
                )}
                <span className="rounded-full bg-gold-soft px-2.5 py-1 text-[11px] font-extrabold">
                  {plan.days} kun
                </span>
              </div>
            </div>
          )}

          {/* K18.5: Telegram Payments — Payme / Click */}
          {info?.auto_pay && plan && (
            <div className="space-y-2">
              <button
                onClick={payNow}
                disabled={paying}
                className="w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-[15px] active:scale-[0.98] transition-transform disabled:opacity-60 shadow-lg"
              >
                {paying ? "Ochilmoqda…" : `💳 Karta bilan to'lash — ${fmt(plan.price)} so'm`}
              </button>
              <div className="text-center text-[11px] text-ink-soft font-semibold">
                {info.provider_name} · Telegram ichida xavfsiz · Uzcard / Humo · VIP darhol yoqiladi
              </div>
              {error && !showReceipt && (
                <div className="rounded-2xl bg-terracotta/10 border border-terracotta/30 px-4 py-3 text-sm font-semibold">
                  {error}
                </div>
              )}
              <button
                onClick={() => setShowReceipt((v) => !v)}
                className="w-full rounded-2xl bg-card border border-cardline py-2.5 text-[12px] font-extrabold text-ink-soft"
              >
                {showReceipt ? "▲ Chek usulini yashirish" : "▼ Boshqa usul: kartaga o'tkazma + chek"}
              </button>
            </div>
          )}

          {/* Karta */}
          {(!info?.auto_pay || showReceipt) && (
          <div className="rounded-3xl bg-ink text-sand p-4 shadow-lg">
            <div className="flex items-center justify-between">
              <div className="text-[11px] font-extrabold tracking-[0.12em] text-sand/70">
                💳 QABUL QILUVCHI KARTA:
              </div>
              <span className="rounded-md bg-white/10 px-2 py-0.5 text-[10px] font-extrabold">
                Uzcard / Humo
              </span>
            </div>
            {info?.card_number ? (
              <>
                <div className="mt-2 font-mono text-[22px] font-extrabold tracking-[0.08em] text-gold">
                  {info.card_number}
                </div>
                {info.card_holder && (
                  <div className="text-[12px] font-semibold text-sand/80">{info.card_holder}</div>
                )}
                <div className="mt-3 flex items-center justify-between gap-2">
                  <span className="text-[11px] text-sand/60 font-semibold">
                    Istalgan bank ilovasidan o'tadi
                  </span>
                  <button
                    onClick={copyCard}
                    className="shrink-0 rounded-xl bg-card px-3 py-2 text-[12px] font-extrabold text-ink active:scale-95 transition-transform"
                  >
                    {copied ? "✓ Nusxalandi" : "📋 Karta raqamini nusxalash"}
                  </button>
                </div>
                <div className="mt-3 text-[11px] text-sand/60 font-semibold">
                  ✨ Click, Payme, Uzum Bank, Anorbank, TBC, Milliy bank yoki boshqa
                  istalgan bank ilovasidan o'tkazishingiz mumkin.
                </div>
              </>
            ) : (
              <div className="mt-2 text-sm font-semibold text-sand/80">
                Karta raqami hozircha sozlanmoqda.{" "}
                {support ? `To'lov uchun ${support} ga yozing.` : "Birozdan keyin qayta kiring."}
              </div>
            )}
          </div>
          )}
        </section>

        {(!info?.auto_pay || showReceipt) && (
        <>
        {/* 3 qadam */}
        <section className="space-y-2">
          <div className="text-[11px] font-extrabold tracking-[0.12em]">
            TO'LOV QILISHNING 3 TA OSON QADAMI:
          </div>
          {[
            <>
              Telefoningizdagi istalgan bank ilovasini oching va yuqoridagi kartaga{" "}
              <b>{plan ? `${fmt(plan.price)} so'm` : "summani"}</b> o'tkazing.
            </>,
            <>
              Pul o'tkazmasi muvaffaqiyatli bo'lgach, ekrandagi{" "}
              <b>to'lov chekini (kvitansiyani) skrinshot qiling</b>.
            </>,
            <>
              Chek rasmini pastdagi tugmaga yuklang va <b>«Chekni yuborish»</b> tugmasini
              bosing.
            </>,
          ].map((node, i) => (
            <div
              key={i}
              className="flex items-start gap-3 rounded-2xl bg-card border border-cardline px-3.5 py-3"
            >
              <span className="w-7 h-7 shrink-0 rounded-full bg-emerald-deep text-white text-[13px] font-extrabold flex items-center justify-center">
                {i + 1}
              </span>
              <div className="text-[13px] font-semibold leading-snug">{node}</div>
            </div>
          ))}
        </section>

        {/* Chek yuklash */}
        {!info?.pending && !sent && (
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="text-[11px] font-extrabold tracking-[0.12em]">
                📸 TO'LOV CHEKINING RASMI:
              </div>
              <span className="text-[10px] font-extrabold text-terracotta">* MAJBURIY</span>
            </div>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
            />
            <button
              onClick={() => fileRef.current?.click()}
              className="w-full rounded-3xl border-2 border-dashed border-cardline bg-card p-5 text-center active:scale-[0.99] transition-transform"
            >
              {preview ? (
                <img
                  src={preview}
                  alt="Chek"
                  className="mx-auto max-h-56 rounded-2xl object-contain"
                />
              ) : (
                <>
                  <div className="mx-auto w-12 h-12 rounded-full bg-gold-soft flex items-center justify-center text-xl">
                    📷
                  </div>
                  <div className="mt-2 text-[13px] font-extrabold">
                    To'lov cheki skrinshotini yuklash
                  </div>
                  <div className="text-[11px] text-ink-soft font-semibold">
                    Bosing yoki faylni tanlang (JPG, PNG)
                  </div>
                </>
              )}
            </button>
            {file && (
              <button
                onClick={() => setFile(null)}
                className="text-[12px] font-bold text-ink-soft underline underline-offset-4"
              >
                Boshqa rasm tanlash
              </button>
            )}

            {error && (
              <div className="rounded-2xl bg-terracotta/10 border border-terracotta/30 px-4 py-3 text-sm font-semibold">
                {error}
              </div>
            )}

            <button
              onClick={submit}
              disabled={!file || sending}
              className="w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-[15px] active:scale-[0.98] transition-transform disabled:opacity-40"
            >
              {sending ? "Yuborilmoqda…" : "Chekni yuborish va VIP olish 🚀"}
            </button>
          </section>
        )}

        </>
        )}

        <div className="rounded-2xl bg-card border border-cardline p-4 text-[12px] font-semibold text-ink-soft">
          {info?.auto_pay
            ? "🔒 To'lov Telegram va to'lov tizimi ichida o'tadi — karta ma'lumotlari bizga kelmaydi. VIP to'lov bilanoq yoqiladi."
            : "⏳ Admin chekni tekshirgach, hisobingizga VIP biriktiriladi. Tasdiqlanishi bilan profilingizda barcha imkoniyatlar ochiladi."}
          {support && (
            <div className="mt-2">
              Savollar yoki tezlashtirish uchun:{" "}
              <a
                href={`https://t.me/${info!.support_username}`}
                target="_blank"
                rel="noreferrer"
                className="font-extrabold text-emerald-dark underline underline-offset-4"
              >
                {support}
              </a>
            </div>
          )}
        </div>

        {/* O'quvchilar — haqiqiy raqamlar */}
        {info && (
          <section className="rounded-3xl bg-card border border-cardline p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="text-[11px] font-extrabold tracking-[0.12em]">
                💬 O'QUVCHILAR
              </div>
              {info.proof.ratings > 0 && (
                <span className="rounded-full bg-emerald-deep/10 px-2 py-0.5 text-[10px] font-extrabold text-emerald-dark">
                  👍 {info.proof.like_percent}% darsdan mamnun
                </span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-2xl bg-sand border border-cardline p-3 text-center">
                <div className="text-xl font-extrabold">{fmt(info.proof.learners)}</div>
                <div className="text-[11px] text-ink-soft font-semibold">o'quvchi</div>
              </div>
              <div className="rounded-2xl bg-sand border border-cardline p-3 text-center">
                <div className="text-xl font-extrabold">{fmt(info.proof.lessons_done)}</div>
                <div className="text-[11px] text-ink-soft font-semibold">dars tugatilgan</div>
              </div>
            </div>
            {info.testimonials.length > 0 && (
              <div className="mt-3 space-y-2">
                {info.testimonials.map((t, i) => (
                  <div key={i} className="rounded-2xl bg-sand border border-cardline p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] font-extrabold">{t.name}</span>
                      <span className="text-[11px] text-gold">★★★★★</span>
                    </div>
                    <div className="mt-1 text-[12px] font-semibold text-ink-soft italic">
                      "{t.text}"
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {!info && error && (
          <div className="text-center text-ink-soft font-semibold">{error}</div>
        )}
      </div>
    </div>
  );
}
