/** ✍️ Dars YOZISH fazasi (K28) — bot yozganingizni o'qiydi.
 *
 *  Ilgari: faqat matn maydoni. «Daftaringizga yozing» topshiriqlarini (A0) bot ko'ra olmasdi, arab
 *  klaviaturasi yo'q o'quvchi yoza olmasdi, AI xatosi esa «AI baholash o'chiq» bo'lib jim qaytardi.
 *  Endi ikki yo'l: ⌨️ yozish (ekrandagi arab klaviaturasi bilan) yoki 📷 daftar surati. Natijada —
 *  bot nima o'qigani, to'g'ri varianti, izoh va maslahat; tuzatib qayta tekshirish mumkin. */

import { useEffect, useRef, useState } from "react";
import { api, type LessonV2Data, type LessonWritingResult } from "../../lib/api";
import { shrinkImage } from "../../lib/image";
import ArabicKeyboard from "./ArabicKeyboard";

const tg = () => window.Telegram?.WebApp;

/** Topshiriq qog'ozga yozishni so'raydimi (daftar, ko'chirish) — surat rejimi standart. */
export function isPaperTask(task: string): boolean {
  return /daftar|qog'oz|ko'chir/i.test(task);
}

export default function LessonWrite({ lesson, onNext }: { lesson: LessonV2Data; onNext: () => void }) {
  const task = lesson.skills.writing.task_uz;
  const aiOn = lesson.ai !== false;
  const [mode, setMode] = useState<"type" | "photo">(isPaperTask(task) ? "photo" : "type");
  const [text, setText] = useState("");
  const [kb, setKb] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<LessonWritingResult | null>(null);
  const [error, setError] = useState("");
  const camRef = useRef<HTMLInputElement>(null);
  const galRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!file) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const pick = (f: File | null | undefined) => {
    if (!f) return;
    const t = (f.type || "").toLowerCase();
    if (t && !t.startsWith("image/") && t !== "application/octet-stream") {
      setError("Faqat surat yuboring (JPG/PNG yoki kamera)");
      return;
    }
    setError("");
    setResult(null);
    setFile(f);
  };

  const ready = mode === "type" ? text.trim().length > 0 : !!file;

  const check = async () => {
    if (!ready || busy) return;
    setBusy(true);
    setError("");
    try {
      const r =
        mode === "photo" && file
          ? await api.evalWritingPhoto(lesson.id, await shrinkImage(file), "writing.jpg")
          : await api.evalWriting(lesson.id, text);
      if (!r.ai) {
        // AI ishlamadi (band / o'chiq) — sabab ko'rsatiladi, «Tekshirish» qayta bosiladigan bo'lib qoladi
        setError(r.feedback_uz);
        return;
      }
      setResult(r);
      tg()?.HapticFeedback?.notificationOccurred(r.ok ? "success" : "warning");
    } catch (e) {
      setError((e as { detail?: string })?.detail || "Tekshirib bo'lmadi — internetni tekshirib, qayta urinib ko'ring.");
    } finally {
      setBusy(false);
    }
  };

  const tab = (m: "type" | "photo", label: string) => (
    <button
      onClick={() => {
        setMode(m);
        setResult(null);
        setError("");
      }}
      className={`flex-1 h-10 rounded-xl text-[13px] font-extrabold transition-colors ${
        mode === m ? "bg-emerald-deep text-white" : "bg-card border border-cardline text-ink-soft"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="pt-4">
      <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2">✍️ YOZISH</div>
      <p className="text-sm font-semibold">{task}</p>

      {aiOn && (
        <div className="mt-3 flex gap-2">
          {tab("type", "⌨️ Yozaman")}
          {tab("photo", "📷 Daftardan surat")}
        </div>
      )}

      {mode === "type" || !aiOn ? (
        <>
          <textarea
            value={text}
            onChange={(e) => {
              setText(e.target.value.slice(0, 1000));
              setResult(null);
            }}
            dir="auto"
            rows={3}
            className="mt-3 w-full rounded-2xl border-2 border-emerald-deep/50 bg-card px-4 py-3 text-xl font-bold outline-none focus:border-emerald-deep font-arabic"
            placeholder="Shu yerga arab harflarida yozing..."
          />
          <button
            onClick={() => setKb((v) => !v)}
            className="mt-1 text-[12px] font-extrabold text-emerald-dark underline underline-offset-4"
          >
            {kb ? "Klaviaturani yopish" : "⌨️ Arab klaviaturasi (telefoningizda bo'lmasa)"}
          </button>
          {kb && (
            <ArabicKeyboard
              onChar={(ch) => {
                setText((v) => (v + ch).slice(0, 1000));
                setResult(null);
              }}
              onBackspace={() => {
                setText((v) => v.slice(0, -1));
                setResult(null);
              }}
            />
          )}
        </>
      ) : (
        <div className="mt-3">
          <input ref={camRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
          <input ref={galRef} type="file" accept="image/*,.heic,.heif" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
          {preview ? (
            <img src={preview} alt="Daftar surati" className="w-full max-h-72 object-contain rounded-2xl border border-cardline bg-card" />
          ) : (
            <div className="rounded-2xl border-2 border-dashed border-cardline bg-card p-5 text-center text-[13px] font-semibold text-ink-soft">
              Daftaringizga yozing, keyin sahifani <b>yorug' joyda, yaqindan va tekis</b> suratga oling.
            </div>
          )}
          <div className="mt-2 flex gap-2">
            <button onClick={() => camRef.current?.click()} className="flex-1 h-11 rounded-xl bg-gold-soft text-sm font-extrabold active:scale-95 transition-transform">
              📷 {file ? "Qayta suratga olish" : "Suratga olish"}
            </button>
            <button onClick={() => galRef.current?.click()} className="flex-1 h-11 rounded-xl bg-card border border-cardline text-sm font-extrabold active:scale-95 transition-transform">
              🖼 Galereyadan
            </button>
          </div>
        </div>
      )}

      {aiOn && !result && (
        <button
          onClick={() => void check()}
          disabled={!ready || busy}
          className="mt-3 w-full rounded-2xl bg-card border-2 border-emerald-deep py-3 font-extrabold text-emerald-dark disabled:opacity-40 active:scale-[0.98] transition-transform"
        >
          {busy ? (mode === "photo" ? "📖 Bot o'qiyapti…" : "🤖 Tekshirilmoqda…") : "🤖 Tekshirish"}
        </button>
      )}
      {error && (
        <div className="mt-3 rounded-2xl bg-gold-soft border border-gold/30 p-3 text-sm font-semibold">{error}</div>
      )}

      {result && (
        <div className="mt-3 rounded-2xl bg-card border border-cardline p-4 space-y-2.5">
          <div className="flex items-center justify-between gap-2">
            <span className="font-extrabold">
              {result.is_handwriting === false ? "📷 Yozuv ko'rinmadi" : result.ok ? "✅ To'g'ri!" : "✏️ Tuzatish kerak"}
            </span>
            {result.is_handwriting !== false && (
              <span
                className={`h-8 inline-flex items-center px-3 rounded-xl text-sm font-extrabold ${
                  (result.score ?? 0) >= 80 ? "bg-emerald-deep text-white" : (result.score ?? 0) >= 50 ? "bg-gold text-white" : "bg-terracotta text-white"
                }`}
              >
                {result.score ?? 0}%
              </span>
            )}
          </div>
          {result.read_ar && (
            <div>
              <div className="text-[11px] font-extrabold tracking-[0.1em] text-ink-soft">BOT O'QIDI</div>
              <div className="font-arabic text-xl leading-loose whitespace-pre-line" dir="rtl">
                {result.read_ar}
              </div>
            </div>
          )}
          {result.corrected_ar && (
            <div className="rounded-xl bg-emerald-deep/10 p-3">
              <div className="text-[11px] font-extrabold tracking-[0.1em] text-emerald-dark">TO'G'RI VARIANTI</div>
              <div className="font-arabic text-xl leading-loose whitespace-pre-line text-emerald-dark" dir="rtl">
                {result.corrected_ar}
              </div>
            </div>
          )}
          <p className="text-sm font-semibold leading-relaxed">🐪 {result.feedback_uz}</p>
          {(result.tips_uz ?? []).length > 0 && (
            <ul className="text-[13px] font-semibold text-ink-soft space-y-1">
              {(result.tips_uz ?? []).map((t, i) => (
                <li key={i}>💡 {t}</li>
              ))}
            </ul>
          )}
          <button
            onClick={() => setResult(null)}
            className="text-[12px] font-extrabold text-emerald-dark underline underline-offset-4"
          >
            ✏️ Tuzatib, qayta tekshirish
          </button>
        </div>
      )}

      <button
        onClick={() => {
          tg()?.HapticFeedback?.impactOccurred("light");
          onNext();
        }}
        disabled={busy}
        className="mt-6 w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-lg active:scale-[0.98] transition-transform disabled:opacity-50"
      >
        Keyingi
      </button>
    </div>
  );
}
