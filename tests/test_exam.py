"""Imtihon: baholash, o'tish chegarasi, vaqt tugashi, daraja qulfi va o'sishi."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from db.models import ExamAttempt, Plan, Progress
from services import exam as ex


def _attempt(minutes: int = 30, started_ago_min: int = 5) -> ExamAttempt:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return ExamAttempt(
        user_id=1,
        level="A0",
        started_at=now - timedelta(minutes=started_ago_min),
        questions_json=json.dumps(
            {
                "minutes": minutes,
                "reading": [{}] * 8,
                "listening": [{}] * 8,
                "writing": [{}] * 2,
                "speaking": [{}] * 3,
            }
        ),
    )


def _passage_attempt(n_passages: int = 2, per: int = 3) -> ExamAttempt:
    """A2+ imtihoni: gapirish o'rnida matn bo'limi."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return ExamAttempt(
        user_id=1,
        level="A2",
        started_at=now - timedelta(minutes=5),
        questions_json=json.dumps(
            {
                "minutes": 40,
                "reading": [{}] * 10,
                "listening": [{}] * 8,
                "writing": [{}] * 2,
                "speaking": [],
                "passages": [
                    {"id": f"p{i}", "questions": [{}] * per}
                    for i in range(n_passages)
                ],
            }
        ),
    )


# ── Baholash ──


def test_perfect_score_passes():
    r = ex.grade(_attempt(), 8, 8, 100, 100)
    assert r["total"] == 100
    assert r["passed"] is True
    assert r["timed_out"] is False


def test_exactly_80_passes():
    """80 — o'tish chegarasi, qat'iy kichik emas."""
    r = ex.grade(_attempt(), 8, 8, 60, 60)  # (100+100+60+60)/4 = 80
    assert r["total"] == 80
    assert r["passed"] is True


def test_79_fails():
    r = ex.grade(_attempt(), 8, 8, 60, 56)  # (100+100+60+56)/4 = 79
    assert r["total"] == 79
    assert r["passed"] is False


def test_weak_section_still_passes_if_total_high():
    """Bo'lim minimumi olib tashlangan — faqat umumiy ball hal qiladi."""
    r = ex.grade(_attempt(), 8, 8, 100, 20)  # (100+100+100+20)/4 = 80
    assert r["speaking"] == 20
    assert r["passed"] is True


def test_timeout_fails_even_with_perfect_score():
    r = ex.grade(_attempt(minutes=30, started_ago_min=40), 8, 8, 100, 100)
    assert r["total"] == 100
    assert r["timed_out"] is True
    assert r["passed"] is False


def test_grace_period_allows_slight_overrun():
    """30 daq + 3 daq imkoniyat = 33; 32-daqiqa hali o'tadi."""
    r = ex.grade(_attempt(minutes=30, started_ago_min=32), 8, 8, 100, 100)
    assert r["timed_out"] is False
    assert r["passed"] is True


def test_correct_answers_clamped_to_question_count():
    """Mijoz 999 ta to'g'ri deb yuborsa ham 100% dan oshmaydi."""
    r = ex.grade(_attempt(), 999, 999, 100, 100)
    assert r["reading"] == 100
    assert r["listening"] == 100


def test_negative_and_oversized_manual_scores_clamped():
    r = ex.grade(_attempt(), 0, 0, -50, 500)
    assert r["writing"] == 0
    assert r["speaking"] == 100


# ── Matn bo'limi (A2+) ──


def test_fourth_section_is_speaking_by_default():
    assert ex.grade(_attempt(), 8, 8, 100, 100)["fourth"] == "speaking"


def test_fourth_section_is_passage_when_passages_present():
    r = ex.grade(_passage_attempt(), 10, 8, 100, 0, passage_correct=6)
    assert r["fourth"] == "passage"
    assert r["speaking"] == 100  # 6/6 to'g'ri
    assert r["total"] == 100


def test_passage_score_is_ratio_of_all_questions():
    r = ex.grade(_passage_attempt(n_passages=2, per=3), 10, 8, 100, 0, 3)
    assert r["speaking"] == 50  # 3/6


def test_speaking_score_ignored_when_passages_present():
    """Mijoz speaking_score=100 yuborsa ham matn bali hisoblanadi."""
    r = ex.grade(_passage_attempt(), 10, 8, 100, 100, passage_correct=0)
    assert r["speaking"] == 0


