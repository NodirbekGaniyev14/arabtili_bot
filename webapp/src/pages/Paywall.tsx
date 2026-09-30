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

/** K29: son va limitlar serverdan olinadi — matnga qattiq yozilmaydi; kunlik limit bor, shuning uchun «cheksiz» deyilmaydi. */
function featuresFor(info: PayInfo | null) {
  const topics = info?.topic_count ?? 11;
  const mocks = info?.mock_count ?? 20;
  const vip = info?.vip_turns ?? 30;
  const free = info?.free_turns ?? 3;
  return [
    {
      icon: "🤖",
      title: "AI ustoz bilan jonli suhbat",
      desc: `${topics} mavzu: Umra va Makka, safar, ish, shifokor… — har xatoni yumshoq tuzatadi`,
    },
    {
      icon: "🎤",
      title: "Speaking — mikrofon orqali",
      desc: "Gapiring, ustoz eshitadi; talaffuz bali va takrorlash mashqi",
    },
    {
      icon: "🎯",
      title: `${mocks} ta kasb bo'yicha mock imtihon`,
      desc: "Shifokor, haydovchi, umra gidi, bank… 5 savol, baho va XP",
    },
    {
      icon: "💬",
      title: "O'zbekcha savol-javob",
      desc: "Tushunmagan so'z yoki qoidani istalgan payt so'rang",
    },
    {
      icon: "🔋",
      title: `Kuniga ${vip} ta suhbat javobi`,
      desc: `Bepul rejimda kuniga faqat ${free} ta`,
    },
  ];
}

/** Hero chiplari — faqat mahsulotda HAQIQATAN bor mavzular (Ustoz: umra, safar, ish, shifokor). */
const HERO_CHIPS = ["🕋 Umra va Makka", "✈️ Safar va aeroport", "💼 Ish intervyusi", "🩺 Shifokor qabuli"];

/** K29.2: «ko'rsating, aytmang» — Ustoz javobining haqiqiy shakli (arabcha + translit + o'zbekcha; xato bo'lsa
 *  tuzatish + bir jumlali izoh + suhbat davomi). Namuna ekani yorliqda yozilgan. */
function SampleChat() {
  const bubble = "max-w-[92%] rounded-2xl rounded-tl-md bg-sand border border-cardline px-3 py-2.5";
  return (
    <section className="rounded-3xl bg-card border border-cardline p-4">
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="text-[11px] font-extrabold tracking-[0.12em]">🤖 USTOZ SHUNDAY TUZATADI</div>
        <span className="shrink-0 rounded-full bg-gold-soft px-2 py-0.5 text-[10px] font-extrabold">
          NAMUNA · 🕋 Umra
        </span>
      </div>
      <p className="mb-3 text-[12px] font-semibold text-ink-soft">
        Yozing yoki mikrofonda ayting — ustoz xatoni ko'rsatadi va suhbatni davom ettiradi.
      </p>
      <div className="space-y-2.5">
        <div className={bubble}>
          <div dir="rtl" className="font-arabic text-xl leading-snug">مَرْحَبًا! أَيْنَ تُرِيدُ أَنْ تَذْهَبَ؟</div>
          <div className="mt-0.5 text-[11px] font-semibold italic text-ink-soft">Marhaban! Ayna turiidu an tadhhaba?</div>
          <div className="text-[12px] font-semibold">Salom! Qayerga bormoqchisiz?</div>
        </div>
        <div className="ml-auto max-w-[80%] rounded-2xl rounded-tr-md bg-emerald-deep px-3 py-2.5 text-white">
          <div dir="rtl" className="font-arabic text-xl leading-snug">أنا أريد أذهب إلى الحرم</div>
          <div className="text-[10px] font-extrabold tracking-wide text-white/60">SIZ</div>
        </div>
        <div className={`${bubble} space-y-2`}>
          <div className="rounded-xl border border-gold/40 bg-gold-soft px-2.5 py-2">
            <div className="text-[10px] font-extrabold tracking-wide text-ink-soft">✏️ KICHIK TUZATISH</div>
            <div dir="rtl" className="font-arabic text-xl leading-snug">
              أَنَا أُرِيدُ <span className="font-extrabold text-emerald-dark">أَنْ أَذْهَبَ</span> إِلَى الحَرَمِ
            </div>
            <div className="text-[12px] font-semibold">«أُرِيدُ» dan keyin «أَنْ» keladi, fe'l esa «أَذْهَبَ» shaklida bo'ladi.</div>
          </div>
          <div>
            <div dir="rtl" className="font-arabic text-xl leading-snug">
              كَيْفَ تُرِيدُ أَنْ تَذْهَبَ؟ بِالحَافِلَةِ أَمْ سَيْرًا عَلَى الأَقْدَامِ؟
            </div>
            <div className="text-[12px] font-semibold">Qanday bormoqchisiz? Avtobusdami yoki piyoda?</div>
          </div>
        </div>
      </div>
    </section>
  );
}

