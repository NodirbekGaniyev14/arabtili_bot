import { useEffect, useRef, useState } from "react";
import BadgeToast from "../components/BadgeToast";
import type { Badge } from "../lib/api";
import { api, type WritingCheck, type WritingInfo } from "../lib/api";
import { playUrl, speakText } from "../lib/audio";

/** ✍️ Yozuv (xattotlik) mashqi (K19.2) — 2 kunda bir matn, hamma uchun bepul.
 *
 *  Matn darajaga mos (content/writing_texts.json): so'zlar / jumlalar / hikoya /
 *  maqol / she'r. O'quvchi qog'ozga ko'chiradi → «Yozdim» → kamera → surat
 *  telefonda kichraytiriladi → AI (vision) asl matn bilan solishtiradi: aniqlik,
 *  tushib qolgan / xato so'zlar (asl matnda belgilanadi), ozodalik, maslahatlar.
 *  Davrda 3 urinish, XP birinchi tekshiruvda. Surat serverda saqlanmaydi. */

const tg = () => window.Telegram?.WebApp;
const MAX_SIDE = 1600;

interface Props {
  onClose: () => void;
  onDone?: () => void;
}

/** Brauzer dekod qila olmagan formatlar (Android'da HEIC) uchun <img> orqali urinish. */
function decodeViaImg(file: File): Promise<ImageBitmap | HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("decode"));
    };
    img.src = url;
  });
}

/** Suratni yuklashdan oldin telefonda kichraytirish (mobil internet, tezlik) va JPEG'ga o'tkazish
 *  (#F84: telefon HEIC/WebP bersa ham serverga JPEG boradi; dekod bo'lmasa asl fayl — server o'qiydi). */
