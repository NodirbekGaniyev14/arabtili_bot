"""Imtihon darajalari: past darajalar ochiq, yuqorilari yopiq."""

import pytest

from api.exam import _level_exam_state
from db.models import ExamAttempt, Progress
from services import exam as ex


async def _state(session, user_id, level, user_level):
    return await _level_exam_state(session, user_id, level, user_level)


# ── Past darajalar ochiq ──


async def test_levels_below_current_are_open(session, make_user):
    """A2 darajasidagi odam A0 va A1 imtihonlarini topshira oladi."""
    user = await make_user()
    for lvl in ("A0", "A1"):
        st = await _state(session, user.id, lvl, "A2")
        assert st["unlocked"] is True, f"{lvl} ochiq bo'lishi kerak"
        assert st["locked_reason"] == ""


async def test_below_open_without_any_lessons(session, make_user):
    """Past daraja darslari tugatilmagan bo'lsa ham ochiq — bosqichdan o'tib kelgan."""
    user = await make_user()
    st = await _state(session, user.id, "A0", "B1")
    assert st["lessons_done"] == 0
    assert st["unlocked"] is True


# ── Yuqori darajalar yopiq ──


@pytest.mark.parametrize("level", ["A1", "A2", "B1"])
async def test_levels_above_current_are_locked(session, make_user, level):
    user = await make_user()
    st = await _state(session, user.id, level, "A0")
    assert st["unlocked"] is False
    assert st["locked_reason"] == "above"


async def test_above_stays_locked_even_with_all_lessons_done(session, make_user):
    """A1 darslarini tugatgan A0-chi baribir A1 imtihoniga kira olmaydi."""
    user = await make_user()
    for lid in ex.level_lesson_ids("A1"):
        session.add(Progress(user_id=user.id, lesson_id=lid))
    await session.commit()

    st = await _state(session, user.id, "A1", "A0")
    assert st["unlocked"] is False
    assert st["locked_reason"] == "above"


# ── Joriy daraja — 80% qoidasi ──


async def test_current_level_locked_without_lessons(session, make_user):
    user = await make_user()
    st = await _state(session, user.id, "A0", "A0")
    assert st["unlocked"] is False
    assert st["locked_reason"] == "lessons"


async def test_current_level_opens_at_threshold(session, make_user):
    user = await make_user()
    ids = sorted(ex.level_lesson_ids("A0"))
    need = ex.unlock_threshold(len(ids))
    for lid in ids[:need]:
        session.add(Progress(user_id=user.id, lesson_id=lid))
    await session.commit()

    st = await _state(session, user.id, "A0", "A0")
    assert st["unlocked"] is True


async def test_passed_exam_reopens_current_level(session, make_user):
    """Bir marta o'tgan bo'lsa — darslar yetmasa ham qayta topshira oladi."""
    user = await make_user()
    session.add(ExamAttempt(user_id=user.id, level="A0", passed=1))
    await session.commit()

    st = await _state(session, user.id, "A0", "A0")
    assert st["unlocked"] is True
    assert st["already_passed"] is True


# ── Foiz va sxema ──


async def test_percent_reflects_progress(session, make_user):
    user = await make_user()
    ids = sorted(ex.level_lesson_ids("A0"))
    half = len(ids) // 2
    for lid in ids[:half]:
        session.add(Progress(user_id=user.id, lesson_id=lid))
    await session.commit()

    st = await _state(session, user.id, "A0", "A0")
    assert st["percent"] == round(half / len(ids) * 100)


async def test_state_has_all_fields(session, make_user):
    user = await make_user()
    st = await _state(session, user.id, "A0", "A0")
    for key in (
        "level", "available", "already_passed", "cooldown_until", "minutes",
        "counts", "unlocked", "locked_reason", "lessons_done", "lessons_total",
        "lessons_needed", "percent",
    ):
        assert key in st


async def test_all_four_levels_have_pools(session, make_user):
    user = await make_user()
    for lvl in ex.LEVEL_ORDER:
        st = await _state(session, user.id, lvl, "B1")
        assert st["available"] is True, f"{lvl} uchun imtihon pooli yo'q"
        assert st["minutes"] > 0
