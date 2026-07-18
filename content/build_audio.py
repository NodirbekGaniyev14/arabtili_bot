"""Kontentdagi barcha arabcha matnlar uchun mp3 generatsiya qiladi (edge-tts).

Ishlatish:  python content/build_audio.py
Fayllar webapp/public/audio/ ga yoziladi (mavjudlari qayta yaratilmaydi).
"""

import asyncio
import json
import sys
from pathlib import Path

import edge_tts

VOICE = "ar-SA-HamedNeural"
RATE = "-20%"  # o'rganuvchilar uchun sekinroq talaffuz

CONTENT_DIR = Path(__file__).parent
OUT_DIR = Path(__file__).parent.parent / "webapp" / "public" / "audio"

# Bu fayllarda audio maydonlari yo'q — o'tkazib yuboriladi
SKIP_FILES = {"curriculum.json"}


def collect_tasks() -> dict[str, str]:
    """audio fayl yo'li (ichki papka bo'lishi mumkin) -> aytiladigan matn"""
    tasks: dict[str, str] = {}

    def scan(obj):
        if isinstance(obj, dict):
            audio = obj.get("audio")
            if audio:
                text = (
                    obj.get("audio_text")
                    or obj.get("ar")
                    or obj.get("arabic")
                    or obj.get("hejazi_ar")
                    or obj.get("transcript_ar")
                    or obj.get("root")
                )
                if text:
                    tasks.setdefault(audio, text)
            for v in obj.values():
                scan(v)
        elif isinstance(obj, list):
            for v in obj:
                scan(v)

    # v1 (modules/*.json) + v2 (modules/{a0..}/*.json, roots/patterns/hejazi.json)
    for f in sorted(CONTENT_DIR.rglob("*.json")):
        if f.name in SKIP_FILES:
            continue
        scan(json.loads(f.read_text(encoding="utf-8")))
    return tasks


async def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tasks = collect_tasks()
    made = skipped = failed = 0

    for filename, text in tasks.items():
        out = OUT_DIR / filename
        out.parent.mkdir(parents=True, exist_ok=True)  # a0/, hj/, roots/ kabi
        if out.exists() and out.stat().st_size > 0:
            skipped += 1
            continue
        try:
            await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(out))
            made += 1
            print(f"  + {filename}  ({text})")
        except Exception as e:
            failed += 1
            print(f"  ! {filename} XATO: {e}")

    print(f"\nJami: {len(tasks)} | yangi: {made} | mavjud: {skipped} | xato: {failed}")


if __name__ == "__main__":
    asyncio.run(main())
