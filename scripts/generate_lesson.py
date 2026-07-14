"""Dars generatsiya CLI.

Ishlatish:
  python scripts/generate_lesson.py a0-22            # bitta dars
  python scripts/generate_lesson.py a0-01 a0-02 ...  # bir nechta
  python scripts/generate_lesson.py --level a0       # butun daraja (imtihonsiz)
  --force  : mavjud faylni ham qayta yozadi
  --review : generatsiyadan keyin tekshiruv varag'ini ham yozadi (docs/review/)
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from services.curriculum import lesson_file, load_curriculum  # noqa: E402
from services.lesson_gen import generate_lesson, review_sheet  # noqa: E402


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    review = "--review" in sys.argv

    cur = load_curriculum()

    if "--level" in sys.argv:
        level = args[0].lower() if args else ""
        ids = [
            l for l, m in cur.items()
            if l.startswith(level + "-") and m["type"] == "lesson"
        ]
    else:
        ids = args

    if not ids:
        print(__doc__)
        return

    ok = failed = skipped = 0
    for lid in ids:
        if lid not in cur:
            print(f"✗ {lid}: curriculum'da yo'q")
            failed += 1
            continue
        if lesson_file(lid).exists() and not force:
            print(f"· {lid}: mavjud (--force bilan qayta yozing)")
            skipped += 1
            continue

        print(f"→ {lid} generatsiya qilinmoqda...")
        try:
            data, errors, warnings = await generate_lesson(lid)
        except Exception as e:
            print(f"✗ {lid}: API xatosi: {e!r}")
            failed += 1
            continue

        for w in warnings:
            print(f"  ⚠ {w}")
        if errors:
            for e in errors:
                print(f"  ✗ {e}")
            print(f"✗ {lid}: validatsiyadan O'TMADI (saqlanmadi)")
            failed += 1
            continue

        n_vocab = len(data.get("vocabulary", []))
        n_test = len(data.get("micro_test", []))
        print(f"✓ {lid}: saqlandi ({n_vocab} so'z, {n_test} test, {len(warnings)} ogohlantirish)")
        ok += 1

        if review:
            rdir = ROOT / "docs" / "review"
            rdir.mkdir(parents=True, exist_ok=True)
            (rdir / f"{lid}.md").write_text(review_sheet(lid), encoding="utf-8")
            print(f"  📝 docs/review/{lid}.md")

    print(f"\nJami: ✓{ok} ✗{failed} ·{skipped}")


if __name__ == "__main__":
    asyncio.run(main())
