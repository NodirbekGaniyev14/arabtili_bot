"""K17.6 — mock imtihoni 4 mezon (lug'at/grammatika/mazmun + STT talaffuz-aniqlik),
sertifikat rasmi (shaxsiy rekord), kasblar katalogi."""

import json
from datetime import timedelta

import httpx
import pytest

from db.models import Certificate, MockResult, TutorTurn, utcnow
from services import stt, tutor


# ── STT ishonch bali ──


def _seg(lp, start=0.0, end=2.0, nsp=0.0):
    return {"avg_logprob": lp, "start": start, "end": end, "no_speech_prob": nsp}


def test_confidence_mapping():
    assert stt.confidence_of({"segments": [_seg(-0.1)]}) == 100
    assert stt.confidence_of({"segments": [_seg(-0.15)]}) == 100
    assert stt.confidence_of({"segments": [_seg(-1.2)]}) == 30
    assert stt.confidence_of({"segments": [_seg(-2.5)]}) == 0
    mid = stt.confidence_of({"segments": [_seg(-0.5)]})
    assert 70 < mid < 80
    # Davomiylik bo'yicha o'rtacha: uzun aniq segment qisqa yomonini bosadi
    mixed = stt.confidence_of({"segments": [_seg(-0.1, 0, 8), _seg(-1.2, 8, 9)]})
    assert mixed > 90
    # Nutq yo'q ehtimoli yuqori — jarima
    assert stt.confidence_of({"segments": [_seg(-0.1, nsp=0.9)]}) == 80
    assert stt.confidence_of({"segments": []}) == -1 and stt.confidence_of({}) == -1


@pytest.mark.asyncio
async def test_transcribe_ex_returns_confidence(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "stt_api_key", "gsk_test")
    payload = {"text": " مرحبا ", "segments": [_seg(-0.2)]}

    def transport(request: httpx.Request):
        assert b"verbose_json" in request.content
        return httpx.Response(200, json=payload)

    class Client(httpx.AsyncClient):
        def __init__(self, **kw):
            kw.pop("timeout", None)
            super().__init__(transport=httpx.MockTransport(transport))

    monkeypatch.setattr(stt.httpx, "AsyncClient", Client)
    text, conf = await stt.transcribe_ex(b"abc")
    assert text == "مرحبا" and conf == 97
    assert await stt.transcribe(b"abc") == "مرحبا"
    payload["text"] = ""
    assert await stt.transcribe_ex(b"abc") == ("", -1)


# ── API oqimi ──


class FakeBot:
    def __init__(self):
        self.photos: list = []

    async def send_photo(self, chat_id, photo, caption="", reply_markup=None, **kw):
        self.photos.append((chat_id, caption, reply_markup))

    async def send_message(self, *a, **kw):
        pass


def _mock_json(vocab, grammar, content, done=False):
    return {
        "ar": "سُؤَال",
        "translit": "su'aal",
        "uz": "savol",
        "score": 1,  # model bergan umumiy ball e'tiborga olinmaydi
        "vocab": vocab,
        "grammar": grammar,
        "content": content,
        "feedback_uz": "yaxshi",
        "ideal_ar": "جَوَاب نَمُوذَجِيّ",
        "done": done,
    }


