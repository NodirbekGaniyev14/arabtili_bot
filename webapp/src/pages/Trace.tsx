import { useEffect, useRef, useState } from "react";
import BadgeToast from "../components/BadgeToast";
import { api, type Badge, type TraceFinish, type TraceInfo, type TraceLetter } from "../lib/api";
import { playAudio } from "../lib/audio";

/** ✍️ Harf chizish mashqi (K21.6) — A0: barmoq bilan harf shaklini chizish.
 *
 *  Kanvasda och rangda namuna harf (Amiri), o'quvchi ustidan chizadi. Baholash
 *  brauzerda, AI'siz: namuna maskasi (matn rasteri) va chizilgan chiziq maskasi
 *  solishtiriladi — qamrov (namunaning qancha qismi bosib o'tildi) va aniqlik
 *  (chiziqning qancha qismi namuna ichida); nuqtalar alohida komponent sifatida
 *  tekshiriladi (nuqtasiz ب — xato). Yakunda o'rtacha ball va XP (server). */

const SIZE = 300; // kanvas (CSS px), kvadrat
const STROKE = 16; // chizish qalinligi
const TOL = 12; // kechirim radiusi
const FONT = `230px "Amiri", serif`;
const GUIDE = "#d9d3c5";
const INK = "#0e6b4e";

type Mask = Uint8Array;

function textMask(ch: string, dilate: number): Mask {
  const c = document.createElement("canvas");
  c.width = SIZE;
  c.height = SIZE;
  const g = c.getContext("2d")!;
  g.font = FONT;
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillStyle = "#000";
  g.fillText(ch, SIZE / 2, SIZE / 2 + 8);
  if (dilate > 0) {
    g.lineJoin = "round";
    g.strokeStyle = "#000";
    g.lineWidth = dilate * 2;
    g.strokeText(ch, SIZE / 2, SIZE / 2 + 8);
  }
  return toMask(g);
}

function strokesMask(strokes: number[][][], width: number): Mask {
  const c = document.createElement("canvas");
  c.width = SIZE;
  c.height = SIZE;
  const g = c.getContext("2d")!;
  g.strokeStyle = "#000";
  g.fillStyle = "#000";
  g.lineWidth = width;
  g.lineCap = "round";
  g.lineJoin = "round";
  for (const s of strokes) {
    if (s.length === 1) {
      g.beginPath();
      g.arc(s[0][0], s[0][1], width / 2, 0, Math.PI * 2);
      g.fill();
      continue;
    }
    g.beginPath();
    g.moveTo(s[0][0], s[0][1]);
    for (let i = 1; i < s.length; i++) g.lineTo(s[i][0], s[i][1]);
    g.stroke();
  }
  return toMask(g);
}

function toMask(g: CanvasRenderingContext2D): Mask {
  const d = g.getImageData(0, 0, SIZE, SIZE).data;
  const m = new Uint8Array(SIZE * SIZE);
  for (let i = 0; i < m.length; i++) m[i] = d[i * 4 + 3] > 90 ? 1 : 0;
  return m;
}

/** Namuna maskasining bog'langan bo'laklari (tana + nuqtalar). */
function components(mask: Mask): number[][] {
  const seen = new Uint8Array(mask.length);
  const out: number[][] = [];
  for (let start = 0; start < mask.length; start++) {
    if (!mask[start] || seen[start]) continue;
    const comp: number[] = [];
    const stack = [start];
    seen[start] = 1;
    while (stack.length) {
      const p = stack.pop()!;
      comp.push(p);
      const x = p % SIZE;
      const y = (p - x) / SIZE;
      const nb = [p - 1, p + 1, p - SIZE, p + SIZE];
      for (let k = 0; k < 4; k++) {
        const q = nb[k];
        if (q < 0 || q >= mask.length) continue;
        if ((k === 0 && x === 0) || (k === 1 && x === SIZE - 1)) continue;
        if ((k === 2 && y === 0) || (k === 3 && y === SIZE - 1)) continue;
        if (mask[q] && !seen[q]) {
          seen[q] = 1;
          stack.push(q);
        }
      }
    }
    out.push(comp);
  }
  return out;
}

export interface Verdict {
  score: number;
  coverage: number;
  precision: number;
  missingDots: number;
  text: string;
}

