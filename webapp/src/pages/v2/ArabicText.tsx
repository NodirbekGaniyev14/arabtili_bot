/** Tap-to-reveal: arabcha matndagi har so'zga bosilsa harakat + ma'no +
 * o'zak + vazn ko'rinadi (spec §2.6 UI talabi). Ma'lumot dars lug'atidan olinadi. */

import { useMemo, useState } from "react";
import type { LessonV2Data } from "../../lib/api";
import { playAudio } from "../../lib/audio";

const HARAKAT_RE = /[ً-ْٰ]/g;

export const stripHarakat = (s: string) => s.replace(HARAKAT_RE, "");

export interface RevealInfo {
  ar: string;
  uz: string;
  root?: string;
  pattern?: string;
  audio?: string;
}

/** Dars bo'ylab (lug'at + o'zak yasalmalari) qidiruv jadvali. */
export function buildLookup(lesson: LessonV2Data): Map<string, RevealInfo> {
  const map = new Map<string, RevealInfo>();
  for (const v of lesson.vocabulary) {
    map.set(stripHarakat(v.ar), {
      ar: v.ar, uz: v.uz, root: v.root, pattern: v.pattern, audio: v.audio,
    });
  }
  for (const r of lesson.roots) {
    for (const d of r.derived) {
      const key = stripHarakat(d.ar);
      if (!map.has(key)) {
        map.set(key, { ar: d.ar, uz: d.uz, root: r.root, pattern: d.pattern });
      }
    }
  }
  return map;
}

interface ArabicTextProps {
  text: string;
  lookup: Map<string, RevealInfo>;
  className?: string;
}

export default function ArabicText({ text, lookup, className = "" }: ArabicTextProps) {
  const [open, setOpen] = useState<number | null>(null);
  const words = useMemo(() => text.split(/\s+/).filter(Boolean), [text]);

  return (
    <span dir="rtl" className={className}>
      {words.map((w, i) => {
        const info = lookup.get(stripHarakat(w).replace(/[.,؟!·:؛]/g, ""));
        return (
          <span key={i} className="relative inline-block mx-0.5">
            <button
              type="button"
              onClick={() => {
                if (!info) return;
                setOpen(open === i ? null : i);
                playAudio(info.audio);
              }}
              className={`font-arabic ${info ? "underline decoration-dotted decoration-gold underline-offset-4" : ""}`}
            >
              {w}
            </button>
            {open === i && info && (
              <span
                dir="ltr"
                className="absolute z-20 top-full right-0 mt-1 w-44 rounded-xl bg-ink text-sand text-xs font-semibold p-2.5 shadow-lg text-left"
                onClick={() => setOpen(null)}
              >
                <span className="font-arabic text-lg block text-gold-soft">
                  {info.ar}
                </span>
                {info.uz}
                {info.root && (
                  <span className="block mt-1 opacity-80">
                    o'zak: <span className="font-arabic">{info.root}</span>
                    {info.pattern && (
                      <>
                        {" · "}vazn: <span className="font-arabic">{info.pattern}</span>
                      </>
                    )}
                  </span>
                )}
              </span>
            )}
          </span>
        );
      })}
    </span>
  );
}
