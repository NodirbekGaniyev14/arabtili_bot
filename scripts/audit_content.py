"""Kontent auditi — o'yin buziladigan jim xatolarni topadi.

validate_content.py sxemani tekshiradi; bu skript esa MANTIQIY nosozliklarni:
  - mcq savolida to'g'ri javob variantlar ichida yo'q (javob berib bo'lmaydi),
  - variantlar takrorlangan yoki 2 tadan kam,
  - mavjud bo'lmagan audio faylga havola (jim tugma),
  - dars/modul tuzilishi: kurikulumda modul lessonlari uzluksiz emasmi,
  - mikro-test juda kichik (qayta topshirishda savol yetmaydi),
  - build_word / match_root savollarida o'zak yoki vazn yo'q.

Ishlatish:
    python scripts/audit_content.py            # hammasi
    python scripts/audit_content.py --level a0
"""

import argparse
import json
import sys
from collections import defaultdict
from itertools import groupby
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
AUDIO_DIR = ROOT / "webapp" / "public" / "audio"

MIN_MICRO_TEST = 5


def audio_exists(name: str) -> bool:
    return bool(name) and (AUDIO_DIR / name).exists()


def check_items(
    items: list[dict], where: str, problems: list[str], need_answer: bool = True
) -> None:
    for i, it in enumerate(items):
        tag = f"{where}[{i}] ({it.get('type', '?')})"
        typ = it.get("type", "")
        answer = str(it.get("answer", "")).strip()
        options = [str(o) for o in it.get("options") or []]

        if need_answer and not answer and typ != "shadowing":
            problems.append(f"{tag}: javob bo'sh")

        if options:
            if len(options) < 2:
                problems.append(f"{tag}: variant 2 tadan kam")
            if len(set(options)) != len(options):
                problems.append(f"{tag}: variantlar takrorlangan — {options}")
            if answer and answer not in options:
                problems.append(
                    f"{tag}: TO'G'RI JAVOB VARIANTLAR ICHIDA YO'Q "
                    f"(answer={answer!r}, options={options})"
                )
        elif typ == "mcq":
            problems.append(f"{tag}: mcq da variant yo'q")

        if typ == "match_root" and not (
            str(it.get("q_ar", "")).strip() or str(it.get("q_uz", "")).strip()
        ):
            problems.append(f"{tag}: match_root da so'z ko'rsatilmagan")
        if typ == "build_word" and not (it.get("root") and it.get("pattern")):
            problems.append(f"{tag}: build_word da o'zak yoki vazn yo'q")
        if typ == "order_words" and len(it.get("words") or []) < 2:
            problems.append(f"{tag}: order_words da so'zlar yo'q")
        if typ in ("dictation", "shadowing") and not audio_exists(it.get("audio", "")):
            problems.append(f"{tag}: audio yo'q — {it.get('audio')!r}")
        if it.get("audio") and not audio_exists(it["audio"]):
            problems.append(f"{tag}: audio fayl topilmadi — {it['audio']!r}")


def audit_lesson(path: Path) -> list[str]:
    problems: list[str] = []
    data = json.loads(path.read_text(encoding="utf-8"))

    micro = data.get("micro_test") or []
    if len(micro) < MIN_MICRO_TEST:
        problems.append(f"micro_test faqat {len(micro)} savol (kamida {MIN_MICRO_TEST})")
    check_items(micro, "micro_test", problems)

    for i, v in enumerate(data.get("vocabulary") or []):
        if v.get("audio") and not audio_exists(v["audio"]):
            problems.append(f"vocabulary[{i}] {v.get('ar')}: audio yo'q — {v['audio']}")
        if not str(v.get("uz", "")).strip():
            problems.append(f"vocabulary[{i}] {v.get('ar')}: o'zbekcha tarjima yo'q")

    for i, h in enumerate(data.get("hejazi") or []):
        if h.get("audio") and not audio_exists(h["audio"]):
            problems.append(f"hejazi[{i}]: audio yo'q — {h['audio']}")

    skills = data.get("skills") or {}
    lis = skills.get("listening") or {}
    if lis.get("audio") and not audio_exists(lis["audio"]):
        problems.append(f"skills.listening: audio yo'q — {lis['audio']}")
    if not lis.get("audio"):
        problems.append("skills.listening: audio biriktirilmagan")

    return problems


