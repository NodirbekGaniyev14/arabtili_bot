"""Yutuqlar — sxema yaxlitligi va berish mantiqi."""

import pytest

from db.models import Progress, XpLog
from services.achievements import BADGES, _metrics, check_and_award, list_achievements


def test_at_least_thirty_badges():
    assert len(BADGES) >= 30


def test_badge_ids_unique():
    ids = [b["id"] for b in BADGES]
    assert len(ids) == len(set(ids))


def test_every_badge_has_required_fields():
    for b in BADGES:
        assert b["id"] and b["icon"] and b["title"] and b["desc"]
        assert callable(b["check"])


def test_checks_survive_empty_metrics():
    """Yangi foydalanuvchining bo'sh metrikasida hech bir check yiqilmasin."""
    empty = {
        "lessons": 0, "words": 0, "perfect_lessons": 0, "total_xp": 0,
        "reviews": 0, "streak": 0, "alphabet_done": False,
        "module_done": {}, "level_done": {}, "roots_seen": 0,
        "exams_passed": 0, "best_exam": 0, "best_weekly_rank": 0,
        "league_rank_idx": 0,
    }
    for b in BADGES:
        assert b["check"](empty) in (True, False, None)


def test_no_badge_awarded_to_empty_metrics():
    empty = {
        "lessons": 0, "words": 0, "perfect_lessons": 0, "total_xp": 0,
        "reviews": 0, "streak": 0, "alphabet_done": False,
        "module_done": {}, "level_done": {}, "roots_seen": 0,
        "exams_passed": 0, "best_exam": 0, "best_weekly_rank": 0,
        "league_rank_idx": 0,
    }
    assert [b["id"] for b in BADGES if b["check"](empty)] == []


# ── Jonli tekshiruv ──


async def test_first_lesson_awards_first_step(session, make_user):
    user = await make_user()
    session.add(Progress(user_id=user.id, lesson_id="a0-01", correct=5, total=5))
    await session.commit()

    new = await check_and_award(session, user.id, streak=1)
    assert "first_step" in [b["id"] for b in new]
    assert "perfect_lesson" in [b["id"] for b in new]


async def test_badges_not_awarded_twice(session, make_user):
    user = await make_user()
    session.add(Progress(user_id=user.id, lesson_id="a0-01", correct=5, total=5))
    await session.commit()

    await check_and_award(session, user.id, streak=1)
    second = await check_and_award(session, user.id, streak=1)
    assert second == []


async def test_streak_badges_scale(session, make_user):
    user = await make_user()
    session.add(Progress(user_id=user.id, lesson_id="a0-01"))
    await session.commit()

    ids = [b["id"] for b in await check_and_award(session, user.id, streak=14)]
    assert "streak_3" in ids and "streak_7" in ids and "streak_14" in ids
    assert "streak_30" not in ids


async def test_xp_badges(session, make_user):
    user = await make_user()
    session.add(XpLog(user_id=user.id, amount=1200, source="t"))
    await session.commit()

    ids = [b["id"] for b in await check_and_award(session, user.id, streak=0)]
    assert "xp_500" in ids and "xp_1000" in ids
    assert "xp_5000" not in ids


async def test_list_reports_locked_and_unlocked(session, make_user):
    user = await make_user()
    session.add(Progress(user_id=user.id, lesson_id="a0-01"))
    await session.commit()
    await check_and_award(session, user.id, streak=1)

    data = await list_achievements(session, user.id)
    assert data["total"] == len(BADGES)
    assert 0 < data["earned_count"] < data["total"]
    assert any(b["earned"] for b in data["badges"])
    assert any(not b["earned"] for b in data["badges"])


async def test_metrics_shape(session, make_user):
    user = await make_user()
    m = await _metrics(session, user.id, streak=0)
    for key in (
        "lessons", "words", "module_done", "level_done", "roots_seen",
        "exams_passed", "best_exam", "best_weekly_rank", "league_rank_idx",
    ):
        assert key in m
