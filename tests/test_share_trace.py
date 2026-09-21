"""K21.5 ulashish kartasi (PNG, ochiq fayl, botga yuborish) va K21.6 harf chizish (bank, XP, kunlik limit)."""

from datetime import datetime, timedelta

import httpx
import pytest

from db.models import XpLog
from services import share_card, trace


@pytest.fixture
def client(session, monkeypatch, tmp_path):
    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

    monkeypatch.setattr(share_card, "SHARE_DIR", tmp_path / "share")

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


def test_render_card(tmp_path):
    data = {
        "name": "Nodir", "level": "A1", "streak": 3, "words": 40, "lessons_total": 5, "week_xp": 120, "week_lessons": 2,
        "week": [10, 0, 50, 0, 0, 30, 30], "week_days": ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"], "rank": 4, "total": 50,
        "ref_link": "https://t.me/JamalArabiy_bot?start=ref1", "ref_days": 3,
    }
    out = tmp_path / "c.png"
    share_card.render(data, out)
    assert out.exists() and out.stat().st_size > 20_000
    from PIL import Image

    assert Image.open(out).size == (share_card.W, share_card.H)
    cap = share_card.caption(data)
    assert "3 kun" in cap and data["ref_link"] in cap and "#4" in cap


def test_public_origin(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "webapp_url", "https://arabiy.example/app?x=1")
    assert share_card.public_origin() == "https://arabiy.example"
    monkeypatch.setattr(settings, "webapp_url", "")
    assert share_card.public_origin() == ""


@pytest.mark.asyncio
async def test_share_week_api(client, make_user, session, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "webapp_url", "https://arabiy.example")
    c, state = client
    u = await make_user("Nodir")
    state["user"] = u
    session.add(XpLog(user_id=u.id, amount=25, source="lesson:a0-01"))
    await session.commit()

    r = await c.post("/api/share/week", json={"send": False})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["url"].startswith("https://arabiy.example/api/share/week_") and d["sent"] is False
    assert d["week_xp"] == 25 and d["ref_link"].endswith(f"ref{u.tg_id}")
    first = d["path"].split("/")[-1]
    f = await c.get(d["path"])
    assert f.status_code == 200 and f.headers["content-type"] == "image/png"
    # Qayta yasalganda eski fayl o'chadi; xavfli nomlar 404
    d2 = (await c.post("/api/share/week", json={"send": True})).json()
    assert d2["path"] != d["path"] and d2["sent"] is False, "bot yo'q — sent=False"
    assert (await c.get(d["path"])).status_code == 404
    assert len(list(share_card.SHARE_DIR.glob(f"week_{u.id}_*.png"))) == 1
    assert (await c.get("/api/share/..%2Fsecret.png")).status_code == 404
    assert (await c.get("/api/share/x.txt")).status_code == 404
    assert first != d2["path"].split("/")[-1]


def test_trace_bank_and_scoring():
    L = trace.letters()
    assert len(L) == 28 and L[0]["ar"] == "ا" and L[0]["name"] == "alif" and L[0]["audio"]
    assert trace.xp_for(90, 4) == 0, "kamida 5 harf"
    assert trace.xp_for(90, 5) == 9 and trace.xp_for(100, 10) == 10 and trace.xp_for(4, 6) == 1
    assert trace.clean_scores({"ا": 150, "ب": -3, "x": 50, "ت": "77", "ث": "yo'q"}) == {"ا": 100, "ب": 0, "ت": 77}


@pytest.mark.asyncio
async def test_trace_finish_xp_once_a_day(client, make_user, session):
    c, state = client
    u = await make_user("Chizuvchi")
    state["user"] = u
    info = (await c.get("/api/v2/trace")).json()
    assert len(info["letters"]) == 28 and info["best"] == {} and info["xp_today"] is False and info["pass"] == 70

    assert (await c.post("/api/v2/trace/finish", json={"scores": {}})).status_code == 422
    r = (await c.post("/api/v2/trace/finish", json={"scores": {"ا": 90, "ب": 80, "ت": 70, "ث": 60, "ج": 100}})).json()
    assert r["avg"] == 80 and r["count"] == 5 and r["xp"] == 8 and r["best"]["ج"] == 100
    # Shu kuni ikkinchi marta — XP yo'q, eng yaxshi ball saqlanadi
    r2 = (await c.post("/api/v2/trace/finish", json={"scores": {"ا": 95, "ب": 10, "ت": 70, "ث": 60, "ج": 50}})).json()
    assert r2["xp"] == 0 and r2["best"] == {"ا": 95, "ب": 80, "ت": 70, "ث": 60, "ج": 100}
    info = (await c.get("/api/v2/trace")).json()
    assert info["xp_today"] is True and info["best"]["ا"] == 95
    xp = (await session.execute(__import__("sqlalchemy").select(XpLog).where(XpLog.user_id == u.id))).scalars().all()
    assert [x.amount for x in xp] == [8] and xp[0].source == "trace"
    # Ertaga yana mumkin
    assert await trace.xp_taken_today(session, u.id, datetime.utcnow() + timedelta(days=1)) is False
