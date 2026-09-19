"""STT sifati (K20, «ustoz nutqni tushunsin»): gallyutsinatsiya filtri, jimlik darvozasi,
prompt yig'ish (mavzu so'zlari + savol + langar), /tutor/transcribe topic_id."""

import httpx
import pytest

from services import stt


def test_is_hallucination():
    assert stt.is_hallucination("")
    assert stt.is_hallucination("اشتركوا في القناة")
    assert stt.is_hallucination("شكراً للمشاهدة!")
    assert stt.is_hallucination("ترجمة نانسي قنقر")
    assert stt.is_hallucination("نعم نعم نعم نعم نعم"), "sirtmoq"
    assert stt.is_hallucination("123 ...")
    assert stt.is_hallucination("hello there")
    q = "مَا اسْمُكَ وَمِنْ أَيْنَ أَنْتَ؟"
    assert stt.is_hallucination("ما اسمك ومن أين أنت", q), "savolning aks-sadosi"
    assert not stt.is_hallucination("اسمي كريم وأنا من طشقند", q)
    assert not stt.is_hallucination("نعم")
    assert not stt.is_hallucination("أنا طالب. أسكن في طشقند.")


def test_build_prompt():
    p = stt.build_prompt("مَا اسْمُكَ؟", ["بَيْت", "كِتَاب", "مَدْرَسَة"])
    assert p.endswith(stt.NEUTRAL_PROMPT) and "بيت كتاب مدرسة" in p and "مَا اسْمُكَ؟" in p
    assert p.index("بيت") < p.index("مَا اسْمُكَ") < p.index(stt.NEUTRAL_PROMPT), "muhimi oxirida"
    assert stt.build_prompt() == stt.NEUTRAL_PROMPT
    long = stt.build_prompt("x" * 1000, ["كلمة"] * 500)
    assert len(long) <= stt.PROMPT_MAX and long.endswith(stt.NEUTRAL_PROMPT)


@pytest.mark.asyncio
async def test_transcribe_drops_noise(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "stt_api_key", "gsk_test")
    seen = {}
    responses = [
        httpx.Response(200, json={"text": "اشتركوا في القناة", "segments": [{"start": 0, "end": 1, "avg_logprob": -0.9, "no_speech_prob": 0.3}]}),
        httpx.Response(200, json={"text": "أنا", "segments": [{"start": 0, "end": 0.5, "avg_logprob": -0.5, "no_speech_prob": 0.95}]}),
        httpx.Response(200, json={"text": "أنا طالب", "segments": [{"start": 0, "end": 1, "avg_logprob": -0.2, "no_speech_prob": 0.1}]}),
    ]

    def transport(request: httpx.Request):
        seen["body"] = request.content
        return responses.pop(0)

    class Client(httpx.AsyncClient):
        def __init__(self, **kw):
            kw.pop("timeout", None)
            super().__init__(transport=httpx.MockTransport(transport))

    monkeypatch.setattr(stt.httpx, "AsyncClient", Client)
    stt._stats.update(day="", ok=0, empty=0, rate=0, fail=0, retried=0)
    assert await stt.transcribe_ex(b"abc") == ("", -1), "subtitr gallyutsinatsiyasi"
    assert await stt.transcribe_ex(b"abc") == ("", -1), "nutq yo'q (no_speech 0.95)"
    text, conf = await stt.transcribe_ex(b"abc", prompt=stt.build_prompt("سؤال", ["كلمة"]))
    assert text == "أنا طالب" and conf > 80
    assert stt.NEUTRAL_PROMPT.encode() in seen["body"] and "كلمة".encode() in seen["body"]
    st = stt.stats()
    assert st["ok"] == 1 and st["empty"] == 2 and stt.last_error == ""


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


@pytest.mark.asyncio
async def test_transcribe_endpoint_topic_words(client, make_user, monkeypatch):
    from config import settings

    c, state = client
    state["user"] = await make_user("Nodir")
    monkeypatch.setattr(settings, "stt_api_key", "gsk_test")
    captured = {}

    async def fake(audio, filename="", mime="", prompt=""):
        captured["prompt"] = prompt
        return "أنا طالب", 90

    monkeypatch.setattr(stt, "transcribe_ex", fake)
    r = await c.post(
        "/api/v2/tutor/transcribe",
        data={"prompt": "مَا اسْمُكَ؟", "topic_id": "oila"},
        files={"file": ("s.webm", b"\\x1a\\x45audio-bytes-" * 100, "audio/webm")},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"text": "أنا طالب", "confidence": 90}
    p = captured["prompt"]
    assert p.endswith(stt.NEUTRAL_PROMPT) and "مَا اسْمُكَ؟" in p
    assert len(p.split()) > 15, "oila mavzusi so'zlari qo'shilgan"

    r = await c.post(
        "/api/v2/tutor/transcribe",
        data={"prompt": "س", "topic_id": "yoq-mavzu"},
        files={"file": ("s.webm", b"\\x1a\\x45audio-bytes-" * 100, "audio/webm")},
    )
    assert r.status_code == 200 and captured["prompt"] == stt.build_prompt("س")