/** K29.2: bepul va VIP farqi — faqat haqiqiy farqlar. Darslar, lug'at, Oktagon bepul qoladi (ishonch: VIP — qo'shimcha). */
function Compare({ info }: { info: PayInfo }) {
  const rows: { label: string; free: string; vip: string }[] = [
    { label: "AI ustoz javobi (kuniga)", free: String(info.free_turns), vip: String(info.vip_turns) },
    // Mock imtihon 5 savol + ochilish = ~6 javob: bepul limit shunga yetmasa, buni to'g'ri aytamiz
    ...(info.free_turns < 6 ? [{ label: "Mock imtihon (5 savol)", free: "oxirigacha yetmaydi", vip: "to'liq ✓" }] : []),
    ...(info.vip_model ? [{ label: "Kuchliroq AI model", free: "—", vip: `${info.vip_model} ✓` }] : []),
    { label: "Darslar, lug'at, Oktagon", free: "bepul ✓", vip: "bepul ✓" },
  ];
  return (
    <section className="rounded-3xl bg-card border border-cardline p-4">
      <div className="text-[11px] font-extrabold tracking-[0.12em] mb-2">⚖️ BEPUL VA VIP</div>
      <div className="grid grid-cols-[1fr_auto_auto] gap-x-3 gap-y-1.5 text-[12px] font-semibold items-center">
        <span />
        <span className="text-[10px] font-extrabold tracking-wide text-ink-soft text-center">BEPUL</span>
        <span className="text-[10px] font-extrabold tracking-wide text-emerald-dark text-center">👑 VIP</span>
        {rows.map((r) => (
          <div key={r.label} className="contents">
            <span className="border-t border-cardline pt-1.5">{r.label}</span>
            <span className="border-t border-cardline pt-1.5 text-center text-ink-soft max-w-[92px]">{r.free}</span>
            <span className="border-t border-cardline pt-1.5 text-center font-extrabold text-emerald-dark">{r.vip}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

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
            {info?.vip ? `VIP faol · ${info.vip_days_left} kun qoldi` : "Arabcha gapirishni boshlang"}
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

        {/* K29: va'da — funksiya ro'yxati emas, natija (faqat mahsulotda haqiqatan bor narsalar) */}
        {info && !info.vip && (
          <section className="rounded-3xl bg-gradient-to-br from-emerald-deep to-emerald-dark p-5 text-white shadow-lg">
            <div className="text-[11px] font-extrabold tracking-[0.14em] text-gold-soft">👑 SHAXSIY AI USTOZ</div>
            <div className="mt-1 text-[22px] leading-tight font-extrabold">Umra, safar va ishda arabcha gaplashing</div>
            <p className="mt-2 text-[13px] font-semibold text-white/85">
              Siz gapirasiz — ustoz eshitadi va xatoni o'sha zahoti yumshoq tushuntiradi.
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {HERO_CHIPS.map((c) => (
                <span key={c} className="rounded-full bg-white/15 px-2.5 py-1 text-[11px] font-extrabold">
                  {c}
                </span>
              ))}
            </div>
            {plan && (
              <div className="mt-3 text-[13px] font-extrabold text-gold-soft">
                Kuniga atigi {fmt(plan.per_day)} so'm
              </div>
            )}
          </section>
        )}

        {info && !info.vip && <SampleChat />}

        {info && !info.vip && info.trial_available && (
          <section className="rounded-3xl bg-gold-soft border border-gold/40 p-4">
            <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">🎁 AVVAL SINAB KO'RING</div>
            <div className="text-[15px] font-extrabold mt-1">
              {info.trial_days} kun VIP — bepul, karta kerak emas
            </div>
            <div className="text-xs text-ink-soft font-semibold mt-0.5">
              Mock imtihonlar, kuniga {info.vip_turns} ta suhbat javobi, talaffuz — bir marta beriladi. Yoqdi — keyin to'lov.
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

        {(sent || info?.pending) && (
          <div className="rounded-2xl bg-emerald-deep/10 border border-emerald-deep/30 p-4">
            <div className="font-extrabold text-emerald-dark">✅ Chek yuborildi!</div>
            <div className="text-sm font-semibold text-ink-soft mt-1">
              Kunduzi (08:00–22:00) {info?.sla_hours ?? 2} soat ichida tekshiriladi va VIP yoqiladi.
              Tasdiqlanishi bilan Telegram'da xabar keladi.
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
              ...featuresFor(info),
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

        {info && !info.vip && <Compare info={info} />}

        {/* Tarif va narx */}
        <section ref={plansRef} className="space-y-3">
          {info && (
            <div className="grid grid-cols-2 gap-2 rounded-2xl bg-cardline/60 p-1.5">
              {info.plans.map((p) => {
                // K29.2: uzoq tarifning haqiqiy tejami (1 oylik narx × oy − tarif narxi)
                const base = info.plans.find((x) => x.months === 1);
                const save = base && p.months > 1 ? base.price * p.months - p.price : 0;
                return (
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
                    {save > 0 && (
                      <div className="text-[10px] font-extrabold text-terracotta">
                        {fmt(save)} so'm tejaysiz
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {plan && (
            <div className="rounded-3xl bg-card border border-cardline p-4">
              <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">
                {plan.title.toUpperCase()} · AI USTOZ + MOCK IMTIHONLAR
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

          {/* Karta (chek oqimi — yagona to'lov usuli) */}
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
        </section>

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

        <div className="rounded-2xl bg-card border border-cardline p-4 text-[12px] font-semibold text-ink-soft">
          ⏳ Chek kunduzi (08:00–22:00) {info?.sla_hours ?? 2} soat ichida tekshiriladi, keyin VIP yoqiladi va Telegram'da xabar keladi.
          <div className="mt-1 text-[11px]">
            Har bir to'lov bank orqali kartaga tushganligi bo'yicha tekshiriladi — haqiqiy to'lov qiling.
          </div>
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
