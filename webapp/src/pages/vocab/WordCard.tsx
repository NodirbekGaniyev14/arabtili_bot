/** Lug'at qidiruvi natijasi — bosilganda misol, eslatma va grammatik ma'lumot ochiladi. */

import { useState } from "react";
import type { VocabWord } from "../../lib/api";
import { playAudio } from "../../lib/audio";

export default function WordCard({ word }: { word: VocabWord }) {
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
