"""Harf chizish mashqi (K21.6) — A0: ekranda barmoq bilan harf shaklini chizish.

Harflar `content/modules/alphabet.json` dan (28 ta, nom + audio). Baholash BRAUZERDA
(canvas: namuna harf maskasi va chizilgan chiziqning qamrov/aniqlik nisbati, nuqtalar
alohida tekshiriladi); server natijani saqlaydi va XP beradi: kamida MIN_LETTERS harf,
XP = o'rtacha/10 (maks 10), kuniga bir marta. Eng yaxshi ballar `best()` — sahifada ✓.
"""

import json
from datetime import datetime, timedelta
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import BASE_DIR
from db.models import TraceResult
from services.stats import TASHKENT_OFFSET

ALPHABET_PATH = BASE_DIR / "content" / "modules" / "alphabet.json"
MIN_LETTERS = 5
MAX_XP = 10
PASS = 70


@lru_cache(maxsize=1)
def letters() -> list[dict]:
    data = json.loads(ALPHABET_PATH.read_text(encoding="utf-8"))
    out: list[dict] = []
    seen: set[str] = set()
    for lesson in data.get("lessons", []):
        for it in lesson.get("new_items", []):
            ar = (it.get("ar") or "").strip()
            if it.get("kind") != "letter" or len(ar) != 1 or ar in seen:
                continue
            seen.add(ar)
            out.append({
                "ar": ar,
                "name": it.get("translit", ""),
                "uz": it.get("uz", ""),
                "audio": it.get("audio", ""),
                "audio_text": it.get("audio_text", ""),
            })
    return out


def xp_for(avg: int, count: int) -> int:
    if count < MIN_LETTERS or avg <= 0:
        return 0
    return max(1, min(MAX_XP, round(avg / 10)))


def clean_scores(raw: dict) -> dict[str, int]:
    """{harf: ball} — faqat bankdagi harflar, 0–100."""
    known = {x["ar"] for x in letters()}
    out: dict[str, int] = {}
    for k, v in (raw or {}).items():
        if k in known:
            try:
                out[k] = max(0, min(100, int(v)))
            except (TypeError, ValueError):
                continue
    return out


async def best(session: AsyncSession, user_id: int) -> dict[str, int]:
    rows = (
        await session.execute(select(TraceResult.scores).where(TraceResult.user_id == user_id))
    ).scalars().all()
    out: dict[str, int] = {}
    for raw in rows:
        try:
            for k, v in json.loads(raw or "{}").items():
                out[k] = max(out.get(k, 0), int(v))
        except (ValueError, TypeError):
            continue
    return out


async def xp_taken_today(session: AsyncSession, user_id: int, now: datetime) -> bool:
    day = (now + TASHKENT_OFFSET).date()
    lo = datetime.combine(day, datetime.min.time()) - TASHKENT_OFFSET
    row = (
        await session.execute(
            select(TraceResult.id).where(
                TraceResult.user_id == user_id, TraceResult.xp > 0,
                TraceResult.created_at >= lo, TraceResult.created_at < lo + timedelta(days=1),
            ).limit(1)
        )
    ).scalar_one_or_none()
    return row is not None
