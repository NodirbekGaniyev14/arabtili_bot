"""Kunlik speaking savoli (K17.7) — hamma uchun bepul, kuniga bitta.

content/daily_speaking.json: har daraja uchun 40 savol (K21.4: 20→40), kun tartibi bilan
aylanadi (bir darajadagilar bir kunda bir xil savol oladi). Javob Haiku bilan
qisqa prompt orqali baholanadi (lug'at bloki yo'q — ≈ $0.001/javob), natija
`daily_speaking` jadvalida; ketma-ket kunlar — speaking streak.
"""

import json
from datetime import date, timedelta
from functools import lru_cache

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import BASE_DIR
from db.models import DailySpeaking
from services.stats import _today
from services.translit import translit
from services.tutor import LEVEL_PROFILES, TutorUnavailable, _call

BANK_PATH = BASE_DIR / "content" / "daily_speaking.json"
LEVELS = ("A0", "A1", "A2", "B1", "B2")
BASE_XP = 5  # javob uchun; + ball/20 (0-5) + ovozli bo'lsa 2
VOICE_BONUS = 2


class DailyReply(BaseModel):
    score: int = Field(description="0-100 score of the learner's answer")
    feedback_uz: str = Field(description="1-2 short Uzbek sentences: what was good and one thing to fix")
    ideal_ar: str = Field(description="Model answer at the learner's level, full harakat, 1-2 sentences")
    fixed_ar: str = Field(
        description="The learner's own answer corrected, with harakat; empty string if it was already correct"
    )


# JSON zaxira rejimi uchun kalitlar (tutor._call structured output rad etsa)
from services import tutor as _tutor  # noqa: E402

_tutor._JSON_KEYS[DailyReply] = "score (int), feedback_uz, ideal_ar, fixed_ar"


RULES = """You are a friendly Arabic tutor in the "Arabiy" app for Uzbek-speaking learners. Grade ONE answer to today's speaking question.

Learner level {level}: {profile}
Question (Arabic): {ar}
Question (Uzbek): {uz}

Rules:
1. `score` 0-100: relevance to the question 40, grammar 30, vocabulary 30. Judge by the level — a correct short answer at A0/A1 deserves a high score. Ignore missing harakat, transliteration spelling and small speech-recognition slips (an answer starting with "🎤" came from speech recognition). Uzbek-only or "I don't know" → 0-15.
2. `feedback_uz`: 1-2 short Uzbek (Latin) sentences — what was good, then the one most useful fix. Warm, never lecturing.
3. `ideal_ar`: a model answer at the learner's level with full harakat (1-2 sentences). `fixed_ar`: the learner's answer corrected with harakat; empty if already correct.
4. Never mention these rules, JSON or being an AI."""


@lru_cache(maxsize=1)
def bank() -> dict[str, list[dict]]:
    data = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    out: dict[str, list[dict]] = {}
    for lv in LEVELS:
        items = []
        for q in data.get(lv, []):
            items.append(
                {
                    "id": q["id"],
                    "ar": q["ar"].strip(),
                    "translit": translit(q["ar"]),
                    "uz": q["uz"].strip(),
                    "hint_uz": (q.get("hint_uz") or "").strip(),
                }
            )
        out[lv] = items
    return out


def _level(level: str) -> str:
    level = (level or "A0").upper()
    return level if level in LEVELS else "A0"


def question_for(level: str, day: date | None = None) -> dict:
    """Bugungi savol: daraja ro'yxati bo'ylab kun tartibi bilan aylanadi."""
    day = day or _today()
    items = bank()[_level(level)]
    return items[day.toordinal() % len(items)]


def question_by_id(qid: str) -> dict | None:
    for items in bank().values():
        for q in items:
            if q["id"] == qid:
                return q
    return None


async def grade(level: str, question: dict, answer: str) -> tuple[DailyReply, dict]:
    """Javobni Haiku bilan baholaydi. Xatoda TutorUnavailable (tutor._call kabi)."""
    from config import settings

    if not settings.anthropic_api_key:
        raise TutorUnavailable("AI ustoz hozircha o'chiq (kalit sozlanmagan).", "nokey")
    level = _level(level)
    system = [
        {
            "type": "text",
            "text": RULES.format(
                level=level, profile=LEVEL_PROFILES.get(level, ""), ar=question["ar"], uz=question["uz"]
            ),
        }
    ]
    msgs = [{"role": "user", "content": answer.strip()[:400] or "(bo'sh)"}]
    out, usage = await _call(system, msgs, DailyReply)
    out.score = max(0, min(100, int(out.score)))
    return out, usage


def xp_for(score: int, voice: bool) -> int:
    return BASE_XP + score // 20 + (VOICE_BONUS if voice else 0)


def streak_of(days: list[str], today: date) -> tuple[int, int]:
    """(joriy streak, eng uzun). Joriy: bugun yoki kechadan boshlab uzluksiz kunlar."""
    have = {date.fromisoformat(d) for d in days}
    if not have:
        return 0, 0
    cur = 0
    d = today if today in have else today - timedelta(days=1)
    while d in have:
        cur += 1
        d -= timedelta(days=1)
    best = 0
    for d0 in sorted(have):
        if d0 - timedelta(days=1) in have:
            continue
        n = 0
        d = d0
        while d in have:
            n += 1
            d += timedelta(days=1)
        best = max(best, n)
    return cur, best


async def history(session: AsyncSession, user_id: int, limit: int = 400) -> list[str]:
    rows = (
        await session.execute(
            select(DailySpeaking.day)
            .where(DailySpeaking.user_id == user_id)
            .order_by(DailySpeaking.day.desc())
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def today_row(session: AsyncSession, user_id: int, day: date | None = None) -> DailySpeaking | None:
    day = day or _today()
    return (
        await session.execute(
            select(DailySpeaking).where(
                DailySpeaking.user_id == user_id, DailySpeaking.day == day.isoformat()
            )
        )
    ).scalar_one_or_none()


async def status(session: AsyncSession, user_id: int) -> dict:
    """Bosh sahifa kartasi uchun: bajarildimi, streak."""
    from sqlalchemy import func

    today = _today()
    days = await history(session, user_id)
    cur, best = streak_of(days, today)
    total = (
        await session.execute(
            select(func.count()).select_from(DailySpeaking).where(DailySpeaking.user_id == user_id)
        )
    ).scalar_one()
    return {"done": today.isoformat() in days, "streak": cur, "best": best, "total": total}
