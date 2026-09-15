"""K17.3 — AI ustoz xavfsizlik tarmog'i: sarf hisobi ($), admin ogohlantirishlari,
STT xato holati, `/ustoz` hisoboti."""

from datetime import timedelta

import httpx
import pytest

from db.models import AiUsage, MockResult, PaymentRequest, TutorTurn, utcnow
from services import ai_usage, alerts, tutor


# ── Sarf hisobi ──


def test_cost_usd_matches_haiku_prices():
    assert ai_usage.cost_usd({"in": 1_000_000}) == pytest.approx(1.00)
    assert ai_usage.cost_usd({"out": 1_000_000}) == pytest.approx(5.00)
    assert ai_usage.cost_usd({"cache_read": 1_000_000}) == pytest.approx(0.10)
    assert ai_usage.cost_usd({"cache_write": 1_000_000}) == pytest.approx(1.25)
    # Odatiy cache'langan turn: ~$0.003
    turn = {"in": 300, "out": 250, "cache_read": 4500, "cache_write": 0}
    assert 0.001 < ai_usage.cost_usd(turn) < 0.004
    assert ai_usage.cost_usd({}) == 0


def test_usage_of_handles_missing_fields():
    class U:
        input_tokens = 12
        output_tokens = 3
        cache_read_input_tokens = None
        cache_creation_input_tokens = None

    class R:
        usage = U()

    assert ai_usage.usage_of(R()) == {"in": 12, "out": 3, "cache_read": 0, "cache_write": 0}
    assert ai_usage.usage_of(object()) == {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0}


@pytest.mark.asyncio
async def test_record_and_summary_by_feature(session, make_user):
    u = await make_user()
    ai_usage.record(session, "tutor", {"in": 100, "out": 50, "cache_read": 4000}, u.id)
    ai_usage.record(session, "tutor", {"in": 100, "out": 50, "cache_read": 4000}, u.id)
    ai_usage.record(session, "onboarding", {"in": 2000, "out": 1500}, u.id)
    await session.commit()

    s = await ai_usage.summary(session)
    assert s["calls"] == 3
    assert s["by"]["tutor"]["calls"] == 2
    assert s["by"]["tutor"]["usage"]["cache_read"] == 8000
    assert s["usage"]["in"] == 2200 and s["usage"]["out"] == 1600
    assert s["cost"] == pytest.approx(
        ai_usage.cost_usd({"in": 2200, "out": 1600, "cache_read": 8000})
    )
    # `since` filtri — kelajakdagi vaqtdan boshlab hech narsa yo'q
    empty = await ai_usage.summary(session, utcnow() + timedelta(minutes=1))
    assert empty["calls"] == 0 and empty["cost"] == 0 and empty["by"] == {}


# ── Xato tasnifi ──


@pytest.mark.parametrize(
    "msg, kind",
    [
        ("Your credit balance is too low to access the Anthropic API.", "credit"),
        ("authentication_error: invalid x-api-key", "auth"),
        ("rate_limit_error: too many requests", "rate"),
        ("Connection reset by peer", "other"),
    ],
)
def test_classify_kinds(msg, kind):
    k, text = tutor.classify(RuntimeError(msg))
    assert k == kind and text


def test_unavailable_carries_kind():
    e = tutor.TutorUnavailable("x", "credit")
    assert e.kind == "credit" and e.message_uz == "x"
    assert tutor.TutorUnavailable("y").kind == "other"


# ── Admin ogohlantirishlari ──


class FakeBot:
    def __init__(self, fail: bool = False):
        self.sent: list[tuple[int, str]] = []
        self.fail = fail

    async def send_message(self, chat_id, text, **kw):
        if self.fail:
            raise RuntimeError("telegram down")
        self.sent.append((chat_id, text))


@pytest.fixture(autouse=True)
def _reset_alerts():
    alerts.reset()
    yield
    alerts.reset()


@pytest.mark.asyncio
async def test_alert_once_per_day(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 777)
    bot = FakeBot()
    assert await alerts.notify(bot, "credit") is True
    assert await alerts.notify(bot, "credit") is False, "kuniga bir marta"
    # Boshqa tur — alohida hisob
    assert await alerts.notify(bot, "stt_auth") is True
    assert [c for c, _ in bot.sent] == [777, 777]
    assert "kredit" in bot.sent[0][1] and "gsk_" in bot.sent[1][1]
    assert set(alerts.last_sent()) == {"credit", "stt_auth"}


