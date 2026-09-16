import { useState } from "react";
import { api } from "../lib/api";

/** Sifat halqasi (K18.2): suhbat/mock/kunlik savol/talaffuz yakunida 👍/👎.
 *  👎 bo'lsa ixtiyoriy izoh so'raladi — adminga mavzu/daraja bilan boradi.
 *  Suhbat matni saqlanmaydi, shuning uchun bu yagona sifat signali. */

interface Props {
  sessionKey: string;
  mode: "chat" | "mock" | "daily" | "drill";
  topic?: string;
  question?: string;
}

export default function RateBar({ sessionKey, mode, topic = "", question = "Ustoz qanday edi?" }: Props) {
  const [choice, setChoice] = useState<boolean | null>(null);
  const [comment, setComment] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const send = async (good: boolean, text = "") => {
    setBusy(true);
    try {
      await api.tutorRate({ session_key: sessionKey, mode, topic, good, comment: text });
      if (good || text) setSent(true);
    } catch {
      /* baho — muhim emas, jim */
    } finally {
      setBusy(false);
    }
  };

  const pick = (good: boolean) => {
    setChoice(good);
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred("light");
    send(good);
  };

  if (sent) {
    return (
      <div className="rounded-2xl bg-card border border-cardline px-4 py-3 text-sm font-semibold text-ink-soft text-center">
        {choice ? "Rahmat! 🌟" : "Rahmat — yaxshilaymiz 🙏"}
      </div>
    );
  }

  return (
    <div className="rounded-2xl bg-card border border-cardline p-3.5 space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-extrabold">{question}</div>
        <div className="flex gap-2 shrink-0">
          <button
            onClick={() => pick(true)}
            disabled={busy}
            className={`w-11 h-11 rounded-xl text-xl active:scale-90 transition-transform ${
              choice === true ? "bg-emerald-deep" : "bg-sand border border-cardline"
            }`}
            aria-label="Yoqdi"
          >
            👍
          </button>
          <button
            onClick={() => pick(false)}
            disabled={busy}
            className={`w-11 h-11 rounded-xl text-xl active:scale-90 transition-transform ${
              choice === false ? "bg-terracotta" : "bg-sand border border-cardline"
            }`}
            aria-label="Yoqmadi"
          >
            👎
          </button>
        </div>
      </div>
      {choice === false && (
        <div className="space-y-2">
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            maxLength={400}
            rows={2}
            placeholder="Nima yoqmadi? (ixtiyoriy) — xato tuzatish, tushunarsiz javob, sekin…"
            className="w-full rounded-xl bg-sand border border-cardline px-3 py-2 text-sm font-semibold outline-none focus:border-emerald-deep/40"
          />
          <div className="flex gap-2">
            <button
              onClick={() => send(false, comment.trim())}
              disabled={busy}
              className="flex-1 rounded-xl bg-emerald-deep py-2 text-sm font-extrabold text-white active:scale-95 transition-transform disabled:opacity-50"
            >
              Yuborish
            </button>
            <button
              onClick={() => setSent(true)}
              className="rounded-xl bg-card border border-cardline px-4 py-2 text-sm font-extrabold text-ink-soft"
            >
              O'tkazish
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
