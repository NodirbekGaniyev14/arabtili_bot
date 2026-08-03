"""Lug'at bazasini tekshiradi — content/vocab/*.json (K16).

docs/VOCAB_PLAN.md §3 dagi 11 qoida. Qo'lda yozilgan so'zlarda eng ko'p
uchraydigan xatolarni ushlaydi: takror so'z, harakat yo'qligi, o'zbekcha
matnga kirill harfi sizib kirishi, misol jumlada so'zning o'zi yo'qligi,
audio slug takrori.

Ishlatish:
    python scripts/validate_vocab.py             # hammasi
    python scripts/validate_vocab.py --level a0  # bitta daraja
    python scripts/validate_vocab.py --strict    # ogohlantirish ham xato sanaladi
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
VOCAB_DIR = CONTENT / "vocab"
AUDIO_DIR = ROOT / "webapp" / "public" / "audio"

sys.path.insert(0, str(ROOT / "backend"))

from services.vocab import LEVELS, POS, TARGETS, THEMES  # noqa: E402

# Harakat siyosati (docs/ARABIY_CURRICULUM.md §2.6)
HARAKAT_REQUIRED = {"A0": True, "A1": True, "A2": True, "B1": False, "B2": False}

CYRILLIC_LOOKALIKES = "оеасрухОЕАСРУХіїқғҳ"

ARABIC_RE = re.compile(r"[؀-ۿ]")
NON_ARABIC_RE = re.compile(r"[A-Za-zЀ-ӿ]")
HARAKAT_RE = re.compile(r"[ً-ْٰ]")
SLUG_RE = re.compile(r"^vocab/[a-z0-9_]+\.mp3$")
ROOT_RE = re.compile(r"^[؀-ۿ](?: [؀-ۿ]){2,3}$")

# Harakat talab qilinmaydigan harflar (cho'ziq unlilar va sukunli tashuvchilar)
NO_HARAKAT_LETTERS = "اويىةءآأإئؤ"

REQUIRED_FIELDS = ("id", "rank", "ar", "translit", "uz", "pos", "level", "theme")


def strip_harakat(s: str) -> str:
    return HARAKAT_RE.sub("", s or "")


def normalize(s: str) -> str:
    """reference.normalize bilan bir xil — takrorni shu shaklda solishtiramiz."""
    s = unicodedata.normalize("NFKC", s or "").lower().strip()
    s = strip_harakat(s)
    s = re.sub(r"[أإآٱ]", "ا", s)
    s = re.sub(r"[ىي]", "ي", s)
    s = re.sub(r"[ةه]", "ه", s)
    s = re.sub(r"['`ʼ’‘ʻʿ]", "", s)
    return re.sub(r"\s+", " ", s)


def lesson_words() -> dict[str, str]:
    """Darslardagi so'zlar: normallashtirilgan shakl -> dars id."""
    from services.reference import vocab_entries  # noqa: E402

    return {normalize(e["ar"]): (e["lessons"] or ["?"])[0] for e in vocab_entries()}


def harakat_ok(text: str) -> bool:
    """Har undoshda harakat bormi. Ibora bo'lsa har so'z alohida tekshiriladi
    (har so'zning oxirgi harfi vaqf holatida harakatsiz qolishi mumkin)."""
    parts = text.split()
    if len(parts) > 1:
        return all(_one_word_harakat_ok(p) for p in parts)
    return _one_word_harakat_ok(text)


def _one_word_harakat_ok(word: str) -> bool:
    letters = [c for c in word if ARABIC_RE.match(c) and not HARAKAT_RE.match(c)]
    if not letters:
        return False
    for i, c in enumerate(word):
        if not ARABIC_RE.match(c) or HARAKAT_RE.match(c):
            continue
        if c in NO_HARAKAT_LETTERS or c == "ٰ":
            continue
        nxt = word[i + 1] if i + 1 < len(word) else ""
        # Oxirgi harf harakatsiz qolishi mumkin (vaqf)
        rest = word[i + 1 :]
        is_last = not any(ARABIC_RE.match(x) and not HARAKAT_RE.match(x) for x in rest)
        if is_last:
            continue
        if not HARAKAT_RE.match(nxt):
            return False
    return True


