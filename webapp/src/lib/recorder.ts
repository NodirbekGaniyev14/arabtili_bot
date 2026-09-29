/** Mikrofon yozuvi (MediaRecorder) — AI ustoz speaking mashqi uchun.
 *
 * Telegram WebView: Android (Chrome) webm/opus, iOS (WKWebView) mp4/aac.
 * Qaysi format qo'llansa — shu tanlanadi; server (Whisper) ikkalasini ham
 * to'g'ridan-to'g'ri qabul qiladi, konvertatsiya kerak emas.
 */

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
  "audio/aac",
];

/** Xavfsizlik chegarasi (yuklash hajmi / STT narxi) — UI'da ko'rsatilmaydi; o'quvchilar odatda 25–40 s gapiradi. */
export const MAX_SECONDS = 90;

export interface Recording {
  blob: Blob;
  filename: string;
  seconds: number;
  /** K28: yozuvdagi eng baland ovoz (RMS, 0..1); -1 — o'lchanmadi (eski WebView) */
  peak: number;
}

/** K28: shundan past — raqamli jimlik (mikrofon o'chiq / boshqa ilova band qilgan), STT'ga yuborilmaydi.
 *  Xona shovqini (AGC bilan) doim ancha baland, shuning uchun gapirgan o'quvchi hech qachon bu yerga tushmaydi. */
export const SILENT_PEAK = 0.002;

/** Yozuv jim edimi — «bot eshitmadi» o'rniga aniq sabab ko'rsatiladi (STT limiti ham tejaladi):
 *  balandlik o'lchangan va deyarli nol, YOKI 1 soniyadan uzun yozuv 1 KB dan kichik (kodek jimlikni
 *  siqib yuborgan — mikrofon ovoz bermagan). */
export function isSilent(rec: Recording): boolean {
  return (rec.peak >= 0 && rec.peak < SILENT_PEAK) || (rec.seconds >= 1 && rec.blob.size < 1000);
}

export const SILENT_MSG =
  "🔇 Mikrofon ovoz olmadi. Telegram'ga mikrofon ruxsatini bering (telefon sozlamalari → Telegram → Mikrofon) va boshqa ilova mikrofonni band qilmaganini tekshiring.";

export function micSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== "undefined"
  );
}

function pickMime(): string {
  if (typeof MediaRecorder === "undefined") return "";
  for (const m of MIME_CANDIDATES) {
    try {
      if (MediaRecorder.isTypeSupported(m)) return m;
    } catch {
      /* eski brauzer */
    }
  }
  return "";
}

function extFor(mime: string): string {
  if (mime.includes("mp4")) return "m4a";
  if (mime.includes("ogg")) return "ogg";
  if (mime.includes("aac")) return "aac";
  return "webm";
}

export class Recorder {
  private rec: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: BlobPart[] = [];
  private startedAt = 0;
  private timer: number | null = null;
  private resolve: ((r: Recording | null) => void) | null = null;
  // K28: ovoz balandligi — UI ko'rsatkichi va jim yozuvni aniqlash
  private ctx: AudioContext | null = null;
  private meter: number | null = null;
  private peak = -1;
  /** Joriy balandlik 0..1 (yozish paytida UI shkalasi uchun) */
  level = 0;

  get active(): boolean {
    return !!this.rec && this.rec.state === "recording";
  }

  /** Balandlik o'lchanyaptimi (UI «ovoz sezilmayapti» ogohlantirishini faqat shunda ko'rsatadi) */
  get metering(): boolean {
    return !!this.ctx && this.ctx.state === "running";
  }

  /** Mikrofon balandligini o'lchash (AnalyserNode). Ishlamasa — jim o'tadi (peak = -1, yozuv baribir ketadi). */
  private startMeter() {
    try {
      const AC =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AC || !this.stream) return;
      const ctx = new AC();
      const an = ctx.createAnalyser();
      an.fftSize = 1024;
      ctx.createMediaStreamSource(this.stream).connect(an);
      void ctx.resume?.();
      const buf = new Uint8Array(an.fftSize);
      this.ctx = ctx;
      this.meter = window.setInterval(() => {
        // To'xtatilgan (suspended) kontekst nol beradi — bunday o'lchov hisobga olinmaydi
        if (ctx.state !== "running") return;
        an.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) {
          const v = (buf[i] - 128) / 128;
          sum += v * v;
        }
        const rms = Math.sqrt(sum / buf.length);
        this.level = Math.min(1, rms * 6);
        this.peak = Math.max(this.peak, rms);
      }, 100);
    } catch {
      this.peak = -1;
    }
  }

  private stopMeter() {
    if (this.meter) window.clearInterval(this.meter);
    this.meter = null;
    this.level = 0;
    try {
      void this.ctx?.close();
    } catch {
      /* allaqachon yopilgan */
    }
    this.ctx = null;
  }

  /** Yozishni boshlaydi. Ruxsat berilmasa xato tashlaydi. `maxSeconds` — avto-to'xtash (standart 90 s). */
  async start(onAutoStop?: () => void, maxSeconds = MAX_SECONDS): Promise<void> {
    if (this.active) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true, // past ovozli o'quvchi — kuchaytiriladi
        channelCount: 1,
      },
    });
    const mime = pickMime();
    this.rec = mime
      ? new MediaRecorder(this.stream, { mimeType: mime, audioBitsPerSecond: 48000 })
      : new MediaRecorder(this.stream);
    this.chunks = [];
    this.rec.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) this.chunks.push(e.data);
    };
    this.rec.onstop = () => this.finish();
    this.startedAt = Date.now();
    this.peak = -1;
    this.rec.start(250);
    this.startMeter();
    // Uzun yozuv — limit; Whisper narxi va yuklash hajmi nazorati
    this.timer = window.setTimeout(() => {
      if (this.active) {
        this.stop();
        onAutoStop?.();
      }
    }, Math.min(maxSeconds, MAX_SECONDS) * 1000);
  }

  /** To'xtatadi va yozuvni qaytaradi (juda qisqa bo'lsa null).
   *  `tailMs` — tugma qo'yib yuborilgach oxirgi bo'g'in kesilmasin deb biroz kutiladi. */
  stop(tailMs = 300): Promise<Recording | null> {
    return new Promise((resolve) => {
      if (!this.rec || this.rec.state === "inactive") {
        this.cleanup();
        resolve(null);
        return;
      }
      this.resolve = resolve;
      const rec = this.rec;
      const doStop = () => {
        try {
          if (rec.state !== "inactive") rec.stop();
        } catch {
          this.cleanup();
          resolve(null);
        }
      };
      if (tailMs > 0) window.setTimeout(doStop, tailMs);
      else doStop();
    });
  }

  private finish() {
    const seconds = (Date.now() - this.startedAt) / 1000;
    const mime = this.rec?.mimeType || "audio/webm";
    const blob = new Blob(this.chunks, { type: mime });
    const res = this.resolve;
    const peak = this.peak;
    this.cleanup();
    // 0.4 s dan qisqa — tasodifiy bosish. 1 s dan uzun, lekin bo'm-bo'sh yozuv — null emas (isSilent aniqlaydi)
    res?.(seconds < 0.4 || (blob.size < 1000 && seconds < 1) ? null : {
      blob,
      filename: `speech.${extFor(mime)}`,
      seconds,
      peak,
    });
  }

  private cleanup() {
    this.stopMeter();
    if (this.timer) window.clearTimeout(this.timer);
    this.timer = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.rec = null;
    this.resolve = null;
  }
}
