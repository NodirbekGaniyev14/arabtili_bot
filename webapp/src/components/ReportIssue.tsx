/** «Xatolik bormi?» (K26) — har test savoli ostida kichik havola.
 *
 *  O'quvchi bosadi → turini tanlaydi (javob xato hisoblandi / talaffuz / tarjima / tushunarsiz / boshqa),
 *  ixtiyoriy izoh yozadi → savol «surati» (matn, variantlar, to'g'ri javob, audio fayl) adminga boradi.
 *  Admin «✅ Tuzatildi» bossa — o'quvchiga bot xabar beradi (bildirishnoma yoqilgan bo'lsa). */

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api, type IssueKind, type IssueReport } from "../lib/api";

const tg = () => window.Telegram?.WebApp;

const KINDS: Array<{ id: IssueKind; label: string }> = [
  { id: "wrong_answer", label: "✅ To'g'ri javobim xato hisoblandi" },
  { id: "audio", label: "🔊 Talaffuz (ovoz) xato" },
  { id: "text", label: "✍️ Tarjima yoki imlo xato" },
  { id: "unclear", label: "🤔 Savol tushunarsiz" },
  { id: "other", label: "💬 Boshqa" },
];

export type IssueContext = Omit<IssueReport, "kind" | "comment">;

export default function ReportIssue({ ctx, className = "" }: { ctx: IssueContext; className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <div className={`flex justify-center ${className}`}>
        <button
          onClick={() => {
            tg()?.HapticFeedback?.impactOccurred("light");
            setOpen(true);
          }}
          className="px-3 py-1.5 text-[11px] font-bold text-ink-soft/80 underline decoration-dotted underline-offset-4 active:opacity-60"
        >
          ⚠️ Xatolik bormi?
        </button>
      </div>
      {open && createPortal(<IssueSheet ctx={ctx} onClose={() => setOpen(false)} />, document.body)}
    </>
  );
}

function IssueSheet({ ctx, onClose }: { ctx: IssueContext; onClose: () => void }) {
  const [kind, setKind] = useState<IssueKind | null>(null);
  const [comment, setComment] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  useEffect(() => {
    if (state !== "sent") return;
    const t = window.setTimeout(onClose, 1800);
    return () => window.clearTimeout(t);
  }, [state, onClose]);

  const send = async () => {
    if (!kind || state === "sending") return;
    setState("sending");
    try {
      await api.reportIssue({ ...ctx, kind, comment: comment.trim() });
      setState("sent");
      tg()?.HapticFeedback?.notificationOccurred?.("success");
    } catch {
      setState("error");
    }
  };

  return (
    <div className="fixed inset-0 z-[70] bg-ink/45 flex items-end" onClick={onClose}>
      <div
        className="w-full max-w-md mx-auto rounded-t-3xl bg-sand px-4 pt-4"
        style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}
        onClick={(e) => e.stopPropagation()}
      >
        {state === "sent" ? (
          <div className="py-8 text-center">
            <div className="text-4xl">🙏</div>
            <div className="mt-2 text-lg font-extrabold">Rahmat!</div>
            <p className="mt-1 text-[13px] font-semibold text-ink-soft">
              Xabaringiz jamoaga yetdi. Tuzatilgach sizga bot orqali xabar beramiz.
            </p>
          </div>
        ) : (
          <>
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-lg font-extrabold">Savolda xato bormi?</div>
                <p className="mt-0.5 text-[12px] font-semibold text-ink-soft">
                  Nima noto'g'ri ekanini tanlang — savolning o'zi avtomatik biriktiriladi.
                </p>
              </div>
              <button
                onClick={onClose}
                className="w-8 h-8 shrink-0 rounded-full bg-cardline text-ink-soft font-extrabold"
                aria-label="Yopish"
              >
                ✕
              </button>
            </div>
            <div className="mt-3 space-y-2">
              {KINDS.map((k) => (
                <button
                  key={k.id}
                  onClick={() => setKind(k.id)}
                  className={`w-full rounded-2xl border-2 px-4 py-3 text-left text-[14px] font-bold transition-colors ${
                    kind === k.id ? "border-emerald-deep bg-emerald-deep/10 text-emerald-dark" : "border-cardline bg-card"
                  }`}
                >
                  {k.label}
                </button>
              ))}
            </div>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value.slice(0, 600))}
              placeholder="Izoh (ixtiyoriy): masalan, qaysi so'z xato o'qildi"
              rows={2}
              className="mt-3 w-full rounded-2xl bg-card border border-cardline px-3.5 py-2.5 text-[14px] font-semibold resize-none outline-none focus:border-emerald-deep/50"
            />
            {state === "error" && (
              <div className="mt-2 text-[12px] font-bold text-terracotta">Yuborilmadi — internetni tekshirib, qayta urinib ko'ring.</div>
            )}
            <button
              onClick={send}
              disabled={!kind || state === "sending"}
              className="mt-3 w-full rounded-2xl bg-emerald-deep py-3.5 text-[15px] font-extrabold text-white shadow-md active:scale-[0.98] transition-transform disabled:opacity-40"
            >
              {state === "sending" ? "Yuborilmoqda…" : "Yuborish"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
