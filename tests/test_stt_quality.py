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


# ── K21.7: OpenAI gpt-4o-transcribe asosiy, Groq zaxira ──


_REAL_CLIENT = httpx.AsyncClient  # patch'dan oldingi haqiqiy sinf (bir testda ikki marta patch qilinganda ham)


def _client(monkeypatch, responses: list, seen: list):
    def transport(request: httpx.Request):
        seen.append((str(request.url), request.content))
        return responses.pop(0)

    class Client(_REAL_CLIENT):
        def __init__(self, **kw):
            kw.pop("timeout", None)
            super().__init__(transport=httpx.MockTransport(transport))

    monkeypatch.setattr(stt.httpx, "AsyncClient", Client)


def test_openai_cost_and_logprob_confidence():
    assert stt.openai_cost("gpt-4o-transcribe", {"type": "tokens", "input_token_details": {"audio_tokens": 1000, "text_tokens": 50}, "output_tokens": 20}) == pytest.approx(0.006325)
    assert stt.openai_cost("gpt-4o-mini-transcribe", {"type": "tokens", "input_token_details": {"audio_tokens": 1000}, "output_tokens": 0}) == pytest.approx(0.003)
    assert stt.openai_cost("whisper-1", {"type": "duration", "seconds": 30}) == pytest.approx(0.003)
    assert stt.openai_cost("gpt-4o-transcribe", None) == 0.0
    assert stt.confidence_from_logprobs([{"logprob": -0.05}, {"logprob": -0.1}]) == 100
    assert stt.confidence_from_logprobs([{"logprob": -1.0}]) == 30
    assert stt.confidence_from_logprobs([]) == -1
    assert stt.confidence_of({"logprobs": [{"logprob": -0.55}]}) == 65


@pytest.mark.asyncio
async def test_openai_primary_then_groq_fallback(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "stt_api_key", "gsk_test")
    monkeypatch.setattr(settings, "stt_openai_api_key", "sk-test")
    stt._stats.update(day="", **stt._EMPTY_STATS)
    stt.openai_error = ""
    assert [p.name for p in stt.providers()] == ["openai", "groq"]

    seen: list = []
    _client(monkeypatch, [
        # 1) OpenAI ok — json + logprobs + usage
        httpx.Response(200, json={"text": "أنا طالب", "logprobs": [{"token": "أنا", "logprob": -0.05}, {"token": " طالب", "logprob": -0.2}],
                                  "usage": {"type": "tokens", "input_token_details": {"audio_tokens": 1000, "text_tokens": 40}, "output_tokens": 10}}),
        # 2) OpenAI 401 → Groq ok
        httpx.Response(401, json={"error": {"message": "invalid key"}}),
        httpx.Response(200, json={"text": "مرحبا", "segments": [{"start": 0, "end": 1, "avg_logprob": -0.2, "no_speech_prob": 0.1}]}),
        # 3) OpenAI 500 → Groq 503 — hammasi yiqildi
        httpx.Response(500, text="boom"),
        httpx.Response(503, text="down"),
    ], seen)

    text, conf = await stt.transcribe_ex(b"abc", prompt=stt.build_prompt("سؤال", ["كلمة"]))
    assert text == "أنا طالب" and conf >= 95
    assert seen[0][0].startswith("https://api.openai.com/v1/audio/transcriptions")
    body = seen[0][1]
    assert b"gpt-4o-transcribe" in body and b'name="include[]"' in body and b"logprobs" in body and b"verbose_json" not in body
    assert stt.NEUTRAL_PROMPT.encode() in body, "prompt OpenAI'ga ham boradi"
    st = stt.stats()
    assert st["openai"] == 1 and st["openai_cost"] == pytest.approx(0.0062) and st["ok"] == 1

    text, conf = await stt.transcribe_ex(b"abc")
    assert text == "مرحبا" and conf > 80 and seen[2][0].startswith("https://api.groq.com")
    assert stt.openai_error == "auth" and stt.last_error == "", "zaxira ishladi — umumiy xato yo'q"
    st = stt.stats()
    assert st["openai_fail"] == 1 and st["fallback"] == 1 and st["ok"] == 2

    assert await stt.transcribe_ex(b"abc") == ("", -1)
    assert stt.last_error == "http:503" and stt.openai_error == "http:500"
    assert stt.stats()["fail"] == 1 and stt.stats()["fallback"] == 2


@pytest.mark.asyncio
async def test_groq_only_unchanged_and_openai_only(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "stt_api_key", "gsk_test")
    monkeypatch.setattr(settings, "stt_openai_api_key", "")
    assert [p.name for p in stt.providers()] == ["groq"]
    seen: list = []
    _client(monkeypatch, [httpx.Response(200, json={"text": "نعم", "segments": []})], seen)
    assert await stt.transcribe_ex(b"abc") == ("نعم", -1)
    assert b"verbose_json" in seen[0][1] and b"include" not in seen[0][1]

    # Faqat OpenAI (Groq kaliti bo'sh) — zaxira yo'q, xato to'g'ridan-to'g'ri
    monkeypatch.setattr(settings, "stt_api_key", "")
    monkeypatch.setattr(settings, "stt_openai_api_key", "sk-test")
    assert stt.available() and [p.name for p in stt.providers()] == ["openai"]
    _client(monkeypatch, [httpx.Response(429, headers={"retry-after": "0.2"}, text="slow"), httpx.Response(429, text="slow")], seen)
    monkeypatch.setattr(stt, "RATE_WAIT_MAX", 0.01)
    assert await stt.transcribe_ex(b"abc") == ("", -1)
    assert stt.last_error == "rate" and stt.openai_error == "rate"


@pytest.mark.asyncio
async def test_diag_openai_stt(monkeypatch):
    from config import settings
    from services import diag

    monkeypatch.setattr(settings, "stt_openai_api_key", "")
    assert await diag.check_stt_openai() == ""
    monkeypatch.setattr(settings, "stt_openai_api_key", "sk-ant-oops")
    assert "OpenAI kaliti emas" in await diag.check_stt_openai()

    monkeypatch.setattr(settings, "stt_openai_api_key", "sk-good")
    responses = [httpx.Response(200, json={"data": [{"id": "gpt-4o-transcribe"}, {"id": "whisper-1"}]}), httpx.Response(401, text="no")]

    def transport(request: httpx.Request):
        return responses.pop(0)

    class Client(httpx.AsyncClient):
        def __init__(self, **kw):
            kw.pop("timeout", None)
            super().__init__(transport=httpx.MockTransport(transport))

    monkeypatch.setattr(diag.httpx, "AsyncClient", Client)
    stt.openai_error = ""
    line = await diag.check_stt_openai()
    assert line.startswith("✅") and "asosiy" in line and "gpt-4o-transcribe" in line
    assert "rad etildi" in await diag.check_stt_openai()
    # Groq kaliti bo'sh, OpenAI bor → zaxira yo'q ogohlantirishi
    monkeypatch.setattr(settings, "stt_api_key", "")
    assert "zaxira yo'q" in await diag.check_stt()
