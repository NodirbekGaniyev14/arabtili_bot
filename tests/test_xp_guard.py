"""K28 pentest — mijoz yuborgan natija XP'ni chegarasiz oshira olmaydi (haftalik reyting VIP sovrini himoyasi).

Ilgari: {"correct": 10**6, "total": 10**6} → million XP (darslar, nazorat, zaif so'zlar, lug'at testi),
bitta kartani cheksiz baholab XP — reytingda halol o'quvchidan sovrin tortib olinardi.
"""

from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select

from db.models import UserWord, XpLog
from services import xp_guard

from play_helpers import answer_run, play_lesson


def test_clamp():
    assert xp_guard.clamp(10**6, 10**6, 14) == (14, 14)
    assert xp_guard.clamp(5, 3, 10) == (3, 3)
    assert xp_guard.clamp(-4, 0, 10) == (0, 1)
    assert xp_guard.clamp(6, 7, 10) == (6, 7)


def test_day_start_is_tashkent_midnight():
    # 2026-09-28 20:30 UTC = 29-sentabr 01:30 Toshkent → kun boshi 28.09 19:00 UTC
    assert xp_guard.day_start_utc(datetime(2026, 9, 28, 20, 30)) == datetime(2026, 9, 28, 19, 0)
    assert xp_guard.day_start_utc(datetime(2026, 9, 28, 10, 0)) == datetime(2026, 9, 27, 19, 0)


@pytest.fixture
def client(session):
    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

    async def _session():
        yield session

    state = {"user": None}
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    try:
        yield c, state
    finally:
        app.dependency_overrides.clear()


async def _xp(session, user_id, prefix=""):
    q = select(func.coalesce(func.sum(XpLog.amount), 0)).where(XpLog.user_id == user_id)
    if prefix:
        q = q.where(XpLog.source.like(prefix + "%"))
    return int((await session.execute(q)).scalar_one())


@pytest.mark.asyncio
async def test_lesson_complete_is_bounded(client, session, make_user, monkeypatch):
    from api import v2

    c, state = client
    state["user"] = u = await make_user("Hacker")
    # K33.2: ball mijoz raqamidan emas — eski usul (correct/total) rad etiladi, javobsiz urinish yiqiladi
    old = await c.post("/api/v2/lessons/a1-01/complete", json={"correct": 10_000, "total": 10_000})
    assert old.status_code == 426
    run_id = (await c.get("/api/v2/lessons/a1-01?v=2")).json()["run"]["id"]
    d = (await c.post("/api/v2/lessons/a1-01/complete", json={"run_id": run_id, "correct": 99, "total": 99})).json()
    assert d["correct"] == 0 and not d["passed"] and d["xp_earned"] == v2.FAIL_XP
    assert (await c.post("/api/v2/lessons/zz-99/complete", json={"run_id": run_id})).status_code == 404
    # tugatilgan urinishni qayta yuborib bo'lmaydi
    assert (await c.post("/api/v2/lessons/a1-01/complete", json={"run_id": run_id})).status_code == 409

    # Kunlik chegara: takror-takror o'ynash XP'ni chegaradan oshirmaydi (progress baribir yoziladi)
    monkeypatch.setattr(v2, "LESSON_XP_DAILY_CAP", 60)
    for _ in range(8):
        await play_lesson(c, session, "a1-01")
    assert await _xp(session, u.id, "lesson:") <= 60


@pytest.mark.asyncio
async def test_honest_lesson_xp_unchanged(client, session, make_user):
    c, state = client
    state["user"] = await make_user("Halol")
    d = await play_lesson(c, session, "a0-01")
    n = d["total"]
    assert n >= 6 and d["correct"] == n and d["perfect"]
    assert d["xp_earned"] == 10 + 2 * n + 5 and d["first_time"]
    d = await play_lesson(c, session, "a0-01", n_correct=n - 1)
    assert d["xp_earned"] == 5 + (n - 1), "takror — oldingidek"


