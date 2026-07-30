"""Kontentdagi barcha arabcha matnlar uchun mp3 generatsiya qiladi (edge-tts).

Ishlatish:
    python content/build_audio.py            # o'zgarganini qayta yaratadi
    python content/build_audio.py --check    # faqat tekshiradi (CI uchun)
    python content/build_audio.py --force    # hammasini qaytadan yaratadi

MUHIM: fayl mavjudligiga emas, MATN O'ZGARGANIGA qarab qayta yaratiladi.
Manifest (audio_manifest.json) har fayl uchun matn xeshini saqlaydi — dars
matni o'zgarsa audio ham yangilanadi. Ilgari mavjud fayl shunchaki
o'tkazib yuborilardi va dars boshqa harfning ovozini chalardi.

ESHITILISH (2026-07-30): yakka harf va bo'g'in ("بَ") juda qisqa chiqib
eshitilmasdi. Endi matn uzunligiga qarab tezlik tanlanadi va 1-2 harfli
matn IKKI MARTA, orasida pauza bilan aytiladi. Ovoz balandligi ham
oshirildi (`VOLUME`). Tezlik/balandlik o'zgarsa manifest xeshi ham
o'zgaradi — hamma fayl avtomatik qayta yaratiladi.
"""

import argparse
import asyncio
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import edge_tts

VOICE = "ar-SA-HamedNeural"
RATE = "-20%"  # o'rganuvchilar uchun sekinroq talaffuz
SHORT_RATE = "-35%"  # 3-4 harfli so'z
TINY_RATE = "-45%"  # 1-2 harf: yakka harf yoki bo'g'in
VOLUME = "+25%"  # telefon karnayida ham aniq eshitilishi uchun
CONCURRENCY = 8

# Harakatlar, sukun, tanvin, tatweel — "harf sanog'i"ga kirmaydi
_MARKS = re.compile(r"[ً-ْٰـۖ-ۭ\s]")


def core_letters(text: str) -> int:
    """Matndagi haqiqiy harflar soni (harakatlar hisobga olinmaydi)."""
    return len(_MARKS.sub("", text))


def voice_plan(text: str) -> tuple[str, str]:
    """(aytiladigan matn, tezlik) — qisqa matn sekinroq va takrorlanadi.

    Yakka harf/bo'g'in ("بَ") bir marta aytilganda 0.3 sekund chiqadi va
    o'quvchi ulgurmaydi — shuning uchun ikki marta, orasida arabcha vergul
    (pauza) bilan aytiladi.
    """
    n = core_letters(text)
    if n <= 2:
        return f"{text}، {text}", TINY_RATE
    if n <= 4:
        return text, SHORT_RATE
    return text, RATE

CONTENT_DIR = Path(__file__).parent
OUT_DIR = Path(__file__).parent.parent / "webapp" / "public" / "audio"
MANIFEST = CONTENT_DIR / "audio_manifest.json"

# Bu fayllarda audio maydonlari yo'q — o'tkazib yuboriladi
SKIP_FILES = {"curriculum.json", "audio_manifest.json"}


def _text_of(obj: dict) -> str | None:
    return (
        obj.get("audio_text")
        or obj.get("ar")
        or obj.get("arabic")
        or obj.get("hejazi_ar")
        or obj.get("transcript_ar")
        or obj.get("text_ar")  # o'qish matnlari (content/reading/*.json)
        or obj.get("root")
    )


def collect(with_sources: bool = False):
    """audio fayl yo'li -> matn (with_sources: fayl -> matn -> manbalar)."""
    found: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    def scan(obj, src: str):
        if isinstance(obj, dict):
            audio = obj.get("audio")
            if audio:
                text = _text_of(obj)
                if text:
                    found[audio][text].append(src)
            for v in obj.values():
                scan(v, src)
        elif isinstance(obj, list):
            for v in obj:
                scan(v, src)

    for f in sorted(CONTENT_DIR.rglob("*.json")):
        if f.name in SKIP_FILES:
            continue
        scan(json.loads(f.read_text(encoding="utf-8")), f.stem)

    if with_sources:
        return found
    return {name: next(iter(texts)) for name, texts in found.items()}


def find_conflicts() -> dict[str, dict[str, list[str]]]:
    """Bitta audio fayliga BIR NECHA xil matn biriktirilgan joylar.

    Bu jim buzuqlik: qaysi matn birinchi uchrasa, o'sha yoziladi va qolgan
    darslar boshqa so'zning (yoki harfning) ovozini chaladi.
    """
    return {
        name: dict(texts)
        for name, texts in collect(with_sources=True).items()
        if len(texts) > 1
    }


def _key(text: str) -> str:
    """Matn + ovoz + tezlik + balandlik xeshi — biri o'zgarsa qayta yaratiladi."""
    spoken, rate = voice_plan(text)
    return hashlib.sha256(
        f"{VOICE}|{rate}|{VOLUME}|{spoken}".encode()
    ).hexdigest()[:16]


def load_manifest() -> dict[str, str]:
    if not MANIFEST.exists():
        return {}
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return {}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="faqat tekshirish")
    ap.add_argument("--force", action="store_true", help="hammasini qayta yaratish")
    args = ap.parse_args()

    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    conflicts = find_conflicts()
    if conflicts:
        print(f"❌ {len(conflicts)} ta audio fayliga bir nechta matn biriktirilgan:\n")
        for name, texts in sorted(conflicts.items()):
            print(f"  {name}")
            for t, srcs in texts.items():
                print(f"      {t!r}  <- {sorted(set(srcs))}")
        print("\nHar bir audio faylga BITTA matn bo'lishi kerak.")
        return 1

    tasks = collect()
    manifest = {} if args.force else load_manifest()

    stale = [
        (n, t)
        for n, t in tasks.items()
        if manifest.get(n) != _key(t) or not (OUT_DIR / n).exists()
    ]

    if args.check:
        if stale:
            print(f"❌ {len(stale)} ta audio eskirgan yoki yo'q:")
            for n, t in stale[:20]:
                print(f"  - {n}  ({t})")
            return 1
        print(f"✅ {len(tasks)} ta audio dolzarb.")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    made = failed = 0
    sem = asyncio.Semaphore(CONCURRENCY)
    done = 0

    async def one(name: str, text: str):
        nonlocal made, failed, done
        out = OUT_DIR / name
        out.parent.mkdir(parents=True, exist_ok=True)  # a0/, hj/, roots/ kabi
        spoken, rate = voice_plan(text)
        async with sem:
            for attempt in range(3):  # tarmoq uzilishi bo'lsa qayta urinadi
                try:
                    await edge_tts.Communicate(
                        spoken, VOICE, rate=rate, volume=VOLUME
                    ).save(str(out))
                    manifest[name] = _key(text)
                    made += 1
                    break
                except Exception as e:
                    if attempt == 2:
                        failed += 1
                        print(f"  ! {name} XATO: {e}", flush=True)
                    else:
                        await asyncio.sleep(1 + attempt)
        done += 1
        if done % 50 == 0:
            print(f"  ... {done}/{len(stale)}", flush=True)

    await asyncio.gather(*(one(n, t) for n, t in stale))

    # Kontentdan olib tashlangan yozuvlarni manifestdan tozalaymiz
    manifest = {n: h for n, h in manifest.items() if n in tasks}
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8",
    )

    print(
        f"\nJami: {len(tasks)} | yangilandi: {made} | "
        f"o'zgarmagan: {len(tasks) - len(stale)} | xato: {failed}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
