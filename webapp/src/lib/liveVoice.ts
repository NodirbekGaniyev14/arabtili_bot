/** K30 jonli ovozli suhbat — brauzer tomoni (server: backend/api/live.py, services/live_voice.py).
 *
 *  Mikrofon → AudioWorklet (/pcm-capture.js, 16 kHz PCM16, 100 ms bo'laklar) → WebSocket (binary) → server → Gemini Live.
 *  Javob: {type:"audio", data: base64 PCM16 24 kHz} → navbat bilan uziluvsiz ijro.
 *
 *  Yarim dupleks (standart): ustoz gapirayotganda mikrofon serverga YUBORILMAYDI — telefon karnayidagi ovoz
 *  mikrofonga qaytib, ustoz o'z gapini «eshitib» to'xtab qolmasin. O'quvchi «✋» bilan gapini bo'la oladi.
 */

export type LiveState = "connecting" | "listening" | "speaking" | "ended";

export type LiveEnd = { reason: string; seconds: number; sessionId: number };

export type LiveHandlers = {
  onState: (s: LiveState) => void;
  onUserText: (t: string) => void;
  onModelText: (t: string) => void;
  onTurn: () => void;
  onLevel?: (v: number) => void;
  onReady?: (maxSeconds: number) => void;
  onEnd: (e: LiveEnd) => void;
  onError: (detail: string, code: string) => void;
};

const OUT_RATE = 24000;
const TAIL_MS = 350; // ustoz ovozi tugagach mikrofonni shuncha kechikib qayta yoqamiz (aks-sado so'nsin)

export function liveSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof WebSocket !== "undefined" &&
    typeof AudioWorkletNode !== "undefined"
  );
}

