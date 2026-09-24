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


# Yangi foydalanuvchining bo'sh metrikasi — _metrics() qaytaradigan barcha kalitlar
EMPTY_METRICS = {
    "lessons": 0, "words": 0, "perfect_lessons": 0, "total_xp": 0,
    "reviews": 0, "streak": 0, "alphabet_done": False,
    "module_done": {}, "level_done": {}, "roots_seen": 0,
    "exams_passed": 0, "best_exam": 0, "best_weekly_rank": 0,
    "league_rank_idx": 0,
    # K17–K20 bo'limlari
    "chat_sessions": 0, "chat_turns": 0, "voice_turns": 0, "daily_best_streak": 0, "daily_total": 0,
    "mocks": 0, "mock_best": 0, "drills": 0, "drill_best": 0, "listens": 0, "listen_best": 0,
    "writings": 0, "writing_best": 0, "writing_neat": 0, "referrals": 0, "best_monthly_rank": 0,
    # K25 Oktagon
    "battles": 0, "battle_wins": 0, "battle_points": 0, "battle_best_correct": 0, "friend_battles": 0,
}


def test_checks_survive_empty_metrics():
    """Yangi foydalanuvchining bo'sh metrikasida hech bir check yiqilmasin."""
    empty = EMPTY_METRICS
    for b in BADGES:
        assert b["check"](empty) in (True, False, None)


def test_no_badge_awarded_to_empty_metrics():
    empty = EMPTY_METRICS
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


@pytest.mark.asyncio
async def test_new_section_badges(session, make_user):
    """Speaking/yozuv nishonlari haqiqiy jadvallardan: mock 70+, yozuv, tinglash, do'st."""
    from db.models import DrillResult, ListeningResult, MockResult, TutorTurn, WritingResult
    from services.achievements import _metrics, check_and_award

    u = await make_user("Nodir")
    m = await _metrics(session, u.id, 0)
    assert set(EMPTY_METRICS) <= set(m), "test EMPTY_METRICS bilan _metrics kalitlari mos"
    assert all(m[k] in (0, False, {}) for k in ("chat_sessions", "mocks", "writings", "referrals"))

    for i in range(3):
        session.add(TutorTurn(user_id=u.id, session_key="s1", mode="chat", voice=1))
    session.add(MockResult(user_id=u.id, mock_id="shifokor", score=74, session_key="m1"))
    session.add(DrillResult(user_id=u.id, topic="oila", score=92, count=10))
    session.add(ListeningResult(user_id=u.id, topic="oila", kind="choice", score=60, count=10))
    session.add(WritingResult(user_id=u.id, period="2026-09-19", text_id="a1-t01", score=91, neatness=5, attempts=1))
    friend = await make_user("Friend", invited_by=u.id, ref_rewarded=1)
    await session.flush()
    got = {b["id"] for b in await check_and_award(session, u.id, 0)}
    assert {"speak_first", "mock_first", "mock_70", "drill_90", "writing_first", "writing_90", "writing_neat", "referral_1"} <= got
    assert "mock_90" not in got and "listen_90" not in got and "speak_50" not in got and "listen_10" not in got
    assert friend.invited_by == u.id
    # Takror chaqiruv — yangi nishon yo'q
    assert await check_and_award(session, u.id, 0) == []
