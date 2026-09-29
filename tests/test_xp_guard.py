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
async def test_lesson_complete_is_bounded(client, session, make_user):
    c, state = client
    state["user"] = u = await make_user("Hacker")
    r = await c.post("/api/v2/lessons/a1-01/complete", json={"correct": 10_000, "total": 10_000})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["perfect"] and d["score"] == 100
    assert d["xp_earned"] <= 10 + 2 * 14 + 5, "savollar soniga qisilgan (mikro-test ≤ 10 + o'qish ≤ 4)"
    too_big = await c.post("/api/v2/lessons/a1-01/complete", json={"correct": 10**6, "total": 10**6})
    assert too_big.status_code == 422
    assert (await c.post("/api/v2/lessons/zz-99/complete", json={"correct": 1, "total": 1})).status_code == 404

    # Kunlik chegara: takror-takror yuborish XP'ni 600 dan oshirmaydi (progress baribir yoziladi)
    for _ in range(40):
        await c.post("/api/v2/lessons/a1-01/complete", json={"correct": 14, "total": 14})
    assert await _xp(session, u.id, "lesson:") <= 600


@pytest.mark.asyncio
async def test_honest_lesson_xp_unchanged(client, session, make_user):
    c, state = client
    state["user"] = await make_user("Halol")
    d = (await c.post("/api/v2/lessons/a0-01/complete", json={"correct": 7, "total": 7})).json()
    assert d["xp_earned"] == 10 + 2 * 7 + 5 and d["first_time"]
    d = (await c.post("/api/v2/lessons/a0-01/complete", json={"correct": 6, "total": 7})).json()
    assert d["xp_earned"] == 5 + 6, "takror — oldingidek"


@pytest.mark.asyncio
async def test_checkpoint_xp_once_a_day(client, session, make_user):
    c, state = client
    state["user"] = u = await make_user("Cp")
    r = await c.post("/api/v2/checkpoint/a0-05/complete", json={"correct": 10**4, "total": 10**4})
    assert r.status_code == 200, r.text
    assert r.json()["xp_earned"] == 15 + 15, "15 savolga qisilgan"
    r = await c.post("/api/v2/checkpoint/a0-05/complete", json={"correct": 15, "total": 15})
    assert r.json()["xp_earned"] == 0 and await _xp(session, u.id, "checkpoint:") == 30


@pytest.mark.asyncio
async def test_weak_practice_and_vocab_quiz_bounded(client, session, make_user):
    c, state = client
    state["user"] = u = await make_user("Weak")
    d = (await c.post("/api/practice/weak/complete", json={"correct": 10_000, "total": 10_000})).json()
    assert d["xp_earned"] == 10
    for _ in range(10):
        await c.post("/api/practice/weak/complete", json={"correct": 10, "total": 10})
    assert await _xp(session, u.id, "practice:weak") == 50

    d = (await c.post("/api/vocab/quiz/submit", json={"level": "A1", "correct": 10_000, "total": 10_000})).json()
    assert d["xp_earned"] == 40 + 10 and d["passed"]
    r = await c.post("/api/vocab/quiz/submit", json={"level": "A1';--", "correct": 5, "total": 0})
    assert r.status_code == 422, "daraja maydoni qisqa"
    d = (await c.post("/api/vocab/quiz/submit", json={"level": "A1'", "correct": 5, "total": 0})).json()
    assert d["xp_earned"] >= 0
    for _ in range(5):
        await c.post("/api/vocab/quiz/submit", json={"level": "A1", "correct": 40, "total": 40})
    assert await _xp(session, u.id, "vocab_quiz:") == 100
    sources = (await session.execute(select(XpLog.source).where(XpLog.source.like("vocab_quiz:%")))).scalars().all()
    assert all(s in ("vocab_quiz:A1", "vocab_quiz:all") for s in sources), sources


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
