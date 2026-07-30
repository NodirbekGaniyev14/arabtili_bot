"""Imtihonni qayta topshirish — 24 soatdan keyin BOSHQA savollar (K14)."""

import json

import pytest

from db.models import ExamAttempt
from services import checkpoint as cp
from services import exam as ex
from services.qbank import pick_fresh, qhash


def _hashes(exam: dict) -> set[str]:
    out: set[str] = set()
    for sec in ("reading", "listening", "writing", "speaking", "passages"):
        for it in exam.get(sec) or []:
            out.add(qhash(it))
    return out


@pytest.mark.parametrize("level", ["A0", "A1", "A2", "B1"])
def test_pool_has_three_disjoint_variants(level):
    """Bank uch marta to'liq yangi imtihon berishga yetadi."""
    seen: set[str] = set()
    for _ in range(3):
        exam = ex.build_exam(level, seen)
        assert exam is not None
        new = _hashes(exam)
        assert not (new & seen), f"{level}: savollar takrorlandi"
        seen |= new


@pytest.mark.parametrize("level", ["A0", "A1", "A2", "B1"])
def test_second_attempt_is_fully_new(level):
    first = ex.build_exam(level)
    second = ex.build_exam(level, _hashes(first))
    assert not (_hashes(first) & _hashes(second))
    # Bo'lim hajmi o'zgarmaydi — imtihon shakli bir xil qoladi
    for sec in ("reading", "listening", "writing"):
        assert len(second[sec]) == len(first[sec])


@pytest.mark.parametrize("level", ["A0", "A1", "A2", "B1"])
def test_exam_never_empty_even_if_pool_exhausted(level):
    """Bank tugasa ham imtihon beriladi (eski savollardan)."""
    pool = ex.load_pool(level)
    all_seen = {
        qhash(it)
        for sec in ("reading", "listening", "writing", "speaking", "passages")
        for it in pool.get(sec) or []
    }
    exam = ex.build_exam(level, all_seen)
    cfg = pool["config"]
    assert len(exam["reading"]) == cfg["reading"]
    assert len(exam["listening"]) == cfg["listening"]


@pytest.mark.asyncio
async def test_seen_questions_reads_previous_attempts(session, make_user):
    user = await make_user()
    exam = ex.build_exam("A0")
    session.add(
        ExamAttempt(
            user_id=user.id,
            level="A0",
            kind="level",
            questions_json=json.dumps(exam, ensure_ascii=False),
        )
    )
    # Mini-imtihon urinishi aralashib ketmasligi kerak
    session.add(
        ExamAttempt(
            user_id=user.id,
            level="A0",
            kind="mini",
            checkpoint=25,
            questions_json=json.dumps({"items": []}),
        )
    )
    await session.commit()

    seen = await ex.seen_questions(session, user.id, "A0")
    assert seen == _hashes(exam)

    retake = ex.build_exam("A0", seen)
    assert not (_hashes(retake) & seen)


@pytest.mark.asyncio
async def test_other_users_attempts_do_not_leak(session, make_user):
    a = await make_user("A")
    b = await make_user("B")
    exam = ex.build_exam("A0")
    session.add(
        ExamAttempt(
            user_id=a.id,
            level="A0",
            kind="level",
            questions_json=json.dumps(exam, ensure_ascii=False),
        )
    )
    await session.commit()

    assert await ex.seen_questions(session, b.id, "A0") == set()


# ── Mini-imtihon (checkpoint) ham takrorlanmasin ──


def test_mini_avoids_seen_questions():
    first = cp.build_mini("A0", 25, seed=1)
    assert first is not None
    seen = {qhash(i) for i in first["items"]}
    second = cp.build_mini("A0", 25, seed=2, seen_hashes=seen)
    assert second is not None
    overlap = {qhash(i) for i in second["items"]} & seen
    assert not overlap, "mini-imtihon qayta topshirishda savollar takrorlandi"


def test_pick_fresh_prefers_unseen():
    items = [{"q_uz": f"q{i}", "answer": str(i)} for i in range(6)]
    seen = {qhash(items[0]), qhash(items[1])}
    picked = pick_fresh(items, 4, seen)
    assert len(picked) == 4
    assert not ({qhash(i) for i in picked} & seen)


def test_pick_fresh_falls_back_when_all_seen():
    items = [{"q_uz": f"q{i}", "answer": str(i)} for i in range(3)]
    seen = {qhash(i) for i in items}
    assert len(pick_fresh(items, 3, seen)) == 3
