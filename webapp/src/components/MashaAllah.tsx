/** «Mā shā Allāh» belgisi — dars, nazorat testi yoki imtihon ≥ 92% bilan tugasa (foydalanuvchi so'rovi). */

export const MASHAALLAH_MIN = 92;

export default function MashaAllah({ score }: { score: number }) {
  if (score < MASHAALLAH_MIN) return null;
  return (
    <div className="inline-flex items-center gap-2.5 rounded-full bg-gold-soft border border-gold/40 px-4 py-1.5 shadow-sm">
      <span className="font-arabic text-2xl leading-none text-emerald-dark" dir="rtl">
        مَا شَاءَ الله
      </span>
      <span className="text-[12px] font-extrabold text-emerald-dark">Ma sha Alloh!</span>
    </div>
  );
}
