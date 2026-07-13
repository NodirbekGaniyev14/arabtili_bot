"""Dars kontentini content/modules/*.json dan yuklab beradi."""

import json
from functools import lru_cache
from pathlib import Path

from config import BASE_DIR

CONTENT_DIR = BASE_DIR / "content" / "modules"

# Kanonik tartib (yangi modul qo'shilsa shu yerga yoziladi)
CANONICAL_ORDER = ["alphabet", "greetings", "introduction"]

# Rejada bo'lishi mumkin, lekin hali yozilmagan modullar (UI'da "tez orada")
PLANNED_TITLES = {
    "family": "Oila",
    "numbers": "Sonlar 1-10",
    "colors": "Ranglar va sifatlar",
    "home": "Uy va narsalar",
    "food": "Ovqat va ichimlik",
    "verbs": "Kunlik ishlar (fe'llar)",
}


@lru_cache(maxsize=1)
def load_modules() -> dict[str, dict]:
    modules: dict[str, dict] = {}
    for f in sorted(CONTENT_DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        modules[data["id"]] = data
    return modules


@lru_cache(maxsize=1)
def lesson_index() -> dict[str, dict]:
    """lesson_id -> {lesson, module_id, module_title, pos, count}"""
    idx: dict[str, dict] = {}
    for mod in load_modules().values():
        lessons = mod.get("lessons", [])
        for i, lesson in enumerate(lessons):
            idx[lesson["id"]] = {
                "lesson": lesson,
                "module_id": mod["id"],
                "module_title": mod["title"],
                "module_ar": mod.get("arabic_title", ""),
                "pos": i + 1,
                "count": len(lessons),
            }
    return idx


def ordered_module_ids(plan_order: list[str] | None) -> list[str]:
    """Foydalanuvchi rejasidagi tartib; mavjud modullar birinchi."""
    available = [m for m in (plan_order or []) if m in load_modules()]
    for m in CANONICAL_ORDER:
        if m not in available:
            available.append(m)
    return available


def flattened_lessons(plan_order: list[str] | None) -> list[str]:
    """Butun kurs bo'ylab darslarning chiziqli tartibi (qulf ochish uchun)."""
    modules = load_modules()
    result: list[str] = []
    for mid in ordered_module_ids(plan_order):
        result.extend(lesson["id"] for lesson in modules[mid]["lessons"])
    return result


def count_words(lesson: dict) -> int:
    """Darsdagi 'so'z' sifatida sanaladigan elementlar (harflar emas)."""
    return sum(
        1 for it in lesson.get("new_items", []) if it.get("kind") != "letter"
    )