function wsUrl(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/api/v2/live/ws`;
}

function pcm16ToFloat(b64: string): Float32Array {
  const bin = atob(b64);
  const n = bin.length >> 1;
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    let v = bin.charCodeAt(2 * i) | (bin.charCodeAt(2 * i + 1) << 8);
    if (v >= 0x8000) v -= 0x10000;
    out[i] = v / 0x8000;
  }
  return out;
}

export class LiveCall {
  private ws: WebSocket | null = null;
  private stream: MediaStream | null = null;
  private micCtx: AudioContext | null = null;
  private playCtx: AudioContext | null = null;
  private node: AudioWorkletNode | null = null;
  private sources: AudioBufferSourceNode[] = [];
  private nextTime = 0;
  private muteUntil = 0;
  private ready = false;
  private finished = false;
  private state: LiveState = "connecting";
  private endTimer = 0;

  constructor(private h: LiveHandlers, private halfDuplex = true) {}

  private setState(s: LiveState) {
    if (this.state === s || this.finished) return;
    this.state = s;
    this.h.onState(s);
  }

  /** Foydalanuvchi bosganda chaqiriladi (iOS: AudioContext faqat bosish ichida yaratilsa ovoz chiqaradi). */
  async start(topicId: string): Promise<void> {
    const AC: typeof AudioContext =
      window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    this.playCtx = new AC();
    void this.playCtx.resume();
    this.h.onState("connecting");
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch {
      this.fail("Mikrofonga ruxsat berilmadi — Telegram sozlamalarida mikrofonni yoqing", "mic");
      return;
    }
    try {
      this.micCtx = new AC();
      await this.micCtx.audioWorklet.addModule("/pcm-capture.js");
      const src = this.micCtx.createMediaStreamSource(this.stream);
      this.node = new AudioWorkletNode(this.micCtx, "pcm-capture");
      const mute = this.micCtx.createGain();
      mute.gain.value = 0; // grafda bo'lishi uchun (ba'zi brauzerlar chiqishsiz tugunni ishlatmaydi), ovoz chiqmaydi
      src.connect(this.node);
      this.node.connect(mute);
      mute.connect(this.micCtx.destination);
      this.node.port.onmessage = (e: MessageEvent<{ pcm: ArrayBuffer; level: number }>) => this.onMic(e.data);
    } catch {
      this.fail("Bu qurilmada jonli suhbat ishlamaydi (audio modul yuklanmadi)", "audio");
      return;
    }

    const ws = new WebSocket(wsUrl());
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    ws.onopen = () =>
      ws.send(JSON.stringify({ type: "start", init_data: window.Telegram?.WebApp.initData ?? "", topic_id: topicId }));
    ws.onmessage = (e) => this.onServer(e.data);
    ws.onclose = () => {
      if (!this.finished) this.fail("Aloqa uzildi. Qayta urinib ko'ring.", "closed");
    };
  }

  private onMic(d: { pcm: ArrayBuffer; level: number }) {
    this.h.onLevel?.(this.isSpeaking() ? 0 : d.level);
    if (!this.ready || this.ws?.readyState !== WebSocket.OPEN) return;
    if (this.halfDuplex && (this.isSpeaking() || performance.now() < this.muteUntil)) return;
    this.ws.send(d.pcm);
  }

  private isSpeaking(): boolean {
    return this.sources.length > 0;
  }

  private onServer(raw: unknown) {
    if (typeof raw !== "string") return;
    let m: { type: string; [k: string]: unknown };
    try {
      m = JSON.parse(raw);
    } catch {
      return;
    }
    switch (m.type) {
      case "ready":
        this.ready = true;
        this.h.onReady?.(Number(m.max_seconds) || 0);
        this.setState("listening");
        break;
      case "audio":
        this.play(String(m.data ?? ""));
        break;
      case "in":
        this.h.onUserText(String(m.text ?? ""));
        break;
      case "out":
        this.h.onModelText(String(m.text ?? ""));
        break;
      case "turn":
        this.h.onTurn();
        break;
      case "interrupted":
        this.stopPlayback();
        break;
      case "error":
        this.fail(String(m.detail ?? "Xatolik"), String(m.code ?? "error"));
        break;
      case "end":
        this.finish({ reason: String(m.reason ?? ""), seconds: Number(m.seconds) || 0, sessionId: Number(m.session_id) || 0 });
        break;
    }
  }

  private play(b64: string) {
    const ctx = this.playCtx;
    if (!ctx || !b64) return;
    const samples = pcm16ToFloat(b64);
    if (!samples.length) return;
    const buf = ctx.createBuffer(1, samples.length, OUT_RATE);
    buf.getChannelData(0).set(samples);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    const at = Math.max(ctx.currentTime + 0.04, this.nextTime);
    src.start(at);
    this.nextTime = at + buf.duration;
    this.sources.push(src);
    this.setState("speaking");
    src.onended = () => {
      this.sources = this.sources.filter((s) => s !== src);
      if (!this.sources.length) {
        this.muteUntil = performance.now() + TAIL_MS;
        this.setState("listening");
      }
    };
  }

  private stopPlayback() {
    for (const s of this.sources) {
      try {
        s.onended = null;
        s.stop();
      } catch {
        /* allaqachon to'xtagan */
      }
    }
    this.sources = [];
    this.nextTime = 0;
    this.muteUntil = performance.now() + 150;
    this.setState("listening");
  }

  /** «✋» — ustoz gapini to'xtatib, o'quvchi gapira boshlaydi. */
  interrupt() {
    this.stopPlayback();
  }

  /** «Yakunlash» — server suhbatni saqlab {type:"end"} qaytaradi (3 s ichida kelmasa ham yopamiz). */
  end() {
    if (this.finished) return;
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "end" }));
      this.endTimer = window.setTimeout(() => this.finish({ reason: "user", seconds: 0, sessionId: 0 }), 4000);
    } else {
      this.finish({ reason: "user", seconds: 0, sessionId: 0 });
    }
    this.stopPlayback();
  }

  private finish(e: LiveEnd) {
    if (this.finished) return;
    this.cleanup();
    this.finished = true;
    this.state = "ended";
    this.h.onState("ended");
    this.h.onEnd(e);
  }

  private fail(detail: string, code: string) {
    if (this.finished) return;
    this.cleanup();
    this.finished = true;
    this.state = "ended";
    this.h.onError(detail, code);
  }

  cleanup() {
    window.clearTimeout(this.endTimer);
    this.stopPlaybackSilently();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    if (this.node) this.node.port.onmessage = null;
    void this.micCtx?.close().catch(() => undefined);
    void this.playCtx?.close().catch(() => undefined);
    this.micCtx = null;
    this.playCtx = null;
    const ws = this.ws;
    this.ws = null;
    if (ws) {
      ws.onclose = null;
      try {
        ws.close();
      } catch {
        /* jim */
      }
    }
  }

  private stopPlaybackSilently() {
    for (const s of this.sources) {
      try {
        s.onended = null;
        s.stop();
      } catch {
        /* jim */
      }
    }
    this.sources = [];
  }
}
