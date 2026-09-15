"""K17.5 — LLM'siz o'rganish: transliteratsiya, talaffuz mashqi (drill),
xatolar daftari, speaking tarixi (/tutor/log), profil hisoblari."""

import json
import random
from datetime import timedelta

import httpx
import pytest

from db.models import DrillResult, MockResult, TutorMistake, TutorTurn, XpLog, utcnow
from services import drill
from services.translit import translit


# ── Transliteratsiya ──


@pytest.mark.parametrize(
    "ar, expected",
    [
        ("كِتَاب", "kitaab"),
        ("شَيْخ", "shayx"),
        ("حِصَان", "hisoon"),  # qalin harfdan keyin cho'ziq a → oo
        ("غَسَّالَة", "g'assaala"),
        ("مُؤَدَّب", "mu'addab"),
        ("سَمَاء", "samaa'"),
        ("أَبَدًا", "abadan"),
        ("مَقْهَى", "maqhaa"),
        ("مِرْآة", "mir'aat"),
        ("جَوْرَب", "javrab"),
        ("شُرْطِيّ", "shurtiy"),
        ("أَرْضِيَّة", "arziyya"),
        ("الشَّيْخُ جَالِسٌ.", "ash-shayxu jaalisun."),
        ("فِي الْبَيْتِ", "fii l-bayti"),
        ("الأَرْضُ كَبِيرَةٌ.", "al-arzu kabiiratun."),
        ("مَا اسْمُكَ؟", "maa smuka?"),
        ("هٰذَا", "haazaa"),
        ("اللهُ", "allohu"),
        ("الحَمْدُ لِلَّهِ", "al-hamdu lillaahi"),
        ("يَوْم", "yavm"),
        ("دَوَاء", "davaa'"),
        ("رَئِيس", "ra'iis"),
        ("بِبُطْءٍ", "bibut'in"),
        ("مُمَثِّل", "mumaththil"),
        ("اِسْم", "ism"),
        ("نَعَمْ، أَنَا بِخَيْرٍ.", "na'am, anaa bixayrin."),
    ],
)
def test_translit_cases(ar, expected):
    assert translit(ar) == expected


def test_translit_keeps_numbers_and_latin():
    assert translit("عِنْدِي 3 كُتُب") == "'indii 3 kutub"
    assert translit("") == ""


# ── Jumla tanlash ──


def test_drill_sentences_level_and_theme():
    from services.vocab import load_level

    rng = random.Random(7)
    items = drill.sentences("A0", "tanishish", rng=rng)
    assert len(items) == drill.DRILL_SIZE
    a0 = {w["example_ar"].strip() for w in load_level("A0")}
    assert all(it["ar"] in a0 for it in items), "A0 o'quvchiga faqat A0 jumlalar"
    assert len({it["ar"] for it in items}) == len(items), "takror jumla"
    for it in items:
        assert it["translit"] and it["uz"] and it["word"]["ar"]

    b2 = drill.sentences("B2", "munozara", rng=random.Random(3))
    assert len(b2) == drill.DRILL_SIZE
    # Mavzuli jumlalar avval o'z darajasidan olinadi
    b2_pool = {w["example_ar"].strip() for w in load_level("B2")}
    assert sum(1 for it in b2 if it["ar"] in b2_pool) >= 5


def test_drill_sentences_unknown_topic_and_level_fallback():
    items = drill.sentences("Z9", "yoq-mavzu", rng=random.Random(1))
    assert len(items) == drill.DRILL_SIZE


def test_drill_session_lifecycle():
    key, items = drill.create(5, "A1", "bozor")
    assert len(items) == 10 and drill.get(key, 5) and drill.get(key, 6) is None
    assert drill.target(key, 5, 0) == items[0]["ar"]
    assert drill.target(key, 5, 99) == "" and drill.target("yoq", 5, 0) == ""
    drill.record(key, 5, 0, 60)
    drill.record(key, 5, 0, 40)  # eng yaxshisi qoladi
    drill.record(key, 5, 1, 90)
    s = drill.summary(key, 5)
    assert s["count"] == 2 and s["score"] == 75 and s["scores"][0] == 60 and s["scores"][2] == -1
    assert drill.xp_for(75, 2) == 0, "5 tadan kam — XP yo'q"
    assert drill.xp_for(75, 5) == 8 and drill.xp_for(100, 10) == 10 and drill.xp_for(3, 5) == 1
    drill.finish(key, 5)
    assert drill.summary(key, 5) is None


def test_drill_sweep_ttl(monkeypatch):
    key, _ = drill.create(1, "A0", "erkin")
    drill._DRILLS[key]["created"] -= drill.TTL + 1
    drill.create(1, "A0", "erkin")
    assert key not in drill._DRILLS


