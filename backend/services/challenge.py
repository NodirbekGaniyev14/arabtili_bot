"""Haftalik chellenj — har dushanba yangilanadigan aralash test.

Maqsad: ko'p dars tugatgan o'rganuvchilar zerikmasin. Savollar foydalanuvchi
TUGATGAN darslardan yig'iladi (checkpoint bilan bir bank), lekin to'plam har
hafta boshqacha bo'ladi — urug' (seed) = hafta + foydalanuvchi.

Urinish `ExamAttempt` da saqlanadi: kind="weekly", checkpoint=<ISO hafta raqami>.
"""

import random
from datetime import datetime

from services.checkpoint import ALLOWED_TYPES, question_bank
from services.league import _week_start_utc

N_QUESTIONS = 10
PASS = 80
XP_REWARD = 40


def week_key(now: datetime | None = None) -> int:
    """Joriy ISO hafta raqami (1-53) — haftalik kalit sifatida."""
    start = _week_start_utc()
    return int(start.isocalendar()[1])


def week_label(now: datetime | None = None) -> str:
    start = _week_start_utc()
    return start.strftime("%d.%m.%Y")


def build_challenge(done_lessons: list[str], user_id: int) -> dict | None:
    """Tugatilgan darslardan haftalik to'plam yig'adi."""
    if not done_lessons:
        return None

    bank = question_bank(done_lessons)
    if not bank:
        return None

    rnd = random.Random(f"{week_key()}-{user_id}")
    rnd.shuffle(bank)
    items = bank[:N_QUESTIONS]

    for it in items:
        if it.get("type") == "mcq" and it.get("options"):
            opts = list(it["options"])
            rnd.shuffle(opts)
            it["options"] = opts

    return {
        "week": week_key(),
        "week_label": week_label(),
        "items": items,
        "pass_score": PASS,
        "xp_reward": XP_REWARD,
        "lessons_pool": len(done_lessons),
    }


def grade(correct: int, total: int) -> dict:
    score = round(100 * correct / total) if total else 0
    return {"score": score, "passed": score >= PASS, "correct": correct, "total": total}


__all__ = [
    "ALLOWED_TYPES",
    "N_QUESTIONS",
    "PASS",
    "XP_REWARD",
    "build_challenge",
    "grade",
    "week_key",
    "week_label",
]
