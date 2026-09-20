import { useEffect, useState } from "react";
import type { Badge } from "../lib/api";

/** Yangi yutuq (badge) xabari — ekran tepasida 7 soniya, bosilsa yopiladi.
 *  Speaking/yozuv/tinglash yakunida server `new_badges` qaytaradi (K20.2). */

const tg = () => window.Telegram?.WebApp;

export default function BadgeToast({ badges }: { badges: Badge[] }) {
  const [shown, setShown] = useState<Badge[]>([]);

  useEffect(() => {
    if (!badges.length) return;
    setShown(badges);
    tg()?.HapticFeedback?.notificationOccurred("success");
    const id = window.setTimeout(() => setShown([]), 7000);
    return () => window.clearTimeout(id);
  }, [badges]);

  if (!shown.length) return null;
  return (
    <div className="fixed left-0 right-0 top-3 z-[80] px-4 max-w-md mx-auto space-y-2 pointer-events-none">
      {shown.slice(0, 3).map((b) => (
        <button
          key={b.id}
          onClick={() => setShown([])}
          className="pointer-events-auto w-full flex items-center gap-3 rounded-2xl bg-card border border-gold/50 p-3 text-left shadow-lg"
        >
          <span className="text-3xl">{b.icon}</span>
          <div className="min-w-0">
            <div className="text-[10px] font-extrabold tracking-[0.14em] text-ink-soft">🏅 YANGI YUTUQ</div>
            <div className="font-extrabold text-[15px] leading-tight">{b.title}</div>
            <div className="text-xs text-ink-soft font-semibold">{b.desc}</div>
          </div>
        </button>
      ))}
      {shown.length > 3 && (
        <div className="pointer-events-auto rounded-xl bg-card/95 border border-cardline px-3 py-1.5 text-center text-[11px] font-extrabold text-ink-soft">
          +{shown.length - 3} ta yana — Profil → Yutuqlar
        </div>
      )}
    </div>
  );
}
