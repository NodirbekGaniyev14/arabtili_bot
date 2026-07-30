"""60% qoidasi va qayta topshirishda savollarning almashishi (K14).

Talab: darsdan 60% dan kam olgan o'quvchi keyingi darsga o'tmaydi, va qayta
topshirganda AYNAN o'sha savollar tushmaydi.
"""

import pytest

from db.models import Progress
from services.course import course_all_levels
from services.lesson_test import PASS_SCORE, build_test, generated_bank
from services.qbank import qhash
from services.stats import completed_lesson_ids, lesson_attempt_count


# ── Qulf: faqat o'tilgan dars keyingisini ochadi ──


@pytest.mark.asyncio
async def test_failed_attempt_is_not_completed(session, make_user):
    user = await make_user()
    session.add(
        Progress(user_id=user.id, lesson_id="a0-01", correct=2, total=7, passed=0)
    )
    await session.commit()

    assert await completed_lesson_ids(session, user.id) == set()


@pytest.mark.asyncio
async def test_passed_attempt_is_completed(session, make_user):
    user = await make_user()
    session.add(
        Progress(user_id=user.id, lesson_id="a0-01", correct=6, total=7, passed=1)
    )
    await session.commit()

    assert await completed_lesson_ids(session, user.id) == {"a0-01"}


@pytest.mark.asyncio
async def test_attempts_are_counted_including_failures(session, make_user):
    user = await make_user()
    for passed in (0, 0, 1):
        session.add(
            Progress(
                user_id=user.id, lesson_id="a0-01", correct=4, total=7, passed=passed
            )
        )
    await session.commit()

    assert await lesson_attempt_count(session, user.id, "a0-01") == 3
    assert await lesson_attempt_count(session, user.id, "a0-02") == 0


def test_next_lesson_stays_locked_without_pass():
    """Yiqilgan dars `done` to'plamiga tushmaydi — keyingisi qulfda qoladi."""
    data = course_all_levels(set(), current_level="A0")
    lessons = data["levels"][0]["modules"][0]["lessons"]
    assert lessons[1]["unlocked"] is False


def test_pass_score_is_60():
    assert PASS_SCORE == 60


# ── Qayta topshirish: boshqa savollar ──


def test_first_attempt_uses_authored_questions():
    test = build_test("a0-22", 0)
    assert test["attempt"] == 0
    assert len(test["items"]) >= 5


def test_retry_questions_differ_from_first_attempt():
    first = {qhash(i) for i in build_test("a0-22", 0)["items"]}
    second = {qhash(i) for i in build_test("a0-22", 1)["items"]}
    assert first, "birinchi urinishda savol bo'lishi kerak"
    assert second
    assert not (first & second), "qayta topshirishda o'sha savollar tushmasligi kerak"


def test_third_attempt_also_differs_from_second():
    second = {qhash(i) for i in build_test("a0-22", 1)["items"]}
    third = {qhash(i) for i in build_test("a0-22", 2)["items"]}
    assert not (second & third)


@pytest.mark.parametrize("lesson_id", ["a0-05", "a0-22", "a1-10", "a2-20", "b1-15"])
def test_every_level_has_enough_questions_for_two_attempts(lesson_id):
    """Bank kamida 2 xil urinishga yetishi kerak (aks holda savollar takrorlanadi)."""
    first = {qhash(i) for i in build_test(lesson_id, 0)["items"]}
    second = {qhash(i) for i in build_test(lesson_id, 1)["items"]}
    assert len(first) >= 5
    assert not (first & second), lesson_id


def test_build_test_is_deterministic():
    a = [qhash(i) for i in build_test("a1-10", 2)["items"]]
    b = [qhash(i) for i in build_test("a1-10", 2)["items"]]
    assert a == b


@pytest.mark.parametrize("lesson_id", ["a0-22", "a1-10", "a2-20", "b1-15"])
def test_generated_questions_are_answerable(lesson_id):
    """Yasalgan savollarda javob variantlar ichida va variantlar noyob."""
    for item in generated_bank(lesson_id):
        opts = item["options"]
        assert len(opts) >= 3, item
        assert len(set(opts)) == len(opts), item
        assert item["answer"] in opts, item


@pytest.mark.parametrize("attempt", [0, 1, 2, 3])
def test_test_items_are_always_answerable(attempt):
    for item in build_test("a2-20", attempt)["items"]:
        if item.get("options"):
            assert item["answer"] in item["options"], item
            assert len(set(item["options"])) == len(item["options"]), item
