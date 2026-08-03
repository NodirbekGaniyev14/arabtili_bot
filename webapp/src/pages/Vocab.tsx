/** Lug'at — darajalar kesimidagi 6000 so'z (K16, docs/VOCAB_PLAN.md).
 *
 * Ikki rejim:
 *   ko'rish   — daraja tablari, mavzu to'plamlari, qidiruv, so'z kartasi
 *   o'rganish — «kunlik 20 so'z» fleshkarta; bilmagani SRS ga tushadi
 */

import { useEffect, useRef, useState } from "react";
import {
  api,
  type VocabStats,
  type VocabTheme,
  type VocabWord,
} from "../lib/api";
import { playAudio } from "../lib/audio";

const tg = () => window.Telegram?.WebApp;
const LEVELS = ["A0", "A1", "A2", "B1", "B2"] as const;

type Mode = "browse" | "study";

export default function Vocab({ onClose }: { onClose: () => void }) {
  const [mode, setMode] = useState<Mode>("browse");
  const [stats, setStats] = useState<VocabStats | null>(null);
  const [level, setLevel] = useState<string>("");
  const [theme, setTheme] = useState<string>("");
  const [themes, setThemes] = useState<VocabTheme[]>([]);
  const [q, setQ] = useState("");
  const [words, setWords] = useState<VocabWord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const loadStats = () => api.getVocabStats().then(setStats).catch(() => {});

  useEffect(() => {
    loadStats();
  }, []);

  useEffect(() => {
    api
      .getVocabThemes(level)
      .then((r) => setThemes(r.items.filter((t) => t.total > 0)))
      .catch(() => {});
  }, [level]);

  // Qidiruvni kechiktirib yuboramiz (har harfda so'rov ketmasin)
  const timer = useRef<number | null>(null);
  useEffect(() => {
    if (mode !== "browse") return;
    setLoading(true);
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      api
        .searchVocabBase(q, level, theme)
        .then((r) => {
          setWords(r.items);
          setTotal(r.total);
        })
        .catch(() => {})
        .finally(() => setLoading(false));
    }, 250);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [q, level, theme, mode]);

  if (mode === "study") {
    return (
      <StudySession
        level={level}
        theme={theme}
        onDone={() => {
          setMode("browse");
          loadStats();
        }}
      />
    );
  }

  const percent = stats?.goal ? Math.round((stats.total / stats.goal) * 100) : 0;

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
          <div className="flex items-center gap-2">
            <span className="text-xl">📚</span>
            <h1 className="text-lg font-extrabold">Lug'at</h1>
          </div>
        </div>

        {/* Umumiy holat */}
        {stats && (
          <div className="mt-4 rounded-2xl bg-emerald-deep text-white p-4">
            <div className="flex items-end justify-between">
              <div>
                <div className="text-[11px] font-extrabold tracking-[0.16em] text-white/60">
                  O'RGANILGAN
                </div>
                <div className="text-3xl font-extrabold leading-tight">
                  {stats.learned}
                  <span className="text-lg text-white/50"> / {stats.total}</span>
                </div>
              </div>
              <span className="font-arabic text-3xl text-white/30">مفردات</span>
            </div>
            <div className="mt-3 h-2 rounded-full bg-white/20 overflow-hidden">
              <div
                className="h-full bg-gold-soft rounded-full transition-[width]"
                style={{
                  width: `${
                    stats.total ? Math.round((stats.learned / stats.total) * 100) : 0
                  }%`,
                }}
              />
            </div>
            <div className="mt-2 text-[11px] font-semibold text-white/60">
              Baza to'ldirilmoqda: {stats.total} / {stats.goal} so'z ({percent}%)
            </div>
          </div>
        )}

        <button
          onClick={() => {
            tg()?.HapticFeedback?.impactOccurred("light");
            setMode("study");
          }}
          className="mt-3 w-full rounded-2xl bg-card border border-cardline p-4 text-left active:scale-[0.99] transition-transform"
        >
          <div className="flex items-center justify-between">
            <div>
              <div className="font-extrabold">Kunlik 20 so'z</div>
              <div className="text-xs text-ink-soft font-semibold">
                {level || "barcha daraja"}
                {theme ? ` · ${themes.find((t) => t.slug === theme)?.title_uz}` : ""} ·
                fleshkarta
              </div>
            </div>
            <span className="text-2xl">🎴</span>
          </div>
        </button>

        {/* Daraja filtri */}
        <div className="mt-3 flex gap-1.5 overflow-x-auto pb-1">
          {["", ...LEVELS].map((lv) => {
            const row = stats?.levels.find((x) => x.level === lv);
            return (
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
                {row && (
                  <span className="opacity-60"> {row.learned}/{row.total}</span>
                )}
              </button>
            );
          })}
        </div>

        {/* Qidiruv */}
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="So'z izlash: kitob, كتاب, ك ت ب..."
          className="mt-3 w-full rounded-2xl border border-cardline bg-card px-4 py-3 text-[15px] font-semibold outline-none focus:border-emerald-deep"
        />

        {/* Mavzular */}
        {themes.length > 0 && (
          <div className="mt-3 flex gap-1.5 overflow-x-auto pb-1">
            <button
              onClick={() => setTheme("")}
              className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-bold border ${
                theme === ""
                  ? "bg-gold-soft border-gold-soft"
                  : "bg-card text-ink-soft border-cardline"
              }`}
            >
              Barcha mavzu
            </button>
            {themes.map((t) => (
              <button
                key={t.slug}
                onClick={() => setTheme(theme === t.slug ? "" : t.slug)}
                className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-bold border ${
                  theme === t.slug
                    ? "bg-gold-soft border-gold-soft"
                    : "bg-card text-ink-soft border-cardline"
                }`}
              >
                {t.title_uz} · {t.total}
              </button>
            ))}
          </div>
        )}

        <div className="mt-2 text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
          {loading ? "IZLANMOQDA..." : `${total} SO'Z`}
        </div>

        {!loading && total === 0 && (
          <div className="mt-10 text-center text-ink-soft font-semibold">
            <div className="text-4xl mb-2">🔍</div>
            Hech narsa topilmadi. Boshqa so'z bilan urinib ko'ring.
          </div>
        )}

        <div className="mt-2 space-y-2">
          {words.map((w) => (
            <WordCard key={w.id} word={w} />
          ))}
          {total > words.length && (
            <p className="text-center text-xs text-ink-soft font-semibold pt-2">
              {words.length} / {total} ko'rsatildi — qidiruvni aniqlashtiring
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function WordCard({ word }: { word: VocabWord }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-2xl bg-card border border-cardline overflow-hidden">
      <button
        onClick={() => {
          setOpen(!open);
          playAudio(word.audio);
        }}
        className="w-full p-3 text-left active:opacity-70"
      >
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="text-[14px] font-extrabold">{word.uz}</div>
            <div className="text-[11px] text-emerald-deep font-bold italic">
              {word.translit}
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className="font-arabic text-2xl" dir="rtl">
              {word.ar}
            </div>
            <div className="flex items-center gap-1.5 justify-end mt-0.5">
              {word.root && (
                <span className="rounded-full bg-gold-soft px-2 py-0.5 text-[10px] font-bold font-arabic">
                  {word.root}
                </span>
              )}
              <span className="text-[10px] text-ink-soft font-bold">{word.level}</span>
              {word.audio && <span className="text-xs">🔊</span>}
            </div>
          </div>
        </div>
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-2">
          {word.example_ar && (
            <div className="rounded-xl bg-sand/60 border border-cardline p-2.5">
              <div className="font-arabic text-lg text-right" dir="rtl">
                {word.example_ar}
              </div>
              <div className="text-[12px] font-semibold text-ink-soft mt-1">
                {word.example_uz}
              </div>
            </div>
          )}
          {word.note_uz && (
            <div className="rounded-xl bg-gold-soft/40 border border-gold-soft p-2.5 text-[12px] font-semibold">
              💡 {word.note_uz}
            </div>
          )}
          <div className="flex flex-wrap gap-1.5 text-[10px] font-bold text-ink-soft">
            {word.pos && <Chip>{word.pos}</Chip>}
            {word.pattern && <Chip>{word.pattern}</Chip>}
            {word.plural_ar && <Chip>ko'plik: {word.plural_ar}</Chip>}
            {word.present_ar && <Chip>{word.present_ar}</Chip>}
            {word.masdar_ar && <Chip>masdar: {word.masdar_ar}</Chip>}
            {word.lessons.map((l) => (
              <Chip key={l}>📍 {l}</Chip>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-sand border border-cardline px-2 py-0.5">
      {children}
    </span>
  );
}

/** Fleshkarta sessiyasi — bilmagan so'zlar SRS kartotekasiga tushadi */
function StudySession({
  level,
  theme,
  onDone,
}: {
  level: string;
  theme: string;
  onDone: () => void;
}) {
  const [cards, setCards] = useState<VocabWord[] | null>(null);
  const [i, setI] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [unknown, setUnknown] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<number | null>(null);

  useEffect(() => {
    api
      .getVocabDaily(level, 20, theme)
      .then((r) => {
        setCards(r.items);
        if (r.items[0]) playAudio(r.items[0].audio);
      })
      .catch(() => setCards([]));
  }, [level, theme]);

  const finish = (list: string[]) => {
    setSaving(true);
    api
      .learnVocab(list)
      .then((r) => setSaved(r.added))
      .catch(() => setSaved(0))
      .finally(() => setSaving(false));
  };

  const answer = (know: boolean) => {
    if (!cards) return;
    const card = cards[i];
    const next = know ? unknown : [...unknown, card.ar];
    setUnknown(next);
    if (i + 1 >= cards.length) {
      finish(next);
      setI(i + 1);
      return;
    }
    setI(i + 1);
    setFlipped(false);
    playAudio(cards[i + 1].audio);
  };

  if (cards === null) {
    return (
      <div className="fixed inset-0 z-30 bg-sand flex items-center justify-center">
        <div className="text-ink-soft font-semibold">Yuklanmoqda...</div>
      </div>
    );
  }

  if (cards.length === 0) {
    return (
      <div className="fixed inset-0 z-30 bg-sand flex flex-col items-center justify-center gap-4 px-6 text-center">
        <div className="text-5xl">🎉</div>
        <div className="font-extrabold text-lg">Bu yerda yangi so'z qolmadi</div>
        <p className="text-sm text-ink-soft font-semibold">
          Boshqa daraja yoki mavzuni tanlang — yoki Takror bo'limida
          o'rganganlaringizni mustahkamlang.
        </p>
        <button
          onClick={onDone}
          className="rounded-2xl bg-emerald-deep text-white font-extrabold px-6 py-3"
        >
          Ortga
        </button>
      </div>
    );
  }

  // Sessiya tugadi
  if (i >= cards.length) {
    return (
      <div className="fixed inset-0 z-30 bg-sand flex flex-col items-center justify-center gap-3 px-6 text-center">
        <div className="text-5xl">✅</div>
        <div className="font-extrabold text-xl">{cards.length} ta so'z ko'rildi</div>
        <p className="text-sm text-ink-soft font-semibold">
          {saving
            ? "Saqlanmoqda..."
            : saved === null
              ? ""
              : saved > 0
                ? `${saved} ta so'z takror kartotekasiga qo'shildi — ertaga uchraydi.`
                : "Hammasini bilar ekansiz — kartotekaga hech narsa qo'shilmadi."}
        </p>
        <button
          onClick={onDone}
          disabled={saving}
          className="mt-2 rounded-2xl bg-emerald-deep text-white font-extrabold px-6 py-3 disabled:opacity-50"
        >
          Tugatish
        </button>
      </div>
    );
  }

  const card = cards[i];

  return (
    <div className="fixed inset-0 z-30 bg-sand overflow-y-auto">
      <div className="max-w-md mx-auto px-4 pt-5 pb-10 min-h-full flex flex-col">
        <div className="flex items-center gap-3">
          <button
            onClick={onDone}
            className="text-2xl text-ink-soft font-bold leading-none active:opacity-60"
          >
            ✕
          </button>
          <div className="flex-1 h-2 rounded-full bg-cardline overflow-hidden">
            <div
              className="h-full bg-emerald-deep rounded-full transition-[width]"
              style={{ width: `${(i / cards.length) * 100}%` }}
            />
          </div>
          <span className="text-xs font-extrabold text-ink-soft">
            {i + 1}/{cards.length}
          </span>
        </div>

        <button
          onClick={() => {
            setFlipped(true);
            playAudio(card.audio);
          }}
          className="flex-1 my-4 rounded-3xl bg-card border border-cardline p-6 flex flex-col items-center justify-center gap-3 active:scale-[0.99] transition-transform"
        >
          <div className="font-arabic text-5xl" dir="rtl">
            {card.ar}
          </div>
          <div className="text-sm text-emerald-deep font-bold italic">
            {card.translit}
          </div>
          {flipped ? (
            <>
              <div className="text-xl font-extrabold text-center">{card.uz}</div>
              {card.example_ar && (
                <div className="mt-2 text-center">
                  <div className="font-arabic text-lg" dir="rtl">
                    {card.example_ar}
                  </div>
                  <div className="text-[12px] text-ink-soft font-semibold mt-1">
                    {card.example_uz}
                  </div>
                </div>
              )}
              {card.note_uz && (
                <div className="text-[12px] font-semibold text-center rounded-xl bg-gold-soft/40 border border-gold-soft p-2 mt-1">
                  💡 {card.note_uz}
                </div>
              )}
            </>
          ) : (
            <div className="text-xs text-ink-soft font-semibold mt-2">
              Ma'nosini ko'rish uchun bosing
            </div>
          )}
        </button>

        <div className="grid grid-cols-2 gap-3">
          <button
            onClick={() => answer(false)}
            className="rounded-2xl bg-terracotta/12 border border-terracotta/40 text-terracotta font-extrabold py-4"
          >
            Bilmayman
          </button>
          <button
            onClick={() => answer(true)}
            className="rounded-2xl bg-emerald-deep text-white font-extrabold py-4"
          >
            Bilaman
          </button>
        </div>
        <p className="mt-2 text-center text-[11px] text-ink-soft font-semibold">
          «Bilmayman» — so'z takror kartotekasiga tushadi
        </p>
      </div>
    </div>
  );
}
