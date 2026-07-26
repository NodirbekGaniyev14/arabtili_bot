"""SRS (interval takrorlash) — soddalashtirilgan SM-2 algoritmi.

Baholar: again (bilmadim) · hard (qiyin) · good (bildim) · easy (oson).
Yangi karta shu kuniyoq takrorga tushadi; keyin intervallar o'sib boradi.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import UserWord
from services.content import lesson_index
from services.stats import _today, completed_lesson_ids

GRADES = ("again", "hard", "good", "easy")

MAX_INTERVAL = 365
MIN_EASE = 1.3
MAX_EASE = 3.0


async def seed_user_words(session: AsyncSession, user_id: int) -> None:
    """Tugatilgan darslardagi barcha yangi elementlarni kartotekaga qo'shadi
    (mavjudlariga tegmaydi) — idempotent."""
    done = await completed_lesson_ids(session, user_id)
    if not done:
        return

    existing = set(
        (
            await session.execute(
                select(UserWord.ar).where(UserWord.user_id == user_id)
            )
        ).scalars()
    )

    idx = lesson_index()
    today = _today().isoformat()
    added = False
    for lid in done:
        info = idx.get(lid)
        if not info:
            continue
        for item in info["lesson"].get("new_items", []):
            if item["ar"] in existing:
                continue
            existing.add(item["ar"])
            session.add(
                UserWord(
                    user_id=user_id,
                    ar=item["ar"],
                    translit=item.get("translit", ""),
                    uz=item.get("uz", ""),
                    audio=item.get("audio", ""),
                    kind=item.get("kind", "word"),
                    due_date=today,
                )
            )
            added = True

    if added:
        await session.commit()


async def seed_from_srs_cards(
    session: AsyncSession, user_id: int, cards: list[dict]
) -> int:
    """v2 dars srs_cards ro'yxatidan kartoteka to'ldiradi. Qo'shilganlar sonini qaytaradi."""
    if not cards:
        return 0
    existing = set(
        (
            await session.execute(
                select(UserWord.ar).where(UserWord.user_id == user_id)
            )
        ).scalars()
    )
    today = _today().isoformat()
    added = 0
    for c in cards:
        front = c.get("front", "").strip()
        if not front or front in existing:
            continue
        existing.add(front)
        session.add(
            UserWord(
                user_id=user_id,
                ar=front,
                uz=c.get("back", ""),
                kind=c.get("type", "word"),
                card_type=c.get("type", "word"),
                deck=c.get("deck", "msa"),
                due_date=today,
            )
        )
        added += 1
    if added:
        await session.commit()
    return added


async def reset_words(
    session: AsyncSession, user_id: int, ar_list: list[str]
) -> int:
    """Xato javob berilgan so'zlarning SRS intervalini qayta boshlaydi (spec §11)."""
    if not ar_list:
        return 0
    rows = (
        (
            await session.execute(
                select(UserWord).where(
                    UserWord.user_id == user_id, UserWord.ar.in_(ar_list)
                )
            )
        )
        .scalars()
        .all()
    )
    today = _today().isoformat()
    for w in rows:
        w.reps = 0
        w.lapses += 1
        w.interval_days = 0
        w.due_date = today
        w.ease = max(MIN_EASE, w.ease - 0.2)
        session.add(w)
    if rows:
        await session.commit()
    return len(rows)


def apply_grade(word: UserWord, grade: str) -> None:
    """Kartani bahoga qarab keyingi sanaga suradi (SM-2 soddalashtirilgan)."""
    # Hali flush qilinmagan kartada ustun standartlari qo'llanmagan bo'ladi
    word.reps = word.reps or 0
    word.lapses = word.lapses or 0
    word.interval_days = word.interval_days or 0
    word.ease = word.ease or 2.5

    if grade == "again":
        word.reps = 0
        word.lapses += 1
        word.interval_days = 0
        word.ease = max(MIN_EASE, word.ease - 0.2)
    elif grade == "hard":
        word.interval_days = (
            max(1, int(word.interval_days * 1.2 + 0.5)) if word.reps else 1
        )
        word.ease = max(MIN_EASE, word.ease - 0.15)
        word.reps += 1
    elif grade == "good":
        word.interval_days = (
            int(word.interval_days * word.ease + 0.5) if word.reps else 1
        )
        word.reps += 1
    else:  # easy
        word.interval_days = (
            int(word.interval_days * word.ease * 1.3 + 0.5) if word.reps else 3
        )
        word.ease = min(MAX_EASE, word.ease + 0.15)
        word.reps += 1

    word.interval_days = min(word.interval_days, MAX_INTERVAL)
    word.due_date = (_today() + timedelta(days=word.interval_days)).isoformat()
