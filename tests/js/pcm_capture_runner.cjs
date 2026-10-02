// webapp/public/pcm-capture.js (AudioWorklet) ni node'da sinaydi (tests/test_live_voice_client.py).
// stdin: {"rate": 48000, "seconds": 1, "freq": 440} → stdout: {"chunks", "samples", "crossings", "maxAbs", "level"}
const fs = require("fs");
const path = require("path");

const cfg = JSON.parse(fs.readFileSync(0, "utf8"));
const posted = [];
let Proc = null;
class AudioWorkletProcessor {
  constructor() {
    this.port = { postMessage: (m) => posted.push(m) };
  }
}
const src = fs.readFileSync(path.resolve(__dirname, "..", "..", "webapp", "public", "pcm-capture.js"), "utf8");
new Function("AudioWorkletProcessor", "registerProcessor", "sampleRate", src)(
  AudioWorkletProcessor,
  (name, cls) => (Proc = cls),
  cfg.rate
);
const p = new Proc();
const total = Math.round(cfg.rate * cfg.seconds);
for (let start = 0; start < total; start += 128) {
  const n = Math.min(128, total - start);
  const block = new Float32Array(n);
  for (let i = 0; i < n; i++) block[i] = 0.5 * Math.sin((2 * Math.PI * cfg.freq * (start + i)) / cfg.rate);
  p.process([[block]]);
}
const all = [];
for (const m of posted) all.push(...new Int16Array(m.pcm));
let crossings = 0;
for (let i = 1; i < all.length; i++) if ((all[i - 1] < 0) !== (all[i] < 0)) crossings++;
process.stdout.write(
  JSON.stringify({
    chunks: posted.length,
    samples: all.length,
    crossings,
    maxAbs: Math.max(...all.map(Math.abs)),
    level: posted.length ? posted[0].level : 0,
  })
);
