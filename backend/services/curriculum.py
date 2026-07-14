"""Curriculum v2 loader — 160 darslik yangi tuzilma.

Eski services/content.py (v1, jonli kurs) ga TEGMAYDI — parallel ishlaydi.
K4 da API'lar shu loader'ga o'tkaziladi.
"""

import json
from functools import lru_cache
from pathlib import Path

from config import BASE_DIR

CONTENT_DIR = BASE_DIR / "content"
CURRICULUM_PATH = CONTENT_DIR / "curriculum.json"


@lru_cache(maxsize=1)
def load_curriculum() -> dict[str, dict]:
    """lesson_id -> meta (curriculum.json'dan)."""
    data = json.loads(CURRICULUM_PATH.read_text(encoding="utf-8"))
    return {l["id"]: l for l in data["lessons"]}


@lru_cache(maxsize=1)
def lesson_order() -> list[str]:
    """Barcha 160 dars ID'si to'g'ri tartibda (A0 → B1)."""
    data = json.loads(CURRICULUM_PATH.read_text(encoding="utf-8"))
    return [l["id"] for l in data["lessons"]]


def lesson_file(lesson_id: str) -> Path:
    level = lesson_id.split("-")[0]  # a0-22 -> a0
    return CONTENT_DIR / "modules" / level / f"{lesson_id}.json"


def load_lesson_v2(lesson_id: str) -> dict | None:
    f = lesson_file(lesson_id)
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def written_lesson_ids() -> set[str]:
    """Kontenti yozib bo'lingan darslar."""
    result = set()
    for level_dir in (CONTENT_DIR / "modules").iterdir():
        if level_dir.is_dir():
            result.update(f.stem for f in level_dir.glob("*.json"))
    return result


def prerequisites_met(done: set[str], lesson_id: str) -> bool:
    meta = load_curriculum().get(lesson_id)
    if not meta:
        return False
    return all(p in done for p in meta.get("prerequisites", []))


@lru_cache(maxsize=1)
def load_roots() -> list[dict]:
    f = CONTENT_DIR / "roots.json"
    return json.loads(f.read_text(encoding="utf-8"))["roots"] if f.exists() else []


@lru_cache(maxsize=1)
def load_patterns() -> list[dict]:
    f = CONTENT_DIR / "patterns.json"
    return json.loads(f.read_text(encoding="utf-8"))["patterns"] if f.exists() else []


@lru_cache(maxsize=1)
def load_hejazi() -> list[dict]:
    f = CONTENT_DIR / "hejazi.json"
    return json.loads(f.read_text(encoding="utf-8"))["phrases"] if f.exists() else []