export function evaluate(ch: string, strokes: number[][][]): Verdict {
  const glyph = textMask(ch, 0);
  const glyphDil = textMask(ch, TOL);
  const ink = strokesMask(strokes, STROKE);
  const inkDil = strokesMask(strokes, STROKE + TOL * 2);
  let g = 0, cov = 0, s = 0, prec = 0;
  for (let i = 0; i < glyph.length; i++) {
    if (glyph[i]) {
      g++;
      if (inkDil[i]) cov++;
    }
    if (ink[i]) {
      s++;
      if (glyphDil[i]) prec++;
    }
  }
  const coverage = g ? cov / g : 0;
  const precision = s ? prec / s : 0;
  // Nuqtalar / kichik belgilar: eng katta bo'lakdan ancha kichik komponentlar
  const comps = components(glyph);
  const largest = Math.max(...comps.map((c) => c.length), 1);
  let missingDots = 0;
  let dots = 0;
  for (const c of comps) {
    if (c.length >= largest * 0.25) continue;
    dots++;
    const hit = c.reduce((n, p) => n + (inkDil[p] ? 1 : 0), 0);
    if (hit / c.length < 0.5) missingDots++;
  }
  let score = Math.round(100 * (0.65 * coverage + 0.35 * precision));
  if (s < g * 0.12) score = Math.min(score, 25);
  if (missingDots) score = Math.min(score, 55);
  let text: string;
  if (s < g * 0.12) text = "Juda kam chizildi — namunani boshidan oxirigacha bosib o'ting";
  else if (missingDots) text = `Nuqta${dots > 1 ? "lar" : ""}ni unutdingiz — ${dots} ta nuqta kerak`;
  else if (coverage < 0.6) text = "Harfning bir qismi chizilmagan — namunani to'liq bosib o'ting";
  else if (precision < 0.6) text = "Chiziq namunadan tashqariga chiqdi — sekinroq, shakl bo'ylab";
  else if (score >= 90) text = "Zo'r! Shakl aniq va toza";
  else text = "Yaxshi — yana biroz aniqroq, shakl bo'ylab";
  return { score, coverage, precision, missingDots, text };
}

interface Props {
  onClose: () => void;
  onDone?: () => void;
}

