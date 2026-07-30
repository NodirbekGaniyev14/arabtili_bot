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

    # ── Kurs bosqichlari (kontentga bog'langan) ──
    {"id": "lessons_25", "icon": "📗", "title": "Chorak yo'l", "desc": "25 ta dars tugatildi", "check": lambda m: m["lessons"] >= 25},
    {"id": "lessons_50", "icon": "📘", "title": "Yarim yo'l", "desc": "50 ta dars tugatildi", "check": lambda m: m["lessons"] >= 50},
    {"id": "lessons_100", "icon": "📕", "title": "Yuzlik", "desc": "100 ta dars tugatildi", "check": lambda m: m["lessons"] >= 100},
    {"id": "level_a0", "icon": "🅰️", "title": "A0 tugadi", "desc": "Boshlang'ich darajaning barcha darslari", "check": lambda m: m["level_done"].get("A0")},
    {"id": "level_a1", "icon": "🥇", "title": "A1 tugadi", "desc": "Elementar darajaning barcha darslari", "check": lambda m: m["level_done"].get("A1")},
    {"id": "level_a2", "icon": "🏅", "title": "A2 tugadi", "desc": "O'rta-quyi darajaning barcha darslari", "check": lambda m: m["level_done"].get("A2")},
    {"id": "level_b1", "icon": "🎖", "title": "B1 tugadi", "desc": "O'rta darajaning barcha darslari", "check": lambda m: m["level_done"].get("B1")},

    # ── Modul ustalari ──
    {"id": "harakat_master", "icon": "◌َ", "title": "Harakat ustasi", "desc": "Harakatlar modulini tugatdingiz", "check": lambda m: m["module_done"].get("harakat")},
    {"id": "verb_forms_master", "icon": "⚙️", "title": "Bob ustasi", "desc": "Fe'l boblari modulini tugatdingiz", "check": lambda m: m["module_done"].get("verb-forms")},
    {"id": "weak_verbs_master", "icon": "🌀", "title": "Illatli fe'llar", "desc": "Illatli fe'llar modulini tugatdingiz", "check": lambda m: m["module_done"].get("weak-verbs")},
    {"id": "saudi_module", "icon": "🇸🇦", "title": "Saudiyaga tayyor", "desc": "Saudiya modulini tugatdingiz", "check": lambda m: m["module_done"].get("saudi")},
    {"id": "quran_module", "icon": "🕌", "title": "Qur'on tili", "desc": "Qur'on va hadis modulini tugatdingiz", "check": lambda m: m["module_done"].get("quran-hadith")},

    # ── Mahorat ──
    {"id": "perfect_15", "icon": "✨", "title": "Zargar aniqligi", "desc": "15 ta darsni xatosiz tugatdingiz", "check": lambda m: m["perfect_lessons"] >= 15},
    {"id": "words_150", "icon": "📚", "title": "Yuz ellik so'z", "desc": "150 ta so'z o'rgandingiz", "check": lambda m: m["words"] >= 150},
    {"id": "words_400", "icon": "🗃", "title": "Boy lug'at", "desc": "400 ta so'z o'rgandingiz", "check": lambda m: m["words"] >= 400},
    {"id": "words_800", "icon": "🏛", "title": "So'z xazinasi", "desc": "800 ta so'z o'rgandingiz", "check": lambda m: m["words"] >= 800},
    {"id": "roots_25", "icon": "🌱", "title": "O'zak ovchisi", "desc": "25 ta o'zak bilan tanishdingiz", "check": lambda m: m["roots_seen"] >= 25},
    {"id": "roots_75", "icon": "🌳", "title": "O'zaklar bog'i", "desc": "75 ta o'zak bilan tanishdingiz", "check": lambda m: m["roots_seen"] >= 75},

    # ── Odat va sadoqat ──
    {"id": "streak_14", "icon": "🔥", "title": "Ikki hafta", "desc": "14 kun ketma-ket", "check": lambda m: m["streak"] >= 14},
    {"id": "streak_100", "icon": "💯", "title": "Yuz kun", "desc": "100 kun ketma-ket", "check": lambda m: m["streak"] >= 100},
    {"id": "reviewer_200", "icon": "🔂", "title": "Takror ustasi", "desc": "200 marta takror qildingiz", "check": lambda m: m["reviews"] >= 200},
    {"id": "reviewer_500", "icon": "♾", "title": "Unutmas", "desc": "500 marta takror qildingiz", "check": lambda m: m["reviews"] >= 500},
    {"id": "xp_5000", "icon": "🔱", "title": "5000 XP", "desc": "Jami 5000 XP to'pladingiz", "check": lambda m: m["total_xp"] >= 5000},

    # ── Imtihon va sovrinlar ──
    {"id": "first_exam", "icon": "📜", "title": "Birinchi sertifikat", "desc": "Daraja imtihonidan o'tdingiz", "check": lambda m: m["exams_passed"] >= 1},
    {"id": "exams_2", "icon": "🎓", "title": "Ikki daraja", "desc": "Ikki daraja imtihonidan o'tdingiz", "check": lambda m: m["exams_passed"] >= 2},
    {"id": "exam_ace", "icon": "💯", "title": "A'lo imtihon", "desc": "Imtihonda 95+ ball oldingiz", "check": lambda m: m["best_exam"] >= 95},
    {"id": "weekly_winner", "icon": "🥇", "title": "Hafta g'olibi", "desc": "Haftalik reytingda 1-o'rin", "check": lambda m: m["best_weekly_rank"] == 1},
    {"id": "weekly_podium", "icon": "🏆", "title": "Sovrindor", "desc": "Haftalik reytingda top-3 ga kirdingiz", "check": lambda m: 1 <= m["best_weekly_rank"] <= 3},
    {"id": "league_gold", "icon": "🥇", "title": "Oltin liga", "desc": "Bir haftada Oltin ligaga yetdingiz (300+ XP)", "check": lambda m: m["league_rank_idx"] >= 2},
    {"id": "league_emerald", "icon": "💎", "title": "Zumrad liga", "desc": "Bir haftada Zumrad ligaga yetdingiz (600+ XP)", "check": lambda m: m["league_rank_idx"] >= 3},
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
                .where(Progress.user_id == user_id, Progress.passed == 1)
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

    # Modul va daraja tugallanishi — faqat YOZILGAN darslar bo'yicha
    from services.curriculum import written_lesson_ids

    cur = load_curriculum()
    written = written_lesson_ids()

    groups_module: dict[str, list[str]] = {}
    groups_level: dict[str, list[str]] = {}
    for lid, m in cur.items():
        if m["type"] != "lesson" or lid not in written:
            continue
        groups_module.setdefault(m.get("module", ""), []).append(lid)
        groups_level.setdefault(m["level"], []).append(lid)

    module_done = {
        mod: bool(ids) and all(lid in done for lid in ids)
        for mod, ids in groups_module.items()
    }
    level_done = {
        lvl: bool(ids) and all(lid in done for lid in ids)
        for lvl, ids in groups_level.items()
    }
    alphabet_done = module_done.get("letters", False)

    # O'zaklar — ko'rilgan darslardagi noyob o'zaklar
    from services.curriculum import load_lesson_v2

    roots: set[str] = set()
    for lid in done:
        data = load_lesson_v2(lid)
        if not data:
            continue
        roots.update(r["root"] for r in data.get("roots", []) if r.get("root"))
        roots.update(v["root"] for v in data.get("vocabulary", []) if v.get("root"))

    # Imtihonlar
    from db.models import ExamAttempt, User, WeeklyAward

    exam_rows = (
        await session.execute(
            select(ExamAttempt.level, ExamAttempt.total_score).where(
                ExamAttempt.user_id == user_id, ExamAttempt.passed == 1
            )
        )
    ).all()
    exams_passed = len({lvl for lvl, _ in exam_rows})
    best_exam = max((s for _, s in exam_rows), default=0)

    best_weekly_rank = (
        await session.execute(
            select(func.min(WeeklyAward.rank)).where(WeeklyAward.user_id == user_id)
        )
    ).scalar() or 0

    # Liga — hozirgi haftalik XP bo'yicha yorliq (ko'tarilish/tushish yo'q).
    # Badge bir marta berilsa qoladi: odam biror hafta oltin/zumradga yetsa yetarli.
    from services.league import LEAGUE_ORDER, _week_start_utc, league_for

    week_xp = (
        await session.execute(
            select(func.coalesce(func.sum(XpLog.amount), 0)).where(
                XpLog.user_id == user_id, XpLog.created_at >= _week_start_utc()
            )
        )
    ).scalar() or 0
    league_idx = LEAGUE_ORDER.index(league_for(int(week_xp))["id"])

    return {
        "lessons": len(done),
        "words": words,
        "perfect_lessons": perfect,
        "total_xp": total_xp,
        "reviews": reviews,
        "streak": streak,
        "alphabet_done": alphabet_done,
        "module_done": module_done,
        "level_done": level_done,
        "roots_seen": len(roots),
        "exams_passed": exams_passed,
        "best_exam": best_exam,
        "best_weekly_rank": best_weekly_rank,
        "league_rank_idx": league_idx,
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
