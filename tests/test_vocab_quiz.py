"""Lug'at imtihoni — daraja kesimidagi test (K16.6)."""

import pytest

from services import vocab as vc
from services import vocab_test as vt


# ── Savol yig'ish ──


def test_quiz_has_requested_size():
    quiz = vt.build_quiz(level="A2", n=20, seed=1)
    assert len(quiz["items"]) == 20
    assert quiz["pass_score"] == vt.PASS_SCORE


def test_quiz_respects_level():
    quiz = vt.build_quiz(level="A1", n=15, seed=2)
    assert all(q["level"] == "A1" for q in quiz["items"])


def test_quiz_respects_theme():
    quiz = vt.build_quiz(level="A2", theme="ovqat", n=10, seed=3)
    assert quiz["items"], "ovqat mavzusida so'z bo'lishi kerak"
    assert all(q["theme"] == "ovqat" for q in quiz["items"])


def test_every_question_is_answerable():
    quiz = vt.build_quiz(level="A0", n=20, seed=4)
    for q in quiz["items"]:
        assert q["answer"] in q["options"], q["word_id"]
        assert len(q["options"]) == vt.OPTIONS
        assert len(set(q["options"])) == vt.OPTIONS, f"variant takrori: {q['options']}"
        assert q["prompt"]


def test_all_three_question_types_appear():
    quiz = vt.build_quiz(level="A2", n=12, seed=5)
    kinds = {q["type"] for q in quiz["items"]}
    assert kinds == {"ar_uz", "uz_ar", "audio_uz"}


def test_audio_questions_have_audio():
    quiz = vt.build_quiz(level="A2", n=30, seed=6)
    for q in quiz["items"]:
        if q["type"] == "audio_uz":
            assert q["audio"].startswith("vocab/") or q["audio"]


def test_seed_makes_quiz_reproducible():
    a = vt.build_quiz(level="B1", n=10, seed=7)
    b = vt.build_quiz(level="B1", n=10, seed=7)
    assert [q["word_id"] for q in a["items"]] == [q["word_id"] for q in b["items"]]


def test_different_seeds_give_different_questions():
    a = vt.build_quiz(level="A2", n=20, seed=8)
    b = vt.build_quiz(level="A2", n=20, seed=9)
    assert [q["word_id"] for q in a["items"]] != [q["word_id"] for q in b["items"]]


def test_empty_level_falls_back_to_all_words():
    quiz = vt.build_quiz(n=10, seed=10)
    assert len(quiz["items"]) == 10


def test_count_is_clamped():
    assert len(vt.build_quiz(level="A2", n=999, seed=11)["items"]) <= vt.MAX_COUNT
    assert len(vt.build_quiz(level="A2", n=1, seed=12)["items"]) >= 5


def test_levels_ready_matches_written_content():
    ready = vt.levels_ready()
    counts = vc.level_counts()
    assert ready == [lv for lv in vc.LEVELS if counts[lv] >= vt.OPTIONS]


# ── Baholash ──


@pytest.mark.parametrize(
    "correct,total,expected,passed",
    [(20, 20, 100, True), (14, 20, 70, True), (13, 20, 65, False), (0, 20, 0, False)],
)
def test_score(correct, total, expected, passed):
    res = vt.score(correct, total)
    assert res["score"] == expected
    assert res["passed"] is passed


def test_score_handles_zero_total():
    assert vt.score(0, 0)["score"] == 0


# ── API ──


@pytest.mark.asyncio
async def test_submit_awards_xp_and_seeds_review(session, make_user):
    from sqlalchemy import select

    from api.routes import QuizResultBody, vocab_quiz_submit
    from db.models import UserWord, XpLog

    user = await make_user()
    wrong = [w["ar"] for w in vc.all_words()[:3]]
    res = await vocab_quiz_submit(
        QuizResultBody(level="A2", correct=15, total=20, wrong_words=wrong),
        user,
        session,
    )

    assert res["score"] == 75
    assert res["passed"] is True
    assert res["added_to_review"] == 3
    assert res["xp_earned"] == 25  # 15 to'g'ri + 10 o'tgani uchun

    words = (
        await session.execute(select(UserWord).where(UserWord.user_id == user.id))
    ).scalars().all()
    assert {w.ar for w in words} == set(wrong)

    logs = (
        await session.execute(select(XpLog).where(XpLog.user_id == user.id))
    ).scalars().all()
    assert logs[0].source == "vocab_quiz:A2"


@pytest.mark.asyncio
async def test_failed_quiz_gets_no_bonus(session, make_user):
    from api.routes import QuizResultBody, vocab_quiz_submit

    user = await make_user()
    res = await vocab_quiz_submit(
        QuizResultBody(level="A0", correct=5, total=20, wrong_words=[]),
        user,
        session,
    )
    assert res["passed"] is False
    assert res["xp_earned"] == 5


@pytest.mark.asyncio
async def test_quiz_endpoint_shape(session, make_user):
    from api.routes import vocab_quiz

    user = await make_user()
    quiz = await vocab_quiz("a2", "", 10, user)
    assert quiz["level"] == "A2"
    assert len(quiz["items"]) == 10
