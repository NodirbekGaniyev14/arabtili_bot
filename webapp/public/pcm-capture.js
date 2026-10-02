// K30 jonli suhbat: mikrofon → 16 kHz PCM16 mono bo'laklari (100 ms) — Gemini Live kirish formati.
// AudioWorklet (alohida audio oqimi — UI qotsa ham ovoz uzilmaydi). Telefon odatda 48 kHz beradi:
// chiziqli interpolyatsiya bilan 16 kHz ga o'tkaziladi, bloklar orasida uzilish bo'lmaydi.
// Asosiy oqimga: { pcm: ArrayBuffer (Int16, 1600 namuna), level: 0..1 (RMS) }.
const OUT_RATE = 16000;
const CHUNK = 1600;

class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / OUT_RATE;
    this.pos = 0; // keyingi chiqish namunasining joriy blokdagi (kasr) o'rni; -1 — oldingi blok oxiri
    this.prev = 0;
    this.out = new Int16Array(CHUNK);
    this.n = 0;
    this.sum = 0;
  }

  push(v) {
    const x = v > 1 ? 1 : v < -1 ? -1 : v;
    this.out[this.n++] = x < 0 ? x * 0x8000 : x * 0x7fff;
    this.sum += x * x;
    if (this.n === CHUNK) {
      const buf = this.out.slice(0, CHUNK).buffer;
      this.port.postMessage({ pcm: buf, level: Math.sqrt(this.sum / CHUNK) }, [buf]);
      this.n = 0;
      this.sum = 0;
    }
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch || !ch.length) return true;
    for (;;) {
      const i0 = Math.floor(this.pos);
      if (i0 + 1 >= ch.length) break;
      const f = this.pos - i0;
      const a = i0 < 0 ? this.prev : ch[i0];
      this.push(a * (1 - f) + ch[i0 + 1] * f);
      this.pos += this.ratio;
    }
    this.pos -= ch.length;
    this.prev = ch[ch.length - 1];
    return true;
  }
}

registerProcessor("pcm-capture", PcmCapture);