def audit_exam_pools() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for f in sorted((CONTENT / "exams").glob("*_pool.json")):
        problems: list[str] = []
        pool = json.loads(f.read_text(encoding="utf-8"))
        cfg = pool.get("config", {})
        for section in ("reading", "listening", "speaking", "passages"):
            items = pool.get(section) or []
            need = cfg.get(section, 0)
            if need and len(items) < need * 3:
                problems.append(
                    f"{section}: {len(items)} savol — 3 xil urinish uchun "
                    f"{need * 3} kerak (imtihonda {need} ta so'raladi)"
                )
            if section == "passages":
                for i, p in enumerate(items):
                    check_items(p.get("questions") or [], f"passages[{i}].questions", problems)
                    if p.get("audio") and not audio_exists(p["audio"]):
                        problems.append(f"passages[{i}]: audio yo'q — {p['audio']}")
            else:
                # gapirish bo'limi o'z-o'zini baholaydi — to'g'ri javob talab qilinmaydi
                check_items(
                    items, section, problems, need_answer=section != "speaking"
                )
        need_w = cfg.get("writing", 0)
        if need_w and len(pool.get("writing") or []) < need_w * 3:
            problems.append(
                f"writing: {len(pool.get('writing') or [])} topshiriq — "
                f"{need_w * 3} kerak"
            )
        if problems:
            out[f.stem] = problems
    return out


def audit_structure() -> tuple[list[str], list[str]]:
    """(muammolar, eslatmalar) — tuzilma tekshiruvi."""
    problems: list[str] = []
    notes: list[str] = []
    cur = json.loads((CONTENT / "curriculum.json").read_text(encoding="utf-8"))["lessons"]
    written = {f.stem for f in (CONTENT / "modules").rglob("*.json")}

    for lvl in ("A0", "A1", "A2", "B1"):
        ids = [l for l in cur if l["level"] == lvl and l["type"] == "lesson"]
        runs = [k for k, _ in groupby(ids, key=lambda l: l["module"])]
        seen: set[str] = set()
        for m in runs:
            if m in seen:
                # course.py bunday modulni ALOHIDA karta qilib ko'rsatadi
                # («... (davomi)»), shuning uchun bu muammo emas — eslatma.
                notes.append(
                    f"{lvl}: «{m}» moduli kursda ikki joyda — Darslar sahifasida "
                    f"«(davomi)» kartasi bo'lib ko'rinadi"
                )
            seen.add(m)
        missing = [l["id"] for l in ids if l["id"] not in written]
        if missing:
            problems.append(f"{lvl}: kontenti yo'q darslar — {missing}")

    return problems, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="", help="a0 | a1 | a2 | b1")
    args = ap.parse_args()

    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    levels = [args.level] if args.level else ["a0", "a1", "a2", "b1"]
    total = 0
    by_level: dict[str, dict[str, list[str]]] = defaultdict(dict)

    for lvl in levels:
        d = CONTENT / "modules" / lvl
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            pr = audit_lesson(f)
            if pr:
                by_level[lvl][f.stem] = pr
                total += len(pr)

    for lvl, lessons in by_level.items():
        print(f"\n═══ {lvl.upper()} ═══")
        for lid, pr in lessons.items():
            print(f"\n  {lid}:")
            for p in pr:
                print(f"    • {p}")

    struct, notes = audit_structure()
    if struct or notes:
        print("\n═══ TUZILMA ═══")
        for p in struct:
            print(f"  • {p}")
        for n in notes:
            print(f"  ℹ {n}")
        total += len(struct)

    pools = audit_exam_pools()
    if pools:
        print("\n═══ IMTIHON BANKLARI ═══")
        for name, pr in pools.items():
            print(f"\n  {name}:")
            for p in pr:
                print(f"    • {p}")
            total += len(pr)

    print(f"\nJami muammo: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