def check_word(
    w: dict,
    level: str,
    seen_ar: dict[str, str],
    seen_id: set[str],
    seen_rank: dict[int, str],
    seen_audio: dict[str, str],
    in_lessons: dict[str, str],
    problems: list[str],
    warnings: list[str],
) -> None:
    tag = f"{w.get('id', '?')} {w.get('ar', '?')}"

    for f in REQUIRED_FIELDS:
        if w.get(f) in (None, ""):
            problems.append(f"{tag}: «{f}» maydoni bo'sh")

    ar = (w.get("ar") or "").strip()
    key = normalize(ar)

    # 1. Takror — baza ichida va darslar bilan
    if key:
        if key in seen_ar:
            problems.append(f"{tag}: TAKROR — {seen_ar[key]} da bor")
        else:
            seen_ar[key] = w.get("id", level)
        if key in in_lessons:
            problems.append(f"{tag}: darsda bor ({in_lessons[key]}) — bazaga qo'shilmasin")

    # 2. Arab yozuvi
    for f in ("ar", "example_ar", "plural_ar", "past_ar", "present_ar", "masdar_ar"):
        val = (w.get(f) or "").strip()
        if val and NON_ARABIC_RE.search(val):
            problems.append(f"{tag}: «{f}» da arab bo'lmagan harf — {val!r}")
    if ar and not ARABIC_RE.search(ar):
        problems.append(f"{tag}: «ar» arabcha emas")

    # 3. Harakat
    if ar and HARAKAT_REQUIRED.get(level, False) and not harakat_ok(ar):
        problems.append(f"{tag}: {level} darajada har undoshga harakat kerak")

    # 4. O'zbekcha matn — kirill harflari va lotin so'z ichiga tushib qolgan
    #    arabcha harf («shu» o'rniga «شu») ushlanadi
    for f in ("uz", "example_uz", "note_uz"):
        val = w.get(f) or ""
        found = {c: val.count(c) for c in CYRILLIC_LOOKALIKES if c in val}
        if found:
            problems.append(f"{tag}: «{f}» da KIRILL harflari — {found}")

    if ARABIC_RE.search(w.get("example_uz") or ""):
        problems.append(f"{tag}: «example_uz» da arabcha harf bor")

    # Izoh va ma'noda arabcha misol bo'lishi mumkin, ammo lotin so'zga yopishmasin
    # («shu» o'rniga «شu» kabi terish xatosi)
    for f in ("uz", "note_uz"):
        for m in re.finditer(r"[A-Za-z][؀-ۿ]|[؀-ۿ][A-Za-z]", w.get(f) or ""):
            problems.append(f"{tag}: «{f}» da arabcha harf lotin so'zga yopishgan — {m.group()!r}")

    # 5. O'zak
    root = (w.get("root") or "").strip()
    if root and not ROOT_RE.match(root):
        problems.append(f"{tag}: o'zak formati «ك ت ب» bo'lsin — {root!r}")

    # 7. Turkum
    if w.get("pos") and w["pos"] not in POS:
        problems.append(f"{tag}: pos noma'lum — {w['pos']!r} ({', '.join(POS)})")
    if w.get("level") != level:
        problems.append(f"{tag}: level={w.get('level')!r}, fayl esa {level}")

    # 8. Misol jumla so'zni o'z ichiga olsin
    ex = (w.get("example_ar") or "").strip()
    if not ex:
        problems.append(f"{tag}: misol jumla yo'q")
    elif ar:
        # Ayol jinsidagi ة egalik qo'shimchasi bilan ت ga aylanadi (عَمَّة > عَمَّتِي).
        # Ibora bo'lsa har so'z alohida qidiriladi (orada ال tushishi mumkin).
        bare_ex = strip_harakat(ex)
        for part in strip_harakat(ar).split():
            stem = part[:-1] if len(part) >= 3 and part[-1] in "ةه" else part
            if stem and stem not in bare_ex:
                warnings.append(f"{tag}: misol jumlada «{part}» ko'rinmadi")
    if ex and not (w.get("example_uz") or "").strip():
        problems.append(f"{tag}: misol jumlaning tarjimasi yo'q")

    # 9. Audio
    audio = (w.get("audio") or "").strip()
    if not audio:
        problems.append(f"{tag}: audio maydoni bo'sh")
    elif not SLUG_RE.match(audio):
        problems.append(f"{tag}: audio nomi «vocab/<slug>.mp3» bo'lsin — {audio!r}")
    elif audio in seen_audio:
        problems.append(f"{tag}: audio nomi takrorlangan — {seen_audio[audio]}")
    else:
        seen_audio[audio] = w.get("id", "")
        if not (AUDIO_DIR / audio).exists():
            warnings.append(f"{tag}: audio fayli hali yo'q — {audio}")

    # 10. id va rank
    wid = w.get("id", "")
    if wid in seen_id:
        problems.append(f"{tag}: id takrorlangan")
    seen_id.add(wid)
    rank = w.get("rank")
    if isinstance(rank, int) and rank > 0:
        if not 1 <= rank <= 6000:
            problems.append(f"{tag}: rank 1..6000 oralig'ida bo'lsin — {rank}")
        if rank in seen_rank:
            problems.append(f"{tag}: rank takrorlangan — {seen_rank[rank]}")
        seen_rank[rank] = wid
        if wid != f"v-{rank:04d}":
            problems.append(f"{tag}: id «v-{rank:04d}» bo'lishi kerak")
    else:
        problems.append(f"{tag}: rank butun son bo'lsin")

    if w.get("theme") and w["theme"] not in THEMES:
        problems.append(f"{tag}: mavzu noma'lum — {w['theme']!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    levels = [args.level.upper()] if args.level else list(LEVELS)
    in_lessons = lesson_words()

    seen_ar: dict[str, str] = {}
    seen_id: set[str] = set()
    seen_rank: dict[int, str] = {}
    seen_audio: dict[str, str] = {}
    total = 0
    all_problems = 0
    all_warnings = 0

    for level in levels:
        path = VOCAB_DIR / f"{level.lower()}.json"
        if not path.exists():
            print(f"✗ {level}: fayl yo'q — {path}")
            all_problems += 1
            continue

        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        words = data.get("words", [])
        problems: list[str] = []
        warnings: list[str] = []

        if data.get("level") != level:
            problems.append(f"fayl «level» maydoni {data.get('level')!r}, kutilgani {level}")

        for w in words:
            check_word(
                w, level, seen_ar, seen_id, seen_rank, seen_audio,
                in_lessons, problems, warnings,
            )

        # 11. Daraja hajmi (maqsad — darsdagi so'zlar bilan birga)
        target = TARGETS[level]
        got = len(words)
        total += got
        all_problems += len(problems)
        all_warnings += len(warnings)

        mark = "✓" if not problems else "✗"
        print(f"{mark} {level}: {got} so'z · {len(problems)} xato · {len(warnings)} ogohlantirish (maqsad {target})")
        for p in problems[:40]:
            print(f"    ✗ {p}")
        if len(problems) > 40:
            print(f"    … yana {len(problems) - 40} xato")
        for wmsg in warnings[:15]:
            print(f"    ⚠ {wmsg}")
        if len(warnings) > 15:
            print(f"    … yana {len(warnings) - 15} ogohlantirish")

    print(f"\nJami: {total} so'z · {all_problems} xato · {all_warnings} ogohlantirish")
    if args.strict:
        return 1 if (all_problems or all_warnings) else 0
    return 1 if all_problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