def test_passage_correct_clamped():
    r = ex.grade(_passage_attempt(), 10, 8, 100, 0, passage_correct=999)
    assert r["speaking"] == 100
    r = ex.grade(_passage_attempt(), 10, 8, 100, 0, passage_correct=-5)
    assert r["speaking"] == 0


def test_build_exam_a2_has_passages_and_no_speaking():
    exam = ex.build_exam("A2")
    assert exam["speaking"] == []
    assert len(exam["passages"]) == 2
    assert ex.passage_questions(exam) == 6


def test_build_exam_b1_has_three_passages():
    exam = ex.build_exam("B1")
    assert exam["speaking"] == []
    assert len(exam["passages"]) == 3


@pytest.mark.parametrize("level", ["A0", "A1"])
def test_build_exam_low_levels_keep_speaking(level):
    exam = ex.build_exam(level)
    assert exam["passages"] == []
    assert len(exam["speaking"]) > 0


# ── Daraja zanjiri ──


@pytest.mark.parametrize(
    "level,expected",
    [("A0", "A1"), ("A1", "A2"), ("A2", "B1"), ("B1", None), ("XX", None)],
)
def test_next_level(level, expected):
    assert ex.next_level(level) == expected


@pytest.mark.parametrize(
    "total,needed",
    [(0, 0), (1, 1), (10, 8), (24, 20), (39, 32), (44, 36), (49, 40)],
)
def test_unlock_threshold_is_80_percent_rounded_up(total, needed):
    assert ex.unlock_threshold(total) == needed


# ── Qulf ──


async def test_level_progress_counts_only_that_level(session, make_user):
    user = await make_user()
    for lid in ("a0-01", "a0-02", "a1-01"):
        session.add(Progress(user_id=user.id, lesson_id=lid))
    await session.commit()

    done_a0, total_a0 = await ex.level_progress(session, user.id, "A0")
    done_a1, _ = await ex.level_progress(session, user.id, "A1")
    assert done_a0 == 2
    assert done_a1 == 1
    # Jami — kontentdan olinadi (qattiq raqam yozilmaydi: kurs o'sib boradi)
    assert total_a0 == len(ex.level_lesson_ids("A0")) > 0


async def test_duplicate_progress_rows_counted_once(session, make_user):
    """Bir dars ikki marta tugatilsa ham qulf uchun 1 hisoblanadi."""
    user = await make_user()
    session.add(Progress(user_id=user.id, lesson_id="a0-01"))
    session.add(Progress(user_id=user.id, lesson_id="a0-01"))
    await session.commit()

    done, _ = await ex.level_progress(session, user.id, "A0")
    assert done == 1


# ── backfill_levels ──


async def test_backfill_promotes_past_exam_passer(session, make_user):
    user = await make_user()
    session.add(Plan(user_id=user.id, level="A0", target_level="A2", target_date=""))
    session.add(ExamAttempt(user_id=user.id, level="A0", passed=1))
    await session.commit()

    assert await ex.backfill_levels(session) == 1
    plan = (await session.execute(__import__("sqlalchemy").select(Plan))).scalar_one()
    assert plan.level == "A1"


async def test_backfill_is_idempotent(session, make_user):
    user = await make_user()
    session.add(Plan(user_id=user.id, level="A0", target_level="A2", target_date=""))
    session.add(ExamAttempt(user_id=user.id, level="A0", passed=1))
    await session.commit()

    await ex.backfill_levels(session)
    assert await ex.backfill_levels(session) == 0


async def test_backfill_follows_chain_of_passes(session, make_user):
    """A0 va A1 dan o'tgan bo'lsa — to'g'ridan-to'g'ri A2 ga."""
    user = await make_user()
    session.add(Plan(user_id=user.id, level="A0", target_level="B1", target_date=""))
    session.add(ExamAttempt(user_id=user.id, level="A0", passed=1))
    session.add(ExamAttempt(user_id=user.id, level="A1", passed=1))
    await session.commit()

    await ex.backfill_levels(session)
    plan = (await session.execute(__import__("sqlalchemy").select(Plan))).scalar_one()
    assert plan.level == "A2"


async def test_backfill_ignores_failed_attempts(session, make_user):
    user = await make_user()
    session.add(Plan(user_id=user.id, level="A0", target_level="A2", target_date=""))
    session.add(ExamAttempt(user_id=user.id, level="A0", passed=0))
    await session.commit()

    assert await ex.backfill_levels(session) == 0
