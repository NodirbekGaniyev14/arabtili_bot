"""Yutuqlar (badge) tizimi — aniqlash, tekshirish va berish."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Achievement, Progress, UserWord, XpLog

# Har bir badge: id, emoji, nom, tavsif, tekshirish sharti (metrics dict asosida)
BADGES: list[dict] = [
    {"id": "first_step", "icon": "👣", "title": "Birinchi qadam", "desc": "Birinchi darsni tugatdingiz", "check": lambda m: m["lessons"] >= 1},
    {"id": "lessons_5", "icon": "📚", "title": "G'ayratli", "desc": "5 ta dars tugatildi", "check": lambda m: m["lessons"] >= 5},
    {"id": "lessons_10", "icon": "🎓", "title": "Bilimdon", "desc": "10 ta dars tugatildi", "check": lambda m: m["lessons"] >= 10},
    {"id": "alphabet_master", "icon": "🔤", "title": "Alifbo ustasi", "desc": "Butun alifbo modulini tugatdingiz", "check": lambda m: m["alphabet_done"]},
    {"id": "perfect_lesson", "icon": "⭐", "title": "Benuqson", "desc": "Darsni xatosiz tugatdingiz", "check": lambda m: m["perfect_lessons"] >= 1},
    {"id": "perfect_5", "icon": "🌟", "title": "Mukammallik", "desc": "5 ta darsni xatosiz tugatdingiz", "check": lambda m: m["perfect_lessons"] >= 5},
    {"id": "words_25", "icon": "📖", "title": "So'z boyligi", "desc": "25 ta so'z o'rgandingiz", "check": lambda m: m["words"] >= 25},
    {"id": "words_50", "icon": "🧠", "title": "Lug'at", "desc": "50 ta so'z o'rgandingiz", "check": lambda m: m["words"] >= 50},
    {"id": "streak_3", "icon": "🔥", "title": "Odat boshlandi", "desc": "3 kun ketma-ket", "check": lambda m: m["streak"] >= 3},
    {"id": "streak_7", "icon": "🔥", "title": "Haftalik olov", "desc": "7 kun ketma-ket", "check": lambda m: m["streak"] >= 7},
    {"id": "streak_30", "icon": "🏆", "title": "Bir oylik sadoqat", "desc": "30 kun ketma-ket", "check": lambda m: m["streak"] >= 30},
    {"id": "reviewer_50", "icon": "🔁", "title": "Takrorchi", "desc": "50 marta takror qildingiz", "check": lambda m: m["reviews"] >= 50},
    {"id": "xp_500", "icon": "💎", "title": "500 XP", "desc": "Jami 500 XP to'pladingiz", "check": lambda m: m["total_xp"] >= 500},
    {"id": "xp_1000", "icon": "👑", "title": "1000 XP", "desc": "Jami 1000 XP to'pladingiz", "check": lambda m: m["total_xp"] >= 1000},
]

BADGE_BY_ID = {b["id"]: b for b in BADGES}


def _public(badge: dict) -> dict:
    return {k: badge[k] for k in ("id", "icon", "title", "desc")}


async def _metrics(session: AsyncSession, user_id: int, streak: int) -> dict:
    from services.course import count_vocab
    from services.curriculum import load_curriculum

    done = set(
        (
            await session.execute(
                select(Progress.lesson_id)
                .where(Progress.user_id == user_id)
                .distinct()
            )
        ).scalars()
    )

    words = sum(count_vocab(lid) for lid in done)

    perfect = (
        await session.execute(
            select(func.count())
            .select_from(Progress)
            .where(
                Progress.user_id == user_id,
                Progress.total > 0,
                Progress.correct == Progress.total,
            )
        )
    ).scalar_one()

    total_xp = (
        await session.execute(
            select(func.coalesce(func.sum(XpLog.amount), 0)).where(
                XpLog.user_id == user_id
            )
        )
    ).scalar_one()

    reviews = (
        await session.execute(
            select(func.count())
            .select_from(XpLog)
            .where(XpLog.user_id == user_id, XpLog.source == "review")
        )
    ).scalar_one()

    # Alifbo ustasi — A0 "letters" moduli (a0-01..a0-09) to'liq tugatilsa
    cur = load_curriculum()
    letters_ids = [
        lid for lid, m in cur.items()
        if m["level"] == "A0" and m["module"] == "letters" and m["type"] == "lesson"
    ]
    alphabet_done = bool(letters_ids) and all(lid in done for lid in letters_ids)

    return {
        "lessons": len(done),
        "words": words,
        "perfect_lessons": perfect,
        "total_xp": total_xp,
        "reviews": reviews,
        "streak": streak,
        "alphabet_done": alphabet_done,
    }


async def check_and_award(
    session: AsyncSession, user_id: int, streak: int
) -> list[dict]:
    """Yangi qo'lga kiritilgan badge'larni beradi va ularni qaytaradi."""
    metrics = await _metrics(session, user_id, streak)

    owned = set(
        (
            await session.execute(
                select(Achievement.badge_id).where(Achievement.user_id == user_id)
            )
        ).scalars()
    )

    newly: list[dict] = []
    for badge in BADGES:
        if badge["id"] in owned:
            continue
        try:
            if badge["check"](metrics):
                session.add(
                    Achievement(user_id=user_id, badge_id=badge["id"])
                )
                newly.append(_public(badge))
        except Exception:
            continue

    if newly:
        await session.commit()
    return newly


async def list_achievements(session: AsyncSession, user_id: int) -> dict:
    """Barcha badge'lar + qo'lga kiritilganlari (profil uchun)."""
    owned = dict(
        (
            await session.execute(
                select(Achievement.badge_id, Achievement.earned_at).where(
                    Achievement.user_id == user_id
                )
            )
        ).all()
    )

    items = [
        {
            **_public(b),
            "earned": b["id"] in owned,
        }
        for b in BADGES
    ]
    return {"earned_count": len(owned), "total": len(BADGES), "badges": items}
