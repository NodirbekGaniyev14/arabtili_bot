"""#F70 (K23) — rad etilgan yozma javoblar jurnali: yozish filtri, tozalash, hisobot, API."""

import httpx
import pytest
from sqlalchemy import func, select

from db.models import AnswerLog
from services import answer_log


@pytest.mark.asyncio
async def test_record_filters_and_report(session, make_user):
    u1 = await make_user("A")
    u2 = await make_user("B")
    ok = await answer_log.record(session, u1.id, "a0-12", "translate_ar_uz", "كِتَاب", "kitob", "kitob ")
    assert ok
    assert not await answer_log.record(session, u1.id, "a0-12", "mcq", "q", "x", "y"), "variantli tur yozilmaydi"
    assert not await answer_log.record(session, u1.id, "a0-12", "dictation", "q", "x", "   "), "bo'sh javob yozilmaydi"
    await answer_log.record(session, u2.id, "a0-12", "translate_ar_uz", "كِتَاب", "kitob", "kitob ")
    await answer_log.record(session, u2.id, "a0-12", "translate_ar_uz", "كِتَاب", "kitob", "daftar")
    await answer_log.record(session, u2.id, "cp25", "harakat", "harakat qo'ying", "مُدَرِّس", "مُدَرِس")
    await session.commit()

    rep = await answer_log.report(session, days=30, top=10)
    assert rep["total"] == 4
    top = rep["items"][0]
    assert (top["context"], top["ex_type"], top["users"], top["n"]) == ("a0-12", "translate_ar_uz", 2, 3)
    assert top["given"][0] == ("kitob", 2), "eng ko'p yozilgan javob oldinda, qisqartirilgan"
    assert rep["items"][1]["context"] == "cp25"
    text = answer_log.report_text(rep)
    assert "a0-12" in text and "«kitob»×2" in text and "«daftar»" in text and "<b>" in text
    assert "yozuv yo'q" in answer_log.report_text({"total": 0, "days": 7, "items": []})


@pytest.mark.asyncio
async def test_prune_keeps_newest(session, make_user, monkeypatch):
    u = await make_user()
    monkeypatch.setattr(answer_log, "MAX_ROWS", 5)
    monkeypatch.setattr(answer_log, "PRUNE_EVERY", 10_000)  # avtomatik tozalash yo'q — qo'lda
    for i in range(8):
        await answer_log.record(session, u.id, "a0-01", "dictation", "q", "x", f"j{i}")
    await session.commit()
    removed = await answer_log.prune(session)
    await session.commit()
    assert removed == 3
    rows = (await session.execute(select(AnswerLog.given).order_by(AnswerLog.id))).scalars().all()
    assert rows == ["j3", "j4", "j5", "j6", "j7"]
    assert await answer_log.prune(session) == 0


@pytest.mark.asyncio
async def test_answer_log_api(session, make_user):
    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

    u = await make_user()

    async def _session():
        yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: u
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post(
                "/api/v2/answer-log",
                json={"context": "a0-05", "ex_type": "fill_blank", "q": "…", "expected": "قَلَمٌ", "given": "قلم"},
            )
            assert r.status_code == 200 and r.json()["ok"] is True
            r = await c.post("/api/v2/answer-log", json={"context": "a0-05", "ex_type": "mcq", "expected": "x", "given": "y"})
            assert r.status_code == 200 and r.json()["ok"] is False
            r = await c.post("/api/v2/answer-log", json={"ex_type": "dictation", "expected": "", "given": "y"})
            assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()
    assert (await session.execute(select(func.count()).select_from(AnswerLog))).scalar_one() == 1
    row = (await session.execute(select(AnswerLog))).scalar_one()
    assert row.user_id == u.id and row.context == "a0-05" and row.given == "قلم"