export default function Trace({ onClose, onDone }: Props) {
  const [info, setInfo] = useState<TraceInfo | null>(null);
  const [error, setError] = useState("");
  const [idx, setIdx] = useState(0);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [scores, setScores] = useState<Record<string, number>>({});
  const [finish, setFinish] = useState<TraceFinish | null>(null);
  const [busy, setBusy] = useState(false);
  const [badges, setBadges] = useState<Badge[]>([]);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const strokes = useRef<number[][][]>([]);
  const drawing = useRef(false);
  const chipsRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    api
      .getTrace()
      .then((d) => {
        setInfo(d);
        // Birinchi «o'tilmagan» harfdan boshlaymiz
        const first = d.letters.findIndex((l) => (d.best[l.ar] ?? 0) < d.pass);
        setIdx(first < 0 ? 0 : first);
      })
      .catch(() => setError("Harflar yuklanmadi"));
  }, []);

  const letter: TraceLetter | undefined = info?.letters[idx];

  // Namuna chizish (shrift yuklangach)
  const drawGuide = () => {
    const c = canvasRef.current;
    if (!c || !letter) return;
    const dpr = window.devicePixelRatio || 1;
    c.width = SIZE * dpr;
    c.height = SIZE * dpr;
    const g = c.getContext("2d")!;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, SIZE, SIZE);
    g.font = FONT;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillStyle = GUIDE;
    g.fillText(letter.ar, SIZE / 2, SIZE / 2 + 8);
    // chizilganlar
    g.strokeStyle = INK;
    g.lineWidth = STROKE;
    g.lineCap = "round";
    g.lineJoin = "round";
    for (const s of strokes.current) {
      g.beginPath();
      if (s.length === 1) {
        g.arc(s[0][0], s[0][1], STROKE / 2, 0, Math.PI * 2);
        g.fillStyle = INK;
        g.fill();
        continue;
      }
      g.moveTo(s[0][0], s[0][1]);
      for (let i = 1; i < s.length; i++) g.lineTo(s[i][0], s[i][1]);
      g.stroke();
    }
  };

  useEffect(() => {
    strokes.current = [];
    setVerdict(null);
    const fonts = (document as Document & { fonts?: { load(f: string): Promise<unknown> } }).fonts;
    (fonts ? fonts.load(FONT).catch(() => undefined) : Promise.resolve()).then(drawGuide);
    chipsRef.current?.querySelector<HTMLElement>(`[data-i="${idx}"]`)?.scrollIntoView({ inline: "center", block: "nearest" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx, letter?.ar]);

  const pos = (e: React.PointerEvent<HTMLCanvasElement>): [number, number] => {
    const r = e.currentTarget.getBoundingClientRect();
    return [((e.clientX - r.left) / r.width) * SIZE, ((e.clientY - r.top) / r.height) * SIZE];
  };

  const down = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (verdict) setVerdict(null); // tekshiruvdan keyin davom etish (masalan nuqtani qo'shish) mumkin
    drawing.current = true;
    e.currentTarget.setPointerCapture(e.pointerId);
    strokes.current.push([pos(e)]);
    drawGuide();
  };
  const move = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return;
    const s = strokes.current[strokes.current.length - 1];
    const p = pos(e);
    const last = s[s.length - 1];
    if (Math.hypot(p[0] - last[0], p[1] - last[1]) < 1.5) return;
    s.push(p);
    drawGuide();
  };
  const up = () => {
    drawing.current = false;
  };

  const clear = () => {
    strokes.current = [];
    setVerdict(null);
    drawGuide();
  };

  const check = () => {
    if (!letter || !strokes.current.length) return;
    const v = evaluate(letter.ar, strokes.current);
    setVerdict(v);
    setScores((s) => ({ ...s, [letter.ar]: Math.max(s[letter.ar] ?? 0, v.score) }));
    window.Telegram?.WebApp.HapticFeedback?.notificationOccurred(v.score >= (info?.pass ?? 70) ? "success" : "warning");
  };

  const next = () => {
    if (!info) return;
    setIdx((i) => (i + 1) % info.letters.length);
  };

  const finishSession = async () => {
    if (!Object.keys(scores).length) return;
    setBusy(true);
    try {
      const r = await api.finishTrace(scores);
      setFinish(r);
      if (r.new_badges?.length) setBadges(r.new_badges);
      setInfo((d) => (d ? { ...d, best: r.best, xp_today: d.xp_today || r.xp > 0 } : d));
      onDone?.();
    } catch {
      setError("Natija saqlanmadi — internetni tekshiring");
    } finally {
      setBusy(false);
    }
  };

  const pass = info?.pass ?? 70;
  const done = Object.keys(scores).length;

  return (
    <div className="fixed inset-0 z-50 bg-sand flex flex-col max-w-md mx-auto">
      <BadgeToast badges={badges} />
      <div className="flex items-center justify-between px-4 py-3 border-b border-cardline bg-card">
        <div className="min-w-0">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">✍️ HARF CHIZISH · A0</div>
          <div className="font-extrabold truncate">
            {letter ? `${letter.name} — ${letter.uz}` : "Yuklanmoqda…"}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {done > 0 && !finish && (
            <button
              onClick={finishSession}
              disabled={busy}
              className="rounded-full bg-emerald-deep px-3 py-1.5 text-[12px] font-extrabold text-white disabled:opacity-60"
            >
              Yakunlash · {done}
            </button>
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

        {finish && (
          <section className="rounded-3xl bg-card border border-cardline p-4 text-center">
            <div className="text-4xl">{finish.avg >= pass ? "🎉" : "💪"}</div>
            <div className="mt-1 font-extrabold text-lg">
              {finish.count} ta harf · o'rtacha {finish.avg}%
            </div>
            <div className="mt-2 inline-block rounded-2xl bg-gold-soft border border-gold/30 px-6 py-2 text-2xl font-extrabold text-emerald-dark">
              +{finish.xp} XP
            </div>
            {finish.xp === 0 && (
              <p className="mt-2 text-[12px] text-ink-soft font-semibold">
                XP: kuniga bir marta, kamida {info?.min_letters ?? 5} ta harf
              </p>
            )}
            <button
              onClick={() => {
                setFinish(null);
                setScores({});
                next();
              }}
              className="mt-3 w-full rounded-2xl bg-emerald-deep py-3 text-white font-extrabold"
            >
              Davom etish
            </button>
          </section>
        )}

        {/* Harflar chiziqchasi */}
        {info && (
          <div ref={chipsRef} className="flex gap-1.5 overflow-x-auto pb-1 -mx-1 px-1">
            {info.letters.map((l, i) => {
              const b = Math.max(info.best[l.ar] ?? 0, scores[l.ar] ?? 0);
              const ok = b >= pass;
              return (
                <button
                  key={l.ar}
                  data-i={i}
                  onClick={() => setIdx(i)}
                  className={`relative shrink-0 w-11 h-11 rounded-xl font-arabic text-2xl leading-none ${
                    i === idx ? "bg-emerald-deep text-white" : ok ? "bg-gold-soft text-emerald-dark" : "bg-card border border-cardline"
                  }`}
                >
                  {l.ar}
                  {ok && <span className="absolute -top-1 -right-1 text-[10px]">✓</span>}
                </button>
              );
            })}
          </div>
        )}

        {/* Kanvas */}
        {letter && (
          <section className="rounded-3xl bg-card border border-cardline p-3">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[11px] font-extrabold tracking-[0.12em] text-ink-soft">
                {idx + 1}/{info?.letters.length} · NAMUNA USTIDAN CHIZING
              </div>
              <button
                onClick={() => playAudio(letter.audio)}
                className="rounded-lg bg-gold-soft px-2.5 py-1 text-[11px] font-extrabold active:scale-95 transition-transform"
              >
                🔊 {letter.name}
              </button>
            </div>
            <canvas
              ref={canvasRef}
              onPointerDown={down}
              onPointerMove={move}
              onPointerUp={up}
              onPointerCancel={up}
              onPointerLeave={up}
              className="mx-auto block rounded-2xl bg-sand border border-cardline touch-none select-none"
              style={{ width: SIZE, height: SIZE, maxWidth: "100%" }}
            />
            {!verdict ? (
              <div className="mt-3 grid grid-cols-3 gap-2">
                <button onClick={clear} className="rounded-2xl bg-cardline py-3 font-extrabold text-ink-soft">
                  Tozalash
                </button>
                <button
                  onClick={check}
                  className="col-span-2 rounded-2xl bg-emerald-deep py-3 font-extrabold text-white active:scale-[0.98] transition-transform"
                >
                  Tekshirish
                </button>
              </div>
            ) : (
              <div className="mt-3">
                <div className="flex items-center gap-3">
                  <div
                    className={`w-16 h-16 shrink-0 rounded-2xl flex items-center justify-center text-xl font-extrabold text-white ${
                      verdict.score >= pass ? "bg-emerald-deep" : verdict.score >= 50 ? "bg-gold" : "bg-terracotta"
                    }`}
                  >
                    {verdict.score}%
                  </div>
                  <div className="text-[13px] font-bold leading-snug">
                    {verdict.text}
                    <div className="mt-0.5 text-[11px] text-ink-soft font-semibold">
                      qamrov {Math.round(verdict.coverage * 100)}% · aniqlik {Math.round(verdict.precision * 100)}%
                      {verdict.score < pass && " · davom etib to'ldiring yoki tozalang"}
                    </div>
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <button onClick={clear} className="rounded-2xl bg-cardline py-3 font-extrabold text-ink-soft">
                    Tozalash
                  </button>
                  <button
                    onClick={next}
                    className="rounded-2xl bg-emerald-deep py-3 font-extrabold text-white active:scale-[0.98] transition-transform"
                  >
                    Keyingi harf ›
                  </button>
                </div>
              </div>
            )}
          </section>
        )}

        <p className="text-[12px] text-ink-soft font-semibold px-1">
          Barmoq bilan och rangli harf ustidan chizing — o'ngdan chapga, nuqtalarni ham qo'ying. {info?.min_letters ?? 5}+ harf
          chizib «Yakunlash» bossangiz — XP (kuniga bir marta). {pass}%+ — ✓.
        </p>
      </div>
    </div>
  );
}