def _envelope(obj: dict) -> dict:
    return {
        "id": "m",
        "type": "message",
        "role": "assistant",
        "model": "m",
        "content": [{"type": "text", "text": json.dumps(obj, ensure_ascii=False)}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


@pytest.fixture
def client(session, monkeypatch, tmp_path):
    import anthropic

    from config import settings
    from db.session import get_session
    from main import app
    from services import certificate, tts
    from services.telegram_auth import get_current_user

    monkeypatch.setattr(settings, "anthropic_api_key", "test")
    monkeypatch.setattr(settings, "stt_api_key", "gsk_test")
    monkeypatch.setattr(tts, "schedule", lambda text, level: "")
    monkeypatch.setattr(certificate, "CERT_DIR", tmp_path / "certs")
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
    bot = FakeBot()
    app.state.bot = bot
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    try:
        yield c, handlers, state, bot
    finally:
        app.dependency_overrides.clear()
        del app.state.bot


async def _run_mock(c, handlers, key, answers, voice_conf=None, monkeypatch=None):
    """5 javobli mock: har javob uchun (vocab, grammar, content). voice_conf — STT bali."""
    from api import v2

    hist = []
    handlers.append(httpx.Response(200, json=_envelope(_mock_json(-1, -1, -1))))
    r = await c.post(
        "/api/v2/tutor/turn",
        json={"session_key": key, "topic_id": "erkin", "history": [], "voice": False, "mode": "mock", "mock_id": "shifokor"},
    )
    assert r.status_code == 200, r.text
    hist.append({"role": "assistant", "content": r.json()["reply"]["ar"]})
    out = []
    for i, (v, g, ct) in enumerate(answers):
        hist.append({"role": "user", "content": f"🎤 جواب {i}"})
        if voice_conf is not None:
            v2._put_voice_conf(1, key, voice_conf)  # user.id = 1 (birinchi make_user)
        handlers.append(httpx.Response(200, json=_envelope(_mock_json(v, g, ct, done=i == len(answers) - 1))))
        r = await c.post(
            "/api/v2/tutor/turn",
            json={
                "session_key": key, "topic_id": "erkin", "history": hist,
                "voice": voice_conf is not None, "mode": "mock", "mock_id": "shifokor",
            },
        )
        assert r.status_code == 200, r.text
        out.append(r.json()["reply"])
        hist.append({"role": "assistant", "content": r.json()["reply"]["ar"]})
    return out


@pytest.mark.asyncio
async def test_mock_criteria_pron_and_certificate(client, session, make_user, monkeypatch):
    from sqlalchemy import select

    c, handlers, state, bot = client
    u = await make_user("Nodir", vip_until=utcnow() + timedelta(days=5))
    assert u.id == 1
    state["user"] = u

    replies = await _run_mock(
        c, handlers, "mocksession01",
        [(90, 70, 80), (80, 80, 80), (100, 90, 90), (70, 60, 80), (90, 90, 100)],
        voice_conf=88,
    )
    first = replies[0]
    assert (first["vocab"], first["grammar"], first["content"], first["pron"]) == (90, 70, 80, 88)
    assert first["score"] == round((90 + 70 + 80 + 88) / 4)
    turns = (await session.execute(select(TutorTurn).order_by(TutorTurn.id))).scalars().all()
    assert turns[0].score == -1 and turns[0].vocab == -1, "ochilish turn'i baholanmaydi"
    assert (turns[1].vocab, turns[1].grammar, turns[1].content, turns[1].pron) == (90, 70, 80, 88)

    r = await c.post("/api/v2/tutor/finish", json={"session_key": "mocksession01"})
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["mock"] and len(f["scores"]) == 5 and f["xp"] > 0
    assert f["criteria"] == {"vocab": 86, "grammar": 78, "content": 86, "pron": 88}
    assert f["certificate"] and f["certificate"]["png_url"].endswith(".png")

    mr = (await session.execute(select(MockResult))).scalar_one()
    assert (mr.vocab, mr.grammar, mr.content, mr.pron) == (86, 78, 86, 88) and mr.score == f["score"]
    cert = (await session.execute(select(Certificate))).scalar_one()
    assert cert.kind == "mock" and cert.score == f["score"] and cert.level == "A0"
    assert json.loads(cert.scores_json)["mock_id"] == "shifokor"
    from pathlib import Path

    assert Path(cert.png_path).exists() and Path(cert.png_path).stat().st_size > 10_000
    assert len(bot.photos) == 1 and "rekord" in bot.photos[0][1]
    assert bot.photos[0][2] is not None, "ulashish tugmasi"

    # Verify sahifasi
    r = await c.get(f"/api/verify/{cert.cert_id.split('-')[-1]}")
    assert r.status_code == 200 and "Speaking mock" in r.text and "Shifokor" in r.text

    # Pastroq natija — sertifikat yo'q (rekord emas), XP ham kuniga bir marta
    await _run_mock(c, handlers, "mocksession02", [(50, 50, 50)] * 5)
    f2 = (await c.post("/api/v2/tutor/finish", json={"session_key": "mocksession02"})).json()
    assert f2["certificate"] is None and f2["xp"] == 0
    assert f2["criteria"]["pron"] == -1, "matnli javob — talaffuz o'lchanmaydi"
    assert len(bot.photos) == 1


@pytest.mark.asyncio
async def test_no_certificate_below_threshold(client, session, make_user):
    from sqlalchemy import func, select

    c, handlers, state, bot = client
    state["user"] = await make_user("Ali", vip_until=utcnow() + timedelta(days=5))
    await _run_mock(c, handlers, "mocksession03", [(60, 60, 60)] * 5)
    f = (await c.post("/api/v2/tutor/finish", json={"session_key": "mocksession03"})).json()
    assert f["score"] == 60 and f["certificate"] is None and f["xp"] == 30
    assert (await session.execute(select(func.count()).select_from(Certificate))).scalar_one() == 0
    assert bot.photos == []


@pytest.mark.asyncio
async def test_voice_conf_handoff_via_transcribe(client, make_user, monkeypatch):
    from api import v2

    c, _, state, _ = client
    u = await make_user()
    state["user"] = u

    async def fake_ex(audio, filename="", mime="", prompt=""):
        return "سلام", 77

    monkeypatch.setattr(stt, "transcribe_ex", fake_ex)
    r = await c.post(
        "/api/v2/tutor/transcribe",
        data={"prompt": "", "session_key": "sessionkey001"},
        files={"file": ("a.webm", b"\x00" * 10, "audio/webm")},
    )
    assert r.status_code == 200 and r.json() == {"text": "سلام", "confidence": 77}
    assert v2._take_voice_conf(u.id, "sessionkey001") == 77
    assert v2._take_voice_conf(u.id, "sessionkey001") == -1, "bir marta olinadi"
    # Muddati o'tgan
    v2._put_voice_conf(u.id, "s2", 50)
    v2._voice_conf[(u.id, "s2")] = (50, 0.0)
    assert v2._take_voice_conf(u.id, "s2") == -1


def test_mock_catalog_levels():
    a1 = [m for m in tutor.mock_list("A1") if m["recommended"]]
    assert {m["id"] for m in a1} >= {"haydovchi", "sotuvchi", "tikuvchi", "quruvchi", "sartarosh"}
    b1 = tutor.mock_list("B1")
    assert all(m["recommended"] for m in b1)
    assert tutor.MOCK_BY_ID["masjid"]["min_level"] == "A2"


def test_migrations_have_no_duplicate_tables():
    """dict'da bir xil kalit ikki marta yozilsa keyingisi avvalgisini yutadi —
    tutor_turns ustunlari yo'qolgan edi."""
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "backend" / "db" / "session.py"
    body = src.read_text(encoding="utf-8")
    start = body.index("_MIGRATIONS = {")
    end = body.index("\n}\n", start)
    keys = re.findall(r'^\s{4}"([a-z_]+)": \{', body[start:end], flags=re.M)
    assert len(keys) == len(set(keys)), f"takror jadval: {keys}"
    from db.session import _MIGRATIONS

    assert {"vocab", "grammar", "content", "pron", "mode", "score"} <= set(_MIGRATIONS["tutor_turns"])
