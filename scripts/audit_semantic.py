"""Kontent auditi (K29.5) — MA'NO jihatidan jim xatolar: o'quvchi «to'g'ri javobim xato hisoblandi» deydigan joylar.

audit_content.py tuzilmani tekshiradi; bu skript savol/javob/audio MUVOFIQLIGINI:
  1. audio-javob   — «Eshiting va ... toping» / diktant: audio aytayotgan matn javobga mos emas;
  2. lookalike     — variantlardan ikkitasi harakatsiz yozilganda bir xil (مُعَلِّم ↔ مُعَلَّم) — o'quvchi ajrata olmaydi;
  3. dup-meaning   — o'zbekcha variantlardan ikkitasi tinish/qavsdan tashqari bir xil;
  4. letter-pairs  — harf tinglash savolida ovozi o'xshash juft (خ/ح, ص/س…) birga kelgan — izoh (option_notes) kerak.

Ishlatish:  python scripts/audit_semantic.py [--json]
Chiqish kodi: 1 — «audio-javob» yoki «dup-meaning» topilsa (haqiqiy nosozlik); lookalike/letter-pairs — ma'lumot.
"""

import importlib.util
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"

_spec = importlib.util.spec_from_file_location("build_audio", CONTENT / "build_audio.py")
build_audio = importlib.util.module_from_spec(_spec)
sys.modules["build_audio"] = build_audio
_spec.loader.exec_module(build_audio)

_HARAKAT = re.compile("[ً-ٰٟـ]")

# Harf nomi → harf (audio matni nomi, javob esa harfning o'zi)
LETTER_OF_NAME = {
    "أَلِف": "ا", "بَاء": "ب", "تَاء": "ت", "ثَاء": "ث", "جِيم": "ج", "حَاء": "ح", "خَاء": "خ", "دَال": "د",
    "ذَال": "ذ", "رَاء": "ر", "زَاي": "ز", "سِين": "س", "شِين": "ش", "صَاد": "ص", "ضَاد": "ض", "طَاء": "ط",
    "ظَاء": "ظ", "عَيْن": "ع", "غَيْن": "غ", "فَاء": "ف", "قَاف": "ق", "كَاف": "ك", "لَام": "ل", "مِيم": "م",
    "نُون": "ن", "هَاء": "ه", "وَاو": "و", "يَاء": "ي", "هَمْزَة": "ء",
}
# Eshitilishi yaqin harflar — tinglash savolida birga kelsa o'quvchi adashadi
CONFUSABLE = [set("خحه"), set("غع"), set("صس"), set("ضد"), set("طت"), set("ظذز"), set("قك"), set("ثسش"), set("ءعا")]


def bare(s: str) -> str:
    s = _HARAKAT.sub("", s or "")
    s = re.sub("[أإآٱ]", "ا", s)
    return " ".join(re.sub(r"[.,،؟!:؛?]", " ", s).split())


def latnorm(s: str) -> str:
    s = re.sub(r"\([^)]*\)", " ", s.lower())
    s = re.sub(r"[^a-z0-9Ѐ-ӿ ]", "", s.replace("'", "").replace("’", "").replace("ʻ", ""))
    return " ".join(s.split())


def is_ar(s: str) -> bool:
    return any("؀" <= c <= "ۿ" for c in s)


def audio_texts() -> dict[str, str]:
    return build_audio.collect()


def iter_items():
    """(manba, indeks, element) — darslar mikro-testi va imtihon banklari."""
    for f in sorted((CONTENT / "modules").rglob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for i, it in enumerate(d.get("micro_test", []) if isinstance(d, dict) else []):
            yield f"{f.stem}", i, it
    for f in sorted((CONTENT / "exams").glob("*_pool.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for sec in ("reading", "listening"):
            for i, it in enumerate(d.get(sec, [])):
                yield f"{f.stem}:{sec}", i, it


def audit() -> dict[str, list[str]]:
    texts = audio_texts()
    out: dict[str, list[str]] = {"audio-javob": [], "lookalike": [], "dup-meaning": [], "letter-pairs": []}
    for src, i, it in iter_items():
        tag = f"{src}[{i}]"
        typ = it.get("type", "")
        answer = str(it.get("answer", "")).strip()
        options = [str(o) for o in it.get("options") or []]
        audio = it.get("audio") or ""
        atext = texts.get(audio, "")

        # 1. audio ↔ javob
        if audio and atext and answer and (typ in ("dictation", "shadowing") or str(it.get("q_uz", "")).startswith("Eshiting")):
            if atext in LETTER_OF_NAME:  # harf nomi → harf
                if answer != LETTER_OF_NAME[atext] and bare(answer) != LETTER_OF_NAME[atext]:
                    out["audio-javob"].append(f"{tag}: audio {audio} = «{atext}» ({LETTER_OF_NAME[atext]}), javob «{answer}»")
            elif is_ar(answer):
                # podkast/matn bo'yicha savol: javob (qavs izohisiz) audio matnida uchrasa — mos
                core = bare(re.sub(r"\([^)]*\)", "", answer))
                if core and core not in bare(atext):
                    out["audio-javob"].append(f"{tag}: audio {audio} = «{atext}», javob «{answer}»")

        # 2. lookalike (harakatsiz bir xil)
        if len(options) >= 2 and any(is_ar(o) for o in options):
            groups: dict[str, list[str]] = {}
            for o in options:
                groups.setdefault(bare(o), []).append(o)
            for k, g in groups.items():
                if len(g) > 1:
                    mark = "JAVOB BILAN" if answer in g else "distraktorlar"
                    out["lookalike"].append(f"{tag}: {mark} — {g} | savol: {str(it.get('q_uz', ''))[:50]}")

        # 3. o'zbekcha variantlar ma'nodosh/bir xil
        if len(options) >= 2 and not any(is_ar(o) for o in options):
            seen: dict[str, str] = {}
            for o in options:
                k = latnorm(o)
                if k and k in seen and seen[k] != o:
                    out["dup-meaning"].append(f"{tag}: «{seen[k]}» ≈ «{o}"+"»")
                seen.setdefault(k, o)

        # 4. harf tinglash: ovozi yaqin juftlar
        if audio and atext in LETTER_OF_NAME and len(options) >= 2 and not it.get("option_notes"):
            letters = [o for o in options if len(bare(o)) == 1]
            for grp in CONFUSABLE:
                hit = [o for o in letters if o in grp]
                if answer in hit and len(hit) > 1:
                    out["letter-pairs"].append(f"{tag}: audio {atext} — variantlar {options} (yaqin: {hit}), izoh yo'q")
                    break
    return out


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    res = audit()
    if "--json" in sys.argv:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        for k, v in res.items():
            print(f"\n== {k}: {len(v)}")
            for line in v[:60]:
                print("  ", line)
            if len(v) > 60:
                print(f"   ... yana {len(v) - 60} ta")
    return 1 if res["audio-javob"] or res["dup-meaning"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
