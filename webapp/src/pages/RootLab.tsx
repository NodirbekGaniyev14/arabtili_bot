import { useEffect, useState } from "react";
import { api, type RootDetail, type RootSummary } from "../lib/api";
import { playAudio } from "../lib/audio";

const tg = () => window.Telegram?.WebApp;

interface RootLabProps {
  onClose: () => void;
}

export default function RootLab({ onClose }: RootLabProps) {
  const [roots, setRoots] = useState<RootSummary[] | null>(null);
  const [active, setActive] = useState<RootDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [seen, setSeen] = useState<Set<string>>(new Set());
  const [error, setError] = useState(false);

  useEffect(() => {
    api
      .getRoots()
      .then((r) => {
        setRoots(r.roots);
        setSeen(new Set(r.roots.filter((x) => x.seen).map((x) => x.root)));
      })
      .catch(() => setError(true));
  }, []);

  const openRoot = (root: string) => {
    tg()?.HapticFeedback?.impactOccurred("light");
    setLoadingDetail(true);
    api
      .getRoot(root)
      .then((d) => {
        setActive(d);
        setSeen((s) => new Set(s).add(root));
        playAudio(d.audio);
      })
      .catch(() => setError(true))
      .finally(() => setLoadingDetail(false));
  };

  return (
    <div className="fixed inset-0 z-30 bg-sand overflow-y-auto">
      <div className="max-w-md mx-auto px-4 pt-5 pb-10">
        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <button
            onClick={active ? () => setActive(null) : onClose}
            className="text-2xl text-ink-soft font-bold leading-none active:opacity-60"
          >
            {active ? "‹" : "✕"}
          </button>
          <div className="flex items-center gap-2">
            <span className="text-xl">🔬</span>
            <h1 className="text-xl font-extrabold">
              {active ? "O'zak daraxti" : "O'zak laboratoriyasi"}
            </h1>
          </div>
        </div>

        {error && (
          <div className="min-h-[50vh] flex items-center justify-center text-ink-soft font-semibold text-center px-6">
            Yuklashda xatolik. Qayta urinib ko'ring.
          </div>
        )}

        {/* ── Ro'yxat ── */}
        {!active && roots && (
          <>
            <p className="text-sm text-ink-soft font-semibold mb-4 leading-relaxed">
              Arab so'zlari <b>3 harfli o'zakdan</b> yasaladi. Bitta o'zakni
              bilsangiz — o'nlab so'zni tanib olasiz. Ko'pini o'zbek tilida
              allaqachon bilasiz!
            </p>
            <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft mb-2">
              KO'RILGAN: {seen.size}/{roots.length}
            </div>
            <div className="grid grid-cols-2 gap-3">
              {roots.map((r) => (
                <button
                  key={r.root}
                  onClick={() => openRoot(r.root)}
                  className={`rounded-2xl border p-3.5 text-center active:scale-95 transition-transform ${
                    seen.has(r.root)
                      ? "bg-emerald-deep/5 border-emerald-deep/40"
                      : "bg-card border-cardline"
                  }`}
                >
                  <div className="font-arabic text-2xl text-emerald-deep tracking-[0.15em]">
                    {r.root}
                  </div>
                  <div className="mt-1 text-[13px] font-extrabold">
                    {r.meaning_uz}
                  </div>
                  <div className="mt-1 text-[10px] text-ink-soft font-semibold truncate">
                    {r.count} so'z
                  </div>
                </button>
              ))}
            </div>
          </>
        )}

        {/* ── Daraxt (detail) ── */}
        {active && (
          <RootTree
            detail={active}
            onAddSrs={() =>
              api.addRootToSrs(active.root).then((res) => {
                tg()?.HapticFeedback?.notificationOccurred("success");
                return res.added;
              })
            }
          />
        )}

        {loadingDetail && !active && (
          <div className="min-h-[40vh] flex items-center justify-center">
            <div className="w-10 h-10 rounded-xl bg-emerald-deep animate-pulse" />
          </div>
        )}
      </div>
    </div>
  );
}

/* ── O'zak daraxti + tap-to-reveal ── */

function RootTree({
  detail,
  onAddSrs,
}: {
  detail: RootDetail;
  onAddSrs: () => Promise<number>;
}) {
  const [added, setAdded] = useState<number | null>(null);

  return (
    <div>
      {/* Ildiz */}
      <div className="rounded-3xl bg-gradient-to-br from-emerald-deep to-emerald-dark p-6 text-center text-white shadow-lg">
        <button
          onClick={() => playAudio(detail.audio)}
          className="font-arabic text-5xl tracking-[0.2em] active:scale-95 transition-transform"
        >
          {detail.root}
        </button>
        <div className="mt-2 text-gold-soft font-bold">{detail.meaning_uz}</div>
        <div className="mt-3 flex flex-wrap gap-1.5 justify-center">
          {detail.uz_cognates.map((c) => (
            <span
              key={c}
              className="rounded-full bg-white/15 px-2.5 py-1 text-[11px] font-bold"
            >
              {c}
            </span>
          ))}
        </div>
      </div>

      {/* Bog'lovchi chiziq */}
      <div className="flex justify-center">
        <div className="w-0.5 h-5 bg-cardline" />
      </div>

      {/* Yasalgan so'zlar */}
      <div className="space-y-2.5">
        {detail.derived.map((d) => (
          <DerivedRow key={d.ar} d={d} />
        ))}
      </div>

      {/* SRS'ga qo'shish */}
      <button
        onClick={() => onAddSrs().then(setAdded)}
        disabled={added !== null}
        className="mt-6 w-full rounded-2xl bg-gold-soft border border-gold/30 py-3.5 font-extrabold text-ink active:scale-[0.98] transition-transform disabled:opacity-70"
      >
        {added === null
          ? "🔁 Bu o'zakni takrorga qo'shish"
          : `✓ ${added} ta karta qo'shildi`}
      </button>
    </div>
  );
}

function DerivedRow({
  d,
}: {
  d: { ar: string; uz: string; pattern: string; audio?: string; uz_cognate?: string };
}) {
  const [open, setOpen] = useState(false);
  return (
    <button
      onClick={() => {
        setOpen((o) => !o);
        playAudio(d.audio);
      }}
      className="w-full flex items-center gap-3 rounded-2xl bg-card border border-cardline p-3 text-left active:scale-[0.99] transition-transform"
    >
      <span className="font-arabic text-2xl text-emerald-deep min-w-24">
        {d.ar}
      </span>
      {open ? (
        <div className="flex-1 min-w-0">
          <div className="font-bold text-[14px] leading-tight">{d.uz}</div>
          <div className="text-[11px] text-ink-soft font-semibold">
            vazn: <span className="font-arabic text-sm">{d.pattern}</span>
            {d.uz_cognate && (
              <span className="ml-1.5 text-emerald-deep">
                · o'zbekcha: {d.uz_cognate}
              </span>
            )}
          </div>
        </div>
      ) : (
        <span className="flex-1 text-ink-soft text-sm font-semibold">
          bosib ko'ring 👁
        </span>
      )}
      <span className="text-lg">🔊</span>
    </button>
  );
}