@pytest.mark.asyncio
async def test_checkpoint_xp_once_a_day(client, session, make_user):
    c, state = client
    state["user"] = u = await make_user("Cp")
    assert (await c.post("/api/v2/checkpoint/a0-05/complete", json={"correct": 15, "total": 15})).status_code == 426
    assert (await c.get("/api/v2/checkpoint/a0-05")).status_code == 426
    xps = []
    for _ in range(2):
        q = (await c.get("/api/v2/checkpoint/a0-05?v=2")).json()
        await answer_run(c, session, q["run"]["id"])
        r = await c.post("/api/v2/checkpoint/a0-05/complete", json={"run_id": q["run"]["id"]})
        assert r.status_code == 200, r.text
        assert r.json()["passed"]
        xps.append(r.json()["xp_earned"])
    assert xps == [15 + len(q["questions"]), 0], "XP kuniga bir marta"
    assert await _xp(session, u.id, "checkpoint:") == xps[0]


@pytest.mark.asyncio
async def test_weak_practice_bounded(client, session, make_user):
    c, state = client
    state["user"] = u = await make_user("Weak")
    for i, (ar, uz) in enumerate([("بَيْت", "uy"), ("كِتَاب", "kitob"), ("قَلَم", "qalam"), ("بَاب", "eshik"), ("مَاء", "suv")]):
        session.add(UserWord(user_id=u.id, ar=ar, uz=uz, kind="word", card_type="word", due_date="2000-01-01", lapses=i))
    await session.commit()

    assert (await c.post("/api/practice/weak/complete", json={"correct": 10_000, "total": 10_000})).status_code == 426
    assert (await c.get("/api/practice/weak")).status_code == 426
    total_xp = 0
    for _ in range(10):  # xalqaro chegara: kuniga 50 XP
        w = (await c.get("/api/practice/weak?v=2")).json()
        await answer_run(c, session, w["run"]["id"])
        d = (await c.post("/api/practice/weak/complete", json={"run_id": w["run"]["id"]})).json()
        assert d["correct"] == d["total"] == len(w["items"])
        total_xp += d["xp_earned"]
    assert total_xp == 50 == await _xp(session, u.id, "practice:weak")


@pytest.mark.asyncio
async def test_legacy_vocab_quiz_gives_no_xp(client, session, make_user):
    """Eski /vocab/quiz/submit natijani mijozdan oladi va hech bir ekran ishlatmaydi — soxta raqamga XP yo'q."""
    c, state = client
    state["user"] = u = await make_user("Lugat")
    d = (await c.post("/api/vocab/quiz/submit", json={"level": "A1", "correct": 10_000, "total": 10_000})).json()
    assert d["xp_earned"] == 0
    r = await c.post("/api/vocab/quiz/submit", json={"level": "A1';--", "correct": 5, "total": 0})
    assert r.status_code == 422, "daraja maydoni qisqa"
    assert await _xp(session, u.id, "vocab_quiz:") == 0


@pytest.mark.asyncio
async def test_review_xp_only_for_due_cards(client, session, make_user):
    c, state = client
    state["user"] = u = await make_user("Rev")
    w = UserWord(user_id=u.id, ar="بَيْت", uz="uy", kind="word", due_date="2000-01-01")
    session.add(w)
    await session.commit()
    r = await c.post("/api/review/answer", json={"word_id": w.id, "grade": "good"})
    assert r.status_code == 200, r.text
    assert await _xp(session, u.id, "review") == 1
    for _ in range(20):  # endi karta kelajakka surilgan — takroriy baholash XP bermaydi
        await c.post("/api/review/answer", json={"word_id": w.id, "grade": "good"})
    assert await _xp(session, u.id, "review") == 1


@pytest.mark.asyncio
async def test_xp_today_ignores_yesterday(session, make_user):
    u = await make_user("Kecha")
    session.add(XpLog(user_id=u.id, amount=500, source="lesson:a0-01", created_at=datetime.utcnow() - timedelta(days=2)))
    session.add(XpLog(user_id=u.id, amount=20, source="lesson:a0-02"))
    session.add(XpLog(user_id=u.id, amount=7, source="lessonX"))  # boshqa prefiks emas — «lesson:» bilan boshlanmaydi
    await session.commit()
    assert await xp_guard.xp_today(session, u.id, "lesson:") == 20
    assert await xp_guard.capped(session, u.id, "lesson:", 50, 60) == 40
