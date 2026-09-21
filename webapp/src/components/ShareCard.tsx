import { useEffect, useState } from "react";
import { api, type ShareCardInfo } from "../lib/api";

/** 📤 Ulashish kartasi (K21.5) — haftalik natija rasmi.
 *
 *  Server PNG yasaydi (story 9:16). Yo'llar: Telegram story (Bot API 7.8+,
 *  `shareToStory` — havola premium'da; matn hammada), botga yuborish (foydalanuvchi
 *  do'stlariga forward qiladi; xabarda «Do'stlarga ulashish» tugmasi), havolani
 *  nusxalash. Kartada taklif havolasi + QR: do'st birinchi darsni tugatsa —
 *  ikkalasiga 3 kun VIP. */

const tg = () => window.Telegram?.WebApp;

interface Props {
  onClose: () => void;
}

export default function ShareCard({ onClose }: Props) {
  const [info, setInfo] = useState<ShareCardInfo | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    api
      .shareWeek(false)
      .then(setInfo)
      .catch(() => setError("Karta yasalmadi — keyinroq urinib ko'ring"));
  }, []);

  const canStory = !!tg()?.shareToStory && !!tg()?.isVersionAtLeast?.("7.8") && !!info?.url.startsWith("https://");

  const toStory = () => {
    if (!info) return;
    try {
      tg()?.shareToStory?.(info.url, {
        text: info.caption,
        widget_link: { url: info.ref_link, name: "Arabiy — arab tili" },
      });
      tg()?.HapticFeedback?.impactOccurred("light");
    } catch {
      setNotice("Story ochilmadi — Telegram'ni yangilang yoki botga yuboring");
    }
  };

  const toBot = async () => {
    setBusy(true);
    setNotice("");
    try {
      const r = await api.shareWeek(true);
      setInfo(r);
      if (r.sent) {
        setNotice("✅ Karta botga yuborildi — xabarni do'stlaringizga forward qiling");
        tg()?.HapticFeedback?.notificationOccurred("success");
      } else {
        setNotice("Botga yuborib bo'lmadi — havolani nusxalab ulashing");
      }
    } catch {
      setNotice("Xatolik — keyinroq urinib ko'ring");
    } finally {
      setBusy(false);
    }
  };

  const copyLink = async () => {
    if (!info) return;
    try {
      await navigator.clipboard.writeText(`${info.caption}`);
      setNotice("✅ Matn va havola nusxalandi");
    } catch {
      setNotice(info.ref_link);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] bg-black/60 flex items-end sm:items-center justify-center" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-t-3xl sm:rounded-3xl bg-sand p-4 pb-8 max-h-[92vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">📤 ULASHISH</div>
            <div className="font-extrabold">Haftalik natijam</div>
          </div>
          <button onClick={onClose} className="w-9 h-9 rounded-full bg-cardline text-ink-soft font-extrabold">
            ✕
          </button>
        </div>

        {error && (
          <div className="rounded-2xl bg-terracotta/10 border border-terracotta/30 px-4 py-3 text-sm font-semibold">{error}</div>
        )}

        {!info && !error && (
          <div className="h-72 rounded-2xl bg-card border border-cardline flex items-center justify-center text-ink-soft font-semibold">
            Karta yasalmoqda…
          </div>
        )}

        {info && (
          <>
            <div className="mx-auto w-[210px] rounded-2xl overflow-hidden border border-cardline shadow-md">
              <img src={info.path} alt="Haftalik natija kartasi" className="block w-full" />
            </div>
            <p className="mt-3 text-center text-[12px] text-ink-soft font-semibold">
              🔥 {info.streak} kun · {info.week_xp} XP so'nggi 7 kunda. Kartada taklif havolangiz bor — do'stingiz birinchi darsni
              tugatsa, ikkalangizga 3 kun VIP.
            </p>
            <div className="mt-3 space-y-2">
              {canStory && (
                <button
                  onClick={toStory}
                  className="w-full rounded-2xl bg-emerald-deep py-3.5 text-white font-extrabold active:scale-[0.98] transition-transform"
                >
                  📲 Story'ga joylash
                </button>
              )}
              <button
                onClick={toBot}
                disabled={busy}
                className="w-full rounded-2xl bg-gold py-3.5 text-white font-extrabold disabled:opacity-60 active:scale-[0.98] transition-transform"
              >
                {busy ? "Yuborilmoqda…" : "👥 Do'stlarga yuborish (bot orqali)"}
              </button>
              <button
                onClick={copyLink}
                className="w-full rounded-2xl bg-card border border-cardline py-3 font-extrabold active:scale-[0.98] transition-transform"
              >
                🔗 Havolani nusxalash
              </button>
            </div>
            {notice && <p className="mt-3 text-center text-[12px] font-bold break-all">{notice}</p>}
          </>
        )}
      </div>
    </div>
  );
}