@pytest.mark.asyncio
async def test_alert_silent_without_admin_or_bot(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 0)
    assert await alerts.notify(FakeBot(), "credit") is False
    monkeypatch.setattr(settings, "admin_id", 5)
    assert await alerts.notify(None, "credit") is False
    assert await alerts.notify(FakeBot(), "nomalum") is False


@pytest.mark.asyncio
async def test_alert_retries_after_send_failure(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 5)
    assert await alerts.notify(FakeBot(fail=True), "auth") is False
    ok = FakeBot()
    assert await alerts.notify(ok, "auth") is True, "yuborilmagan bo'lsa qayta uriniladi"
    assert "ANTHROPIC_API_KEY" in ok.sent[0][1]


@pytest.mark.asyncio
async def test_alert_fire_schedules_task(monkeypatch):
    import asyncio

    from config import settings

    monkeypatch.setattr(settings, "admin_id", 5)
    bot = FakeBot()
    alerts.fire(bot, "stt_down", "http:503")
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(bot.sent) == 1 and "http:503" in bot.sent[0][1]


@pytest.mark.asyncio
async def test_reply_credit_error_kind(monkeypatch):
    """Anthropic kredit xatosi → TutorUnavailable(kind='credit')."""
    import anthropic

    from config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "test")
    err = {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": "Your credit balance is too low to access the Anthropic API.",
        },
    }

    def transport(request: httpx.Request):
        return httpx.Response(400, json=err)

    orig = anthropic.AsyncAnthropic

    class Patched(orig):
        def __init__(self, **kw):
            super().__init__(
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)), **kw
            )

    monkeypatch.setattr(anthropic, "AsyncAnthropic", Patched)
    with pytest.raises(tutor.TutorUnavailable) as ei:
        await tutor.reply(name="N", level="A0", topic_id="oila", history=[], known=[])
    assert ei.value.kind == "credit"


# ── STT xato holati ──


@pytest.mark.asyncio
async def test_stt_last_error_auth_and_ok(monkeypatch):
    from config import settings
    from services import stt

    monkeypatch.setattr(settings, "stt_api_key", "gsk_test")
    responses = [httpx.Response(401, json={"error": "invalid api key"})]

    def transport(request: httpx.Request):
        return responses.pop(0)

    class Client(httpx.AsyncClient):
        def __init__(self, **kw):
            kw.pop("timeout", None)
            super().__init__(transport=httpx.MockTransport(transport))

    monkeypatch.setattr(stt.httpx, "AsyncClient", Client)
    assert await stt.transcribe(b"abc") == ""
    assert stt.last_error == "auth"

    responses.append(httpx.Response(200, json={"text": " مرحبا "}))
    assert await stt.transcribe(b"abc") == "مرحبا"
    assert stt.last_error == ""

    responses.append(httpx.Response(503, text="down"))
    assert await stt.transcribe(b"abc") == ""
    assert stt.last_error == "http:503"


# ── /ustoz hisoboti ──


@pytest.mark.asyncio
async def test_tutor_report_smoke(session, make_user, monkeypatch):
    from config import settings
    from services import admin

    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    monkeypatch.setattr(settings, "stt_api_key", "")
    u = await make_user(vip_until=utcnow() + timedelta(days=2))
    ai_usage.record(session, "tutor", {"in": 300, "out": 200, "cache_read": 4500}, u.id)
    ai_usage.record(session, "mock", {"in": 300, "out": 200, "cache_read": 4500}, u.id)
    session.add(TutorTurn(user_id=u.id, session_key="s1", mode="chat", voice=1))
    session.add(TutorTurn(user_id=u.id, session_key="s2", mode="mock", score=80))
    session.add(MockResult(user_id=u.id, mock_id="shifokor", score=80, session_key="s2"))
    session.add(
        PaymentRequest(
            user_id=u.id, plan="1oy", amount=40_000, status="approved", days=30,
            decided_at=utcnow(),
        )
    )
    session.add(PaymentRequest(user_id=u.id, plan="3oy", amount=100_000, status="pending"))
    await session.commit()

    text = await admin.tutor_report(session)
    assert "AI ustoz" in text
    assert "<b>2</b> chaqiruv" in text  # bugun 2 ta
    assert "💬 Suhbat 1" in text and "🎯 Mock imtihon 1" in text
    assert "Faol: <b>1</b> · 3 kun ichida tugaydi: 1" in text
    assert "Kutayotgan cheklar: <b>1</b>" in text
    assert "1 ta · <b>40 000</b> so'm" in text
    assert "STT_API_KEY bo'sh" in text
    assert f"VIP {settings.tutor_daily_turns}/kun" in text
    assert "Ogohlantirishlar: yo'q" in text


