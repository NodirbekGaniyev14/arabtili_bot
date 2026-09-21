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
}

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

  get active(): boolean {
    return !!this.rec && this.rec.state === "recording";
  }

  /** Yozishni boshlaydi. Ruxsat berilmasa xato tashlaydi. */
  async start(onAutoStop?: () => void): Promise<void> {
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
    this.rec.start(250);
    // Uzun yozuv — limit; Whisper narxi va yuklash hajmi nazorati
    this.timer = window.setTimeout(() => {
      if (this.active) {
        this.stop();
        onAutoStop?.();
      }
    }, MAX_SECONDS * 1000);
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
    this.cleanup();
    // 0.4 s dan qisqa — tasodifiy bosish
    res?.(seconds < 0.4 || blob.size < 1000 ? null : {
      blob,
      filename: `speech.${extFor(mime)}`,
      seconds,
    });
  }

  private cleanup() {
    if (this.timer) window.clearTimeout(this.timer);
    this.timer = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.rec = null;
    this.resolve = null;
  }
}