# ── API oqimi ──

_REPLY = {
    "ar": "أَهْلًا",
    "translit": "ahlan",
    "uz": "salom",
    "correction_ok": False,
    "fixed_ar": "أَنَا طَالِبٌ",
    "note_uz": "«طالب» dan oldin «أنا» kerak",
    "hint_uz": "",
    "new_words": [],
    "answer_uz": "",
    "done": False,
}


def _envelope(text: str) -> dict:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "m",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


@pytest.fixture
def client(session, monkeypatch):
    import anthropic

    from config import settings
    from db.session import get_session
    from main import app
    from services import tts
    from services.telegram_auth import get_current_user

    monkeypatch.setattr(settings, "anthropic_api_key", "test")
    monkeypatch.setattr(settings, "stt_api_key", "gsk_test")
    monkeypatch.setattr(tts, "schedule", lambda text, level: "")
    handlers: list = []

    def transport(request: httpx.Request):
        return handlers.pop(0)

    orig = anthropic.AsyncAnthropic

    class Patched(orig):
        def __init__(self, **kw):
            super().__init__(
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)), **kw
            )

    monkeypatch.setattr(anthropic, "AsyncAnthropic", Patched)

    async def _session():
        yield session

    state = {"user": None}
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    try:
        yield c, handlers, state
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_correction_goes_to_mistakes(client, session, make_user):
    from sqlalchemy import select

    c, handlers, state = client
    state["user"] = await make_user(vip_until=utcnow() + timedelta(days=3))
    handlers.append(httpx.Response(200, json=_envelope(json.dumps(_REPLY, ensure_ascii=False))))
    r = await c.post(
        "/api/v2/tutor/turn",
        json={
            "session_key": "abcdefgh1234",
            "topic_id": "tanishish",
            "history": [{"role": "assistant", "content": "x"}, {"role": "user", "content": "🎤 طالب"}],
            "voice": True,
            "mode": "chat",
        },
    )
    assert r.status_code == 200, r.text
    m = (await session.execute(select(TutorMistake))).scalar_one()
    assert m.kind == "chat" and m.topic == "tanishish"
    assert m.said_ar == "طالب" and m.fixed_ar == "أَنَا طَالِبٌ" and "أنا" in m.note_uz

    log = (await c.get("/api/v2/tutor/log")).json()
    assert len(log["mistakes"]) == 1 and log["mistakes"][0]["title"] == "Tanishish"
    # «O'rgandim»
    assert (await c.delete(f"/api/v2/tutor/mistakes/{m.id}")).status_code == 200
    assert (await c.get("/api/v2/tutor/log")).json()["mistakes"] == []
    assert (await c.delete(f"/api/v2/tutor/mistakes/{m.id}")).status_code == 404


@pytest.mark.asyncio
async def test_mistake_notebook_capped(session, make_user):
    from types import SimpleNamespace

    from api.v2 import MISTAKE_KEEP, _note_mistake

    u = await make_user()
    body = SimpleNamespace(mode="chat", topic_id="oila", mock_id="", history=[{"role": "user", "content": "x"}])
    reply = SimpleNamespace(correction_ok=False, fixed_ar="y", note_uz="n")
    for _ in range(MISTAKE_KEEP + 5):
        await _note_mistake(session, u.id, body, reply, -1)
        await session.flush()
    from sqlalchemy import func, select

    n = (await session.execute(select(func.count()).select_from(TutorMistake))).scalar_one()
    assert n == MISTAKE_KEEP


