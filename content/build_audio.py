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

CONTENT_DIR = Path(__file__).parent / "modules"
OUT_DIR = Path(__file__).parent.parent / "webapp" / "public" / "audio"


def collect_tasks() -> dict[str, str]:
    """audio fayl nomi -> aytiladigan matn"""
    tasks: dict[str, str] = {}

    def scan(obj):
        if isinstance(obj, dict):
            audio = obj.get("audio")
            if audio:
                text = obj.get("audio_text") or obj.get("ar") or obj.get("arabic")
                if text:
                    tasks.setdefault(audio, text)
            for v in obj.values():
                scan(v)
        elif isinstance(obj, list):
            for v in obj:
                scan(v)

    for f in sorted(CONTENT_DIR.glob("*.json")):
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
