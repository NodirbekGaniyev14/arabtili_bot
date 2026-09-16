"""K18.3 — tinglab tushunish: variantlar, sessiya (matn oldindan berilmaydi),
javob tekshiruvi (tanlash / diktant), XP, API oqimi, log."""

import random

import httpx
import pytest

from db.models import ListeningResult, XpLog
from services import listening


def test_build_choice_and_dictation():
    items = listening.build("A1", "oila", "choice", random.Random(3))
    assert len(items) == listening.SIZE
    for it in items:
        assert len(it["options"]) == listening.CHOICES
        assert len(set(it["options"])) == listening.CHOICES, "variantlar takror"
        assert it["options"][it["answer"]] == it["uz"]
    d = listening.build("B1", "ish", "dictation", random.Random(1))
    assert len(d) == listening.SIZE and "options" not in d[0]
    assert listening.build("A0", "erkin", "nomalum", random.Random(1))[0].get("options"), "noma'lum rejim → tanlash"


def test_session_choice_and_dictation():
    key, d = listening.create(7, "A1", "bozor", "choice")
    pub = listening.public_items(d)
    assert all("ar" not in p and "uz" not in p for p in pub), "matn oldindan sizmaydi"
    assert len(pub[0]["options"]) == 4
    assert listening.get(key, 8) is None

    it = d["items"][0]
    wrong = (it["answer"] + 1) % 4
    r = listening.answer(key, 7, 0, choice=wrong)
    assert r["correct"] is False and r["score"] == 0 and r["ar"] == it["ar"] and r["answer"] == it["answer"]
    # Qayta urinish ballni o'zgartirmaydi (birinchi urinish hisob)
    r2 = listening.answer(key, 7, 0, choice=it["answer"])
    assert r2["correct"] is True and listening.summary(key, 7)["scores"][0] == 0
    assert listening.answer(key, 7, 1, choice=d["items"][1]["answer"])["score"] == 100
    assert listening.answer(key, 7, 1, choice=9) is None and listening.answer(key, 7, 99, choice=0) is None
    s = listening.summary(key, 7)
    assert s["count"] == 2 and s["score"] == 50 and s["kind"] == "choice"

    key2, d2 = listening.create(7, "A2", "safar", "dictation")
    it = d2["items"][0]
    r = listening.answer(key2, 7, 0, text=it["ar"])
    assert r["correct"] is True and r["score"] == 100 and r["words"]
    r = listening.answer(key2, 7, 1, text="")
    assert r["score"] == 0 and r["correct"] is False

    assert listening.xp_for(90, 4) == 0 and listening.xp_for(90, 5) == 9 and listening.xp_for(0, 5) == 0
    listening.finish(key, 7)
    assert listening.summary(key, 7) is None


@pytest.fixture
def client(session, monkeypatch):
    from db.session import get_session
    from main import app
    from services import tts
    from services.telegram_auth import get_current_user

    monkeypatch.setattr(tts, "schedule", lambda text, level: "")

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


@pytest.mark.asyncio
async def test_listen_api_flow(client, session, make_user):
    from sqlalchemy import select

    c, state = client
    state["user"] = await make_user()

    r = await c.get("/api/v2/tutor/listen", params={"topic_id": "oila", "kind": "choice"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["kind"] == "choice" and d["level"] == "A0" and len(d["items"]) == 10
    assert "ar" not in d["items"][0] and len(d["items"][0]["options"]) == 4
    key = d["key"]

    # 5 ta javob: to'g'ri variantni bilmaymiz — javob qaytargan `answer` bilan solishtiramiz
    scores = []
    for i in range(5):
        r = await c.post("/api/v2/tutor/listen/answer", json={"key": key, "idx": i, "choice": 0})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ar"] and body["uz"] and "answer" in body
        scores.append(body["score"])
        assert body["correct"] == (body["answer"] == 0)
    assert (await c.post("/api/v2/tutor/listen/answer", json={"key": "yoq-kalit-1", "idx": 0, "choice": 0})).status_code == 404

    f = (await c.post("/api/v2/tutor/listen/finish", json={"key": key})).json()
    assert f["count"] == 5 and f["score"] == round(sum(scores) / 5) and f["total"] == 10
    assert f["xp"] == listening.xp_for(f["score"], 5)
    row = (await session.execute(select(ListeningResult))).scalar_one()
    assert row.topic == "oila" and row.kind == "choice" and row.count == 5
    if f["xp"]:
        assert (await session.execute(select(XpLog))).scalar_one().source == f"listen:{key}"
    assert (await c.post("/api/v2/tutor/listen/finish", json={"key": key})).status_code == 404

    # Diktant — to'liq to'g'ri matn
    d2 = (await c.get("/api/v2/tutor/listen", params={"topic_id": "oila", "kind": "dictation"})).json()
    assert "options" not in d2["items"][0]
    r = await c.post("/api/v2/tutor/listen/answer", json={"key": d2["key"], "idx": 0, "text": "x"})
    ar = r.json()["ar"]
    r = await c.post("/api/v2/tutor/listen/answer", json={"key": d2["key"], "idx": 1, "text": ar})
    assert r.json()["score"] < 100 or r.json()["ar"] == ar

    log = (await c.get("/api/v2/tutor/log")).json()
    assert log["listens"][0]["topic_id"] == "oila" and "tanlash" in log["listens"][0]["title"]

    # Baho rejimi «listen» qabul qilinadi
    r = await c.post("/api/v2/tutor/rate", json={"session_key": key, "mode": "listen", "topic": "oila", "good": True})
    assert r.status_code == 200
