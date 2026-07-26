/** Ma'lumotnoma — butun kurs grammatikasi va lug'ati, qidiruv bilan.
 *
 * Darsni qayta ochmasdan qoidani yoki so'zni topish uchun: 174 grammatika
 * nuqtasi va 1168 so'z bir joyda.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type GrammarEntry,
  type ReferenceStats,
  type VocabEntry,
} from "../lib/api";
import { playAudio } from "../lib/audio";

type Tab = "grammar" | "vocab";
const LEVELS = ["A0", "A1", "A2", "B1"] as const;

export default function Reference({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<Tab>("grammar");
  const [q, setQ] = useState("");
  const [level, setLevel] = useState<string>("");
  const [stats, setStats] = useState<ReferenceStats | null>(null);

  const [grammar, setGrammar] = useState<GrammarEntry[]>([]);
  const [vocab, setVocab] = useState<VocabEntry[]>([]);
  const [vocabTotal, setVocabTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    api.getReferenceStats().then(setStats).catch(() => {});
  }, []);

  // Qidiruvni kechiktirib yuboramiz (har harfda so'rov ketmasin)
  const timer = useRef<number | null>(null);
  useEffect(() => {
    setLoading(true);
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const req =
        tab === "grammar"
          ? api.searchGrammar(q, level).then((r) => setGrammar(r.items))
          : api.searchVocab(q, level).then((r) => {
              setVocab(r.items);
              setVocabTotal(r.total);
            });
      req.catch(() => {}).finally(() => setLoading(false));
    }, 250);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [tab, q, level]);

  const count = tab === "grammar" ? grammar.length : vocabTotal;
  const placeholder =
    tab === "grammar"
      ? "Qoida izlash: majhul, hol, shart..."
      : "So'z izlash: kitob, كتاب, ك ت ب...";

  const grouped = useMemo(() => {
    const by: Record<string, GrammarEntry[]> = {};
    grammar.forEach((g) => {
      by[g.level] = by[g.level] || [];
      by[g.level].push(g);
    });
    return by;
  }, [grammar]);

  return (
    <div className="fixed inset-0 z-30 bg-sand overflow-y-auto">
      <div className="max-w-md mx-auto px-4 pt-5 pb-24">
        <div className="flex items-center gap-3">
          <button
            onClick={onClose}
            className="text-2xl text-ink-soft font-bold leading-none active:opacity-60"
          >
            ✕
          </button>
          <div className="font-extrabold text-lg">Ma'lumotnoma</div>
        </div>

        {/* Tab: grammatika / lug'at */}
        <div className="mt-4 grid grid-cols-2 gap-2">
          {(
            [
              ["grammar", "قواعد", "Grammatika", stats?.grammar_points],
              ["vocab", "مفردات", "Lug'at", stats?.vocab_words],
            ] as const
          ).map(([id, ar, label, n]) => (
            <button
              key={id}
              onClick={() => {
                setTab(id as Tab);
                setOpen(null);
              }}
              className={`rounded-2xl border p-3 text-center transition-colors ${
                tab === id
                  ? "bg-emerald-deep/8 border-emerald-deep"
                  : "bg-card border-cardline"
              }`}
            >
              <div className="font-arabic text-xl text-emerald-deep">{ar}</div>
              <div className="text-sm font-extrabold mt-0.5">{label}</div>
              {n != null && (
                <div className="text-[11px] text-ink-soft font-semibold">{n} ta</div>
              )}
            </button>
          ))}
        </div>

        {/* Qidiruv */}
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={placeholder}
          className="mt-3 w-full rounded-2xl border border-cardline bg-card px-4 py-3 text-[15px] font-semibold outline-none focus:border-emerald-deep"
        />

        {/* Daraja filtri */}
        <div className="mt-2.5 flex gap-1.5 overflow-x-auto pb-1">
          {["", ...LEVELS].map((lv) => (
            <button
              key={lv || "all"}
              onClick={() => setLevel(lv)}
              className={`shrink-0 rounded-full px-3.5 py-1.5 text-xs font-extrabold border transition-colors ${
                level === lv
                  ? "bg-emerald-deep text-white border-emerald-deep"
                  : "bg-card text-ink-soft border-cardline"
              }`}
            >
              {lv || "Hammasi"}
            </button>
          ))}
        </div>

        <div className="mt-2 text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
          {loading ? "IZLANMOQDA..." : `${count} NATIJA`}
        </div>

        {/* Natijalar */}
        {!loading && count === 0 && (
          <div className="mt-10 text-center text-ink-soft font-semibold">
            <div className="text-4xl mb-2">🔍</div>
            Hech narsa topilmadi. Boshqa so'z bilan urinib ko'ring.
          </div>
        )}

        {tab === "grammar" ? (
          <div className="mt-3 space-y-4">
            {LEVELS.filter((lv) => grouped[lv]?.length).map((lv) => (
              <div key={lv}>
                <div className="text-[11px] font-extrabold tracking-[0.14em] text-emerald-deep mb-2">
                  {lv} · {grouped[lv].length} QOIDA
                </div>
                <div className="space-y-2">
                  {grouped[lv].map((g) => (
                    <GrammarCard
                      key={g.lesson_id}
                      entry={g}
                      open={open === g.lesson_id}
                      onToggle={() =>
                        setOpen(open === g.lesson_id ? null : g.lesson_id)
                      }
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-3 space-y-2">
            {vocab.map((v) => (
              <VocabRow key={v.ar + v.lessons[0]} entry={v} />
            ))}
            {vocabTotal > vocab.length && (
              <p className="text-center text-xs text-ink-soft font-semibold pt-2">
                {vocab.length} / {vocabTotal} ko'rsatildi — qidiruvni
                aniqlashtiring
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function GrammarCard({
  entry,
  open,
  onToggle,
}: {
  entry: GrammarEntry;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="rounded-2xl bg-card border border-cardline overflow-hidden">
      <button onClick={onToggle} className="w-full p-3.5 text-left active:opacity-70">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="font-arabic text-xl text-emerald-deep" dir="rtl">
              {entry.point_ar}
            </div>
            <div className="text-[13px] font-bold mt-1">{entry.lesson_title}</div>
          </div>
          <span className="text-ink-soft text-lg leading-none shrink-0">
            {open ? "−" : "+"}
          </span>
        </div>
      </button>

      {open && (
        <div className="px-3.5 pb-3.5 space-y-3">
          <p className="text-[13px] font-semibold leading-relaxed">
            {entry.explanation_uz}
          </p>

          {entry.table.length > 0 && (
            <div className="rounded-xl bg-sand/60 border border-cardline overflow-hidden">
              {entry.table.map((row, i) => (
                <div
                  key={i}
                  className={`flex items-center gap-2 px-3 py-2 ${
                    i ? "border-t border-cardline" : ""
                  }`}
                >
                  <span
                    className="font-arabic text-lg min-w-20 text-emerald-deep"
                    dir="rtl"
                  >
                    {row.ar}
                  </span>
                  <span className="flex-1 text-xs font-bold">{row.uz}</span>
                  {row.form && (
                    <span className="font-arabic text-[11px] text-ink-soft">
                      {row.form}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}

          {entry.common_mistakes_uz.length > 0 && (
            <div className="rounded-xl bg-terracotta/8 border border-terracotta/30 p-3">
              <div className="text-[10px] font-extrabold tracking-[0.14em] text-terracotta mb-1">
                ⚠️ KENG TARQALGAN XATOLAR
              </div>
              {entry.common_mistakes_uz.map((m, i) => (
                <p key={i} className="text-[12px] font-semibold leading-relaxed">
                  • {m}
                </p>
              ))}
            </div>
          )}

          <div className="text-[11px] text-ink-soft font-semibold">
            📍 {entry.lesson_id} · {entry.module}
          </div>
        </div>
      )}
    </div>
  );
}

function VocabRow({ entry }: { entry: VocabEntry }) {
  return (
    <button
      onClick={() => entry.audio && playAudio(entry.audio)}
      className="w-full rounded-2xl bg-card border border-cardline p-3 text-left active:scale-[0.99] transition-transform"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-extrabold">{entry.uz}</div>
          <div className="text-[11px] text-emerald-deep font-bold italic">
            {entry.translit}
          </div>
          {entry.example_ar && (
            <div className="mt-1 text-[11px] text-ink-soft font-semibold truncate">
              {entry.example_uz}
            </div>
          )}
        </div>
        <div className="text-right shrink-0">
          <div className="font-arabic text-2xl" dir="rtl">
            {entry.ar}
          </div>
          <div className="flex items-center gap-1.5 justify-end mt-0.5">
            {entry.root && (
              <span className="rounded-full bg-gold-soft px-2 py-0.5 text-[10px] font-bold font-arabic">
                {entry.root}
              </span>
            )}
            <span className="text-[10px] text-ink-soft font-bold">{entry.level}</span>
            {entry.audio && <span className="text-xs">🔊</span>}
          </div>
        </div>
      </div>
    </button>
  );
}