@pytest.mark.asyncio
async def test_drill_flow_scores_and_xp(client, session, make_user, monkeypatch):
    from sqlalchemy import select

    from services import stt

    c, _, state = client
    state["user"] = await make_user()  # VIP emas — mashq bepul

    r = await c.get("/api/v2/tutor/drill", params={"topic_id": "tanishish"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["level"] == "A0" and len(d["items"]) == 10 and d["voice"] is True
    key = d["key"]

    heard = {"text": ""}

    async def fake_transcribe(audio, filename="", mime="", prompt=""):
        return heard["text"]

    monkeypatch.setattr(stt, "transcribe", fake_transcribe)

    # 5 ta jumla: to'liq aytilgan → 100
    for i in range(5):
        heard["text"] = d["items"][i]["ar"]
        r = await c.post(
            "/api/v2/tutor/pronounce",
            data={"drill_key": key, "idx": str(i)},
            files={"file": ("a.webm", b"\x00" * 100, "audio/webm")},
        )
        assert r.status_code == 200, r.text
        assert r.json()["score"] == 100
    # Noto'g'ri idx / begona kalit
    r = await c.post(
        "/api/v2/tutor/pronounce",
        data={"drill_key": "yoq-kalit", "idx": "0"},
        files={"file": ("a.webm", b"\x00" * 100, "audio/webm")},
    )
    assert r.status_code == 404

    r = await c.post("/api/v2/tutor/drill/finish", json={"key": key})
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["score"] == 100 and f["count"] == 5 and f["xp"] == drill.MAX_XP
    assert f["scores"][:5] == [100] * 5 and f["scores"][5] == -1
    assert (await session.execute(select(DrillResult))).scalar_one().xp == drill.MAX_XP
    assert (await session.execute(select(XpLog))).scalar_one().source == f"drill:{key}"
    # Kalit yopildi
    assert (await c.post("/api/v2/tutor/drill/finish", json={"key": key})).status_code == 404

    # Shu mavzu bugun ikkinchi marta — natija yoziladi, XP yo'q
    d2 = (await c.get("/api/v2/tutor/drill", params={"topic_id": "tanishish"})).json()
    for i in range(5):
        heard["text"] = d2["items"][i]["ar"]
        await c.post(
            "/api/v2/tutor/pronounce",
            data={"drill_key": d2["key"], "idx": str(i)},
            files={"file": ("a.webm", b"\x00" * 100, "audio/webm")},
        )
    f2 = (await c.post("/api/v2/tutor/drill/finish", json={"key": d2["key"]})).json()
    assert f2["xp"] == 0 and f2["score"] == 100

    log = (await c.get("/api/v2/tutor/log")).json()
    assert log["drills"][0]["topic_id"] == "tanishish"
    assert log["drills"][0]["attempts"] == 2 and log["drills"][0]["best"] == 100

    prof = (await c.get("/api/profile")).json()
    assert prof["speaking"]["drill_attempts"] == 2 and prof["speaking"]["drill_best"] == 100


@pytest.mark.asyncio
async def test_drill_too_few_sentences_no_xp(client, session, make_user, monkeypatch):
    from services import stt

    c, _, state = client
    state["user"] = await make_user()
    d = (await c.get("/api/v2/tutor/drill", params={"topic_id": "oila"})).json()

    async def fake_transcribe(audio, filename="", mime="", prompt=""):
        return d["items"][0]["ar"]

    monkeypatch.setattr(stt, "transcribe", fake_transcribe)
    await c.post(
        "/api/v2/tutor/pronounce",
        data={"drill_key": d["key"], "idx": "0"},
        files={"file": ("a.webm", b"\x00" * 10, "audio/webm")},
    )
    f = (await c.post("/api/v2/tutor/drill/finish", json={"key": d["key"]})).json()
    assert f["count"] == 1 and f["xp"] == 0 and f["score"] == 100


@pytest.mark.asyncio
async def test_stt_daily_cap(client, make_user, monkeypatch):
    from api import v2
    from services import stt

    c, _, state = client
    u = await make_user()
    state["user"] = u
    monkeypatch.setattr(v2, "STT_DAILY_CAP", 2)
    v2._stt_used.pop(u.id, None)

    async def fake_transcribe(audio, filename="", mime="", prompt=""):
        return "سلام"

    monkeypatch.setattr(stt, "transcribe", fake_transcribe)
    codes = []
    for _ in range(3):
        r = await c.post(
            "/api/v2/tutor/transcribe",
            data={"prompt": ""},
            files={"file": ("a.webm", b"\x00" * 10, "audio/webm")},
        )
        codes.append(r.status_code)
    assert codes == [200, 200, 429]


@pytest.mark.asyncio
async def test_log_mock_history(client, session, make_user):
    c, _, state = client
    u = await make_user()
    state["user"] = u
    for s in (40, 70, 65):
        session.add(MockResult(user_id=u.id, mock_id="shifokor", level="A2", score=s, session_key="k"))
    session.add(MockResult(user_id=u.id, mock_id="gid", level="A2", score=90, session_key="k2"))
    await session.commit()
    log = (await c.get("/api/v2/tutor/log")).json()
    assert [m["mock_id"] for m in log["mocks"]] == ["gid", "shifokor"]
    sh = log["mocks"][1]
    assert sh["best"] == 70 and sh["last"] == 65 and sh["attempts"] == 3 and sh["history"] == [40, 70, 65]
    assert sh["title"] and sh["emoji"]
    prof = (await c.get("/api/profile")).json()
    assert prof["speaking"] == {
        "mistakes": 0, "mock_attempts": 4, "mock_best": 90, "drill_attempts": 0, "drill_best": 0,
    }


def test_topics_expose_vip_turns_label():
    import inspect

    from api import v2

    assert '"vip_turns"' in inspect.getsource(v2.tutor_topics)
