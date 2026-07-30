"""Bosqichma-bosqich o'qish (reading) moduli — A2 dan boshlab (K14).

Foydalanuvchi talabi: «darslarga o'qish bo'limi qo'shish, A2 dan boshlab
bosqichma-bosqich reading matnlari». Dars ichidagi qisqa `skills.reading`
(1-2 gap) o'rniga bu modul TO'LIQ matn beradi: har bosqichda matn uzayadi,
harakatlar kamayadi va savollar baholanadigan testga aylanadi (javobni
ko'rish emas).

Tuzilishi: `content/reading/a2.json`, `content/reading/b1.json`
  stages[]: {stage, lesson_id, title_uz, words, harakat, text_ar, audio,
             glossary[{ar,uz}], questions[mcq]}

`lesson_id` — matn qaysi darsda ochilishi. Har 4 darsda bittasi qo'yiladi,
shuning uchun o'qish mashqi kursning tabiiy bosqichlariga tushadi.
"""

import json
from functools import lru_cache

from config import BASE_DIR

READING_DIR = BASE_DIR / "content" / "reading"
LEVELS = ("A2", "B1", "B2")


@lru_cache(maxsize=8)
def load_stages(level: str) -> tuple[dict, ...]:
    f = READING_DIR / f"{level.lower()}.json"
    if not f.exists():
        return ()
    data = json.loads(f.read_text(encoding="utf-8"))
    return tuple(data.get("stages", []))


@lru_cache(maxsize=1)
def _by_lesson() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for lvl in LEVELS:
        total = len(load_stages(lvl))
        for st in load_stages(lvl):
            lid = st.get("lesson_id")
            if lid:
                out[lid] = {**st, "level": lvl, "stages_total": total}
    return out


def passage_for(lesson_id: str) -> dict | None:
    """Shu darsda ko'rsatiladigan o'qish matni (bo'lmasa None)."""
    return _by_lesson().get(lesson_id)


def stage_list(level: str) -> list[dict]:
    """Daraja bo'yicha bosqichlar ro'yxati (matnsiz — ko'rsatkich uchun)."""
    return [
        {
            "stage": s["stage"],
            "lesson_id": s["lesson_id"],
            "title_uz": s["title_uz"],
            "words": s.get("words", 0),
        }
        for s in load_stages(level)
    ]