async function shrink(file: File): Promise<Blob> {
  try {
    let src: ImageBitmap | HTMLImageElement;
    try {
      src = await createImageBitmap(file);
    } catch {
      src = await decodeViaImg(file);
    }
    const w = "naturalWidth" in src ? src.naturalWidth : src.width;
    const h = "naturalHeight" in src ? src.naturalHeight : src.height;
    const scale = Math.min(1, MAX_SIDE / Math.max(w, h));
    const isJpeg = file.type === "image/jpeg" || file.type === "image/png";
    if (scale === 1 && file.size < 1_500_000 && isJpeg) return file;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(w * scale);
    canvas.height = Math.round(h * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(src, 0, 0, canvas.width, canvas.height);
    return await new Promise<Blob>((resolve) =>
      canvas.toBlob((b) => resolve(b ?? file), "image/jpeg", 0.85)
    );
  } catch {
    return file; // eski WebView / HEIC — server o'zi o'qiydi va kichraytiradi
  }
}

/** Solishtirish uchun: harakat, tatvil va tinish belgilarisiz (model harakatsiz qaytarishi mumkin). */
function norm(w: string): string {
  return w.replace(/[ً-ْٰـ]/g, "").replace(/[·.،؟!«»"'“”()]/g, "").trim();
}

function scoreClass(s: number) {
  return s >= 85 ? "bg-emerald-deep text-white" : s >= 60 ? "bg-gold text-white" : "bg-terracotta text-white";
}

const KIND_LABEL: Record<string, string> = {
  "so'zlar": "So'zlar", matn: "Matn", hikoya: "Hikoya", maqol: "Maqollar", "she'r": "She'r", xat: "Xat",
};

export default function Writing({ onClose, onDone }: Props) {
  const [badges, setBadges] = useState<Badge[]>([]);
  const [info, setInfo] = useState<WritingInfo | null>(null);
  const [error, setError] = useState("");
  const [showTranslit, setShowTranslit] = useState(false);
  const [showUz, setShowUz] = useState(true); // tarjima standart ochiq (foydalanuvchi fikri #F59)
  const [preview, setPreview] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<WritingCheck | null>(null);
  const [attemptsLeft, setAttemptsLeft] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const galleryRef = useRef<HTMLInputElement>(null); // #F84: galereyadan (capture'siz)

  useEffect(() => {
    api
      .getWriting()
      .then((d) => {
        setInfo(d);
        setAttemptsLeft(d.attempts_left);
      })
      .catch(() => setError("Matn yuklanmadi. Qayta urinib ko'ring."));
  }, []);

  useEffect(() => {
    if (!file) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const listen = async () => {
    if (!info) return;
    const ok = info.text.audio_url ? await playUrl(info.text.audio_url) : false;
    if (!ok) speakText(info.text.ar.replace(/\n/g, ". "));
  };

  const pick = (f: File | null) => {
    if (!f) return;
    // Tur bo'sh bo'lishi mumkin (Android galereya) — server baytlardan aniqlaydi; faqat aniq video/pdf rad
    const t = (f.type || "").toLowerCase();
    if (t && !t.startsWith("image/") && t !== "application/octet-stream") {
      setError(t.startsWith("video/") ? "Bu video — yozuvning suratini yuboring" : "Faqat surat (JPG/PNG yoki kamera)");
      return;
    }
    setError("");
    setFile(f);
    setResult(null);
  };

  const check = async () => {
    if (!file || checking) return;
    setChecking(true);
    setError("");
    try {
      const blob = await shrink(file);
      const r = await api.checkWriting(blob, blob === file ? file.name : "writing.jpg");
      setResult(r);
      setBadges(r.new_badges ?? []);
      setAttemptsLeft(r.attempts_left);
      setInfo((i) => (i ? { ...i, done: { ...r }, attempts_left: r.attempts_left } : i));
      tg()?.HapticFeedback?.notificationOccurred(r.result.accuracy >= 60 ? "success" : "warning");
      onDone?.();
    } catch (e) {
      setError((e as { detail?: string })?.detail || "Tekshirib bo'lmadi. Qayta urinib ko'ring.");
    } finally {
      setChecking(false);
    }
  };

  const text = info?.text;
  const lines = text ? text.ar.split("\n") : [];
  const best = info?.done;
  const shown = result?.result ?? (best ? { ...best, accuracy: best.score } : null);
  const wrongSet = new Set((shown?.wrong_words ?? []).map((w) => norm(w.correct)));
  const missingSet = new Set((shown?.missing_words ?? []).map(norm));
  const anyMark = lines.some((line) => line.split(" ").some((w) => wrongSet.has(norm(w)) || missingSet.has(norm(w))));

  return (
    <div className="fixed inset-0 z-50 bg-sand flex flex-col max-w-md mx-auto">
      <BadgeToast badges={badges} />
      <div className="flex items-center justify-between px-4 py-3 border-b border-cardline bg-card">
        <div className="min-w-0">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
            ✍️ YOZUV MASHQI{info ? ` · ${info.level}` : ""}
          </div>
          <div className="font-extrabold truncate">
            {text ? text.title_uz : "Yuklanmoqda…"}
            {text && <span className="ml-2 text-[11px] font-bold text-ink-soft">{KIND_LABEL[text.kind] ?? text.kind}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {info && (
            <span className="rounded-full bg-gold-soft px-2.5 py-1 text-[11px] font-extrabold" title="Yangi matn kuni">
              📅 {info.ends.slice(8, 10)}.{info.ends.slice(5, 7)} gacha
            </span>
          )}
          <button onClick={onClose} className="w-9 h-9 rounded-full bg-cardline text-ink-soft font-extrabold">
            ✕
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3 pb-10">
        {error && (
          <div className="rounded-2xl bg-terracotta/10 border border-terracotta/30 px-4 py-3 text-sm font-semibold">{error}</div>
        )}

        {/* Matn */}
        {text && (
          <section className="rounded-3xl bg-card border border-cardline p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">MATN — QOG'OZGA KO'CHIRING</div>
              <div className="flex gap-1.5">
                <button onClick={listen} className="rounded-lg bg-gold-soft px-2.5 py-1 text-[11px] font-extrabold active:scale-95 transition-transform">
                  🔊
                </button>
                <button
                  onClick={() => setShowTranslit((v) => !v)}
                  className={`rounded-lg px-2.5 py-1 text-[11px] font-extrabold ${showTranslit ? "bg-emerald-deep text-white" : "bg-cardline text-ink-soft"}`}
                >
                  Translit
                </button>
                <button
                  onClick={() => setShowUz((v) => !v)}
                  className={`rounded-lg px-2.5 py-1 text-[11px] font-extrabold ${showUz ? "bg-emerald-deep text-white" : "bg-cardline text-ink-soft"}`}
                >
                  Tarjima
                </button>
              </div>
            </div>
            <div className="font-arabic text-[30px] leading-[2] text-ink" dir="rtl">
              {lines.map((line, i) => (
                <div key={i}>
                  {line.split(" ").map((w, j) => {
                    const bare = norm(w);
                    const wrong = !!shown && !!bare && wrongSet.has(bare);
                    const missing = !!shown && !!bare && missingSet.has(bare);
                    return (
                      <span
                        key={j}
                        className={
                          missing
                            ? "text-terracotta underline decoration-2 decoration-dotted"
                            : wrong
                              ? "text-gold underline decoration-2"
                              : ""
                        }
                      >
                        {w}{" "}
                      </span>
                    );
                  })}
                </div>
              ))}
            </div>
            {showTranslit && (
              <div className="mt-2 text-[13px] italic text-ink-soft font-semibold">{text.translit}</div>
            )}
            {showUz && (
              <div className="mt-2 text-[13px] text-ink font-semibold whitespace-pre-line">{text.uz}</div>
            )}
            {text.hint_uz && (
              <div className="mt-3 rounded-2xl bg-gold-soft px-3 py-2 text-[12px] font-semibold">💡 {text.hint_uz}</div>
            )}
            {anyMark && (
              <div className="mt-2 text-[11px] font-semibold text-ink-soft">
                <span className="text-gold">sariq</span> — xato yozilgan · <span className="text-terracotta">qizil</span> — tushib qolgan
              </div>
            )}
          </section>
        )}

        {/* Natija */}
        {shown && (
          <section className="rounded-3xl bg-card border border-cardline p-4 space-y-3">
            <div className="flex items-center gap-3">
              <div className={`rounded-2xl px-3 py-2 text-2xl font-extrabold ${scoreClass(shown.accuracy)}`}>
                {shown.accuracy}%
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-extrabold">
                  {shown.accuracy >= 85 ? "A'lo yozuv!" : shown.accuracy >= 60 ? "Yaxshi, oz qoldi" : shown.accuracy > 0 ? "Yana mashq kerak" : "Surat mos kelmadi"}
                </div>
                <div className="text-[12px] text-ink-soft font-semibold">
                  Ozodalik: {"★".repeat(shown.neatness)}{"☆".repeat(Math.max(5 - shown.neatness, 0))}
                  {result?.xp_awarded ? ` · +${result.xp_awarded} XP` : best?.xp ? ` · ${best.xp} XP olingan` : ""}
                  {result && result.result.accuracy < (best?.score ?? 0) ? ` · eng yaxshi ${best?.score}%` : ""}
                </div>
              </div>
            </div>
            {shown.praise_uz && <div className="text-sm font-semibold">🌟 {shown.praise_uz}</div>}
            {shown.read_ar && shown.is_handwriting && (
              <div>
                <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">AI O'QIDI</div>
                <div className="font-arabic text-xl leading-relaxed whitespace-pre-line" dir="rtl">{shown.read_ar}</div>
              </div>
            )}
            {shown.wrong_words.length > 0 && (
              <div className="space-y-1">
                <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">XATO SO'ZLAR</div>
                {shown.wrong_words.map((w, i) => (
                  <div key={i} className="flex items-center gap-2 rounded-xl bg-sand px-3 py-2 text-sm">
                    <span className="font-arabic text-lg text-terracotta line-through" dir="rtl">{w.written}</span>
                    <span className="text-ink-soft">→</span>
                    <span className="font-arabic text-lg text-emerald-dark" dir="rtl">{w.correct}</span>
                    <span className="ml-auto text-[11px] font-semibold text-ink-soft text-right">{w.note_uz}</span>
                  </div>
                ))}
              </div>
            )}
            {shown.missing_words.length > 0 && (
              <div className="text-sm font-semibold">
                <span className="text-ink-soft">Tushib qolgan: </span>
                <span className="font-arabic text-lg" dir="rtl">{shown.missing_words.join(" · ")}</span>
              </div>
            )}
            {shown.tips_uz.length > 0 && (
              <div className="space-y-1">
                <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">MASLAHATLAR</div>
                {shown.tips_uz.map((t, i) => (
                  <div key={i} className="text-sm font-semibold">✍️ {t}</div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* Qadamlar + kamera */}
        {info && (
          <section className="space-y-2">
            {!shown && (
              <div className="grid grid-cols-3 gap-2">
                {[["✍️", "Qog'ozga yozing"], ["📷", "Suratga oling"], ["🤖", "AI tekshiradi"]].map(([ic, t], i) => (
                  <div key={i} className="rounded-2xl bg-card border border-cardline p-3 text-center">
                    <div className="text-2xl">{ic}</div>
                    <div className="text-[11px] font-extrabold mt-1">{i + 1}. {t}</div>
                  </div>
                ))}
              </div>
            )}
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              capture="environment"
              hidden
              onChange={(e) => pick(e.target.files?.[0] ?? null)}
            />
            {/* #F84: oldin olingan surat — galereyadan (capture'siz) */}
            <input
              ref={galleryRef}
              type="file"
              accept="image/*,.heic,.heif"
              hidden
              onChange={(e) => pick(e.target.files?.[0] ?? null)}
            />
            {preview && !result && (
              <img
                src={preview}
                alt="Yozuv"
                className="w-full max-h-64 rounded-2xl object-contain bg-card border border-cardline"
                // HEIC'ni brauzer ko'rsata olmasa — surat baribir tanlangan, server o'qiydi
                onError={(e) => {
                  e.currentTarget.style.display = "none";
                  setError("");
                }}
              />
            )}
            {attemptsLeft > 0 ? (
              <>
                {!file || result ? (
                  <div className="space-y-2">
                    <button
                      onClick={() => {
                        tg()?.HapticFeedback?.impactOccurred("medium");
                        fileRef.current?.click();
                      }}
                      className="w-full rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-[15px] active:scale-[0.98] transition-transform"
                    >
                      {result || best ? "📷 Qayta suratga olish" : "✅ Yozdim — suratga olish"}
                    </button>
                    <button
                      onClick={() => galleryRef.current?.click()}
                      className="w-full rounded-2xl bg-card border border-cardline py-3 text-[13px] font-extrabold text-ink-soft active:scale-[0.98] transition-transform"
                    >
                      🖼 Galereyadan tanlash
                    </button>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <button
                      onClick={() => fileRef.current?.click()}
                      className="rounded-2xl bg-card border border-cardline px-4 py-4 text-sm font-extrabold text-ink-soft"
                    >
                      Boshqa
                    </button>
                    <button
                      onClick={check}
                      disabled={checking}
                      className="flex-1 rounded-2xl bg-emerald-deep py-4 text-white font-extrabold text-[15px] active:scale-[0.98] transition-transform disabled:opacity-60"
                    >
                      {checking ? "🤖 Tekshirilmoqda… (5–10 s)" : "🤖 Tekshirish"}
                    </button>
                  </div>
                )}
                <div className="text-center text-[11px] text-ink-soft font-semibold">
                  {attemptsLeft} urinish qoldi · {info.ai ? "AI tekshiradi, surat saqlanmaydi" : "AI hozircha o'chiq"}
                </div>
              </>
            ) : (
              <div className="rounded-2xl bg-card border border-cardline p-4 text-center text-sm font-semibold text-ink-soft">
                Bu matn uchun urinishlar tugadi. Yangi matn — {info.ends.slice(8, 10)}.{info.ends.slice(5, 7)} dan keyin ✍️
              </div>
            )}
          </section>
        )}

        {/* Tarix */}
        {info && info.history.length > 0 && (
          <section className="rounded-3xl bg-card border border-cardline p-4">
            <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft mb-2">OLDINGI MASHQLAR</div>
            <div className="space-y-1.5">
              {info.history.map((h) => (
                <div key={h.period} className="flex items-center justify-between text-sm">
                  <span className="font-semibold truncate">
                    <span className="text-ink-soft">{h.period.slice(8, 10)}.{h.period.slice(5, 7)}</span> · {h.title}
                  </span>
                  <span className={`shrink-0 rounded-lg px-2 py-0.5 text-[12px] font-extrabold ${scoreClass(h.score)}`}>{h.score}%</span>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