@pytest.mark.asyncio
async def test_tutor_report_empty_db(session):
    from services import admin

    text = await admin.tutor_report(session)
    assert "<b>0</b> chaqiruv" in text and "$0.00" in text


def test_default_daily_limit_is_30():
    from config import Settings

    assert Settings.model_fields["tutor_daily_turns"].default == 30


# ── API oqimi: /tutor/turn → 503 + admin ogohlantirish; 200 → sarf yoziladi ──

_REPLY = {
    "ar": "أَهْلًا",
    "translit": "ahlan",
    "uz": "salom",
    "correction_ok": True,
    "fixed_ar": "",
    "note_uz": "",
    "hint_uz": "",
    "new_words": [],
    "answer_uz": "",
    "done": False,
}


def _envelope(text: str, usage: dict) -> dict:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "m",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": usage,
    }


@pytest.fixture
def api_client(session, monkeypatch):
    """main.app + test sessiyasi + soxta bot; Anthropic javoblari `handlers`dan."""
    import json

    import anthropic

    from config import settings
    from db.session import get_session
    from main import app
    from services import tts
    from services.telegram_auth import get_current_user

    monkeypatch.setattr(settings, "anthropic_api_key", "test")
    monkeypatch.setattr(settings, "admin_id", 42)
    monkeypatch.setattr(tts, "schedule", lambda text, level: "")
    handlers: list = []

    def transport(request: httpx.Request):
        json.loads(request.content)
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
    try:
        yield app, handlers, state, bot
    finally:
        app.dependency_overrides.clear()
        del app.state.bot


async def _post_turn(app, **body):
    payload = {
        "session_key": "abcdefgh1234",
        "topic_id": "oila",
        "history": [],
        "voice": False,
        "mode": "chat",
        **body,
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as c:
        return await c.post("/api/v2/tutor/turn", json=payload)


@pytest.mark.asyncio
async def test_turn_credit_error_alerts_admin_once(api_client, session, make_user):
    import asyncio

    from sqlalchemy import func, select

    app, handlers, state, bot = api_client
    state["user"] = await make_user(vip_until=utcnow() + timedelta(days=5))
    err = httpx.Response(
        400,
        json={
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "Your credit balance is too low to access the Anthropic API.",
            },
        },
    )
    handlers.extend([err, err, err, err])  # 2 so'rov × (structured + JSON zaxira)

    r = await _post_turn(app)
    assert r.status_code == 503 and "band" in r.json()["detail"]
    r = await _post_turn(app)
    assert r.status_code == 503
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(bot.sent) == 1 and bot.sent[0][0] == 42, "kuniga bir marta"
    assert "krediti tugagan" in bot.sent[0][1]
    # Turn ham, sarf ham yozilmadi — o'quvchi limiti kuymaydi
    assert (await session.execute(select(func.count()).select_from(TutorTurn))).scalar_one() == 0
    assert (await session.execute(select(func.count()).select_from(AiUsage))).scalar_one() == 0


@pytest.mark.asyncio
async def test_turn_success_records_usage(api_client, session, make_user):
    import json

    from sqlalchemy import select

    app, handlers, state, bot = api_client
    state["user"] = await make_user(vip_until=utcnow() + timedelta(days=5))
    handlers.append(
        httpx.Response(
            200,
            json=_envelope(
                json.dumps(_REPLY, ensure_ascii=False),
                {"input_tokens": 320, "output_tokens": 180, "cache_read_input_tokens": 4400},
            ),
        )
    )
    r = await _post_turn(app, history=[{"role": "user", "content": "أهلا"}])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["usage"]["cache_read"] == 4400 and body["turns_left"] >= 0

    row = (await session.execute(select(AiUsage))).scalar_one()
    assert row.feature == "tutor" and row.user_id == state["user"].id
    assert (row.tokens_in, row.tokens_out, row.cache_read) == (320, 180, 4400)
    assert (await session.execute(select(TutorTurn))).scalar_one().mode == "chat"
    assert bot.sent == []
