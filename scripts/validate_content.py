"""Barcha v2 kontentni tekshiradi.

Ishlatish: python scripts/validate_content.py [a0-22 ...]
Argumentsiz — yozilgan barcha darslarni tekshiradi.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from services.curriculum import (  # noqa: E402
    lesson_order,
    load_curriculum,
    load_lesson_v2,
    written_lesson_ids,
)
from services.lesson_schema import validate_lesson  # noqa: E402


def main():
    ids = sys.argv[1:] or sorted(written_lesson_ids())
    if not ids:
        print("Hali yozilgan dars yo'q.")
        return

    cur = load_curriculum()
    known = set(lesson_order())
    total_e = total_w = 0

    for lid in ids:
        data = load_lesson_v2(lid)
        if data is None:
            print(f"✗ {lid}: fayl topilmadi")
            total_e += 1
            continue
        errors, warnings = validate_lesson(data, meta=cur.get(lid), known_lesson_ids=known)
        status = "✓" if not errors else "✗"
        print(f"{status} {lid}: {len(errors)} xato, {len(warnings)} ogohlantirish")
        for e in errors:
            print(f"    ✗ {e}")
        for w in warnings:
            print(f"    ⚠ {w}")
        total_e += len(errors)
        total_w += len(warnings)

    print(f"\nJami: {len(ids)} dars · {total_e} xato · {total_w} ogohlantirish")
    sys.exit(1 if total_e else 0)


if __name__ == "__main__":
    main()
