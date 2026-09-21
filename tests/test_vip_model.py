"""K23.4 — VIP uchun kuchliroq model (TUTOR_VIP_MODEL): tanlash, narx, zaxira, API oqimi."""

import json
from datetime import timedelta

import httpx
import pytest

from db.models import AiUsage, utcnow
from services import ai_usage, tutor

SONNET = "claude-sonnet-5"


def test_model_for(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "tutor_vip_model", "")
    assert tutor.model_for(True) == settings.tutor_model
    assert tutor.model_for(False) == settings.tutor_model
    monkeypatch.setattr(settings, "tutor_vip_model", SONNET)
    assert tutor.model_for(True) == SONNET
    assert tutor.model_for(False) == settings.tutor_model, "bepul foydalanuvchi asosiy modelda qoladi"


def test_prices_by_model():
    assert ai_usage.cost_usd({"in": 1_000_000}, SONNET) == pytest.approx(2.00)
    assert ai_usage.cost_usd({"out": 1_000_000}, SONNET) == pytest.approx(10.00)
    assert ai_usage.cost_usd({"in": 1_000_000, "model": SONNET}) == pytest.approx(2.00), "usage ichidagi model ham yetarli"
    assert ai_usage.cost_usd({"in": 1_000_000}, "claude-haiku-4-5-20251001") == pytest.approx(1.00)
    assert ai_usage.cost_usd({"in": 1_000_000}, "nomalum-model") == pytest.approx(1.00), "noma'lum → Haiku narxi"
    assert ai_usage.short_model("claude-haiku-4-5-20251001") == "Haiku 4.5"
    assert ai_usage.short_model(SONNET) == "Sonnet 5"
    assert ai_usage.short_model("") == "?"


@pytest.mark.asyncio
async def test_summary_by_model(session, make_user):
    u = await make_user()
    ai_usage.record(session, "tutor", {"in": 1000, "out": 0, "model": SONNET}, u.id)
    ai_usage.record(session, "tutor", {"in": 1000, "out": 0, "model": "claude-haiku-4-5-20251001"}, u.id)
    ai_usage.record(session, "daily", {"in": 1000, "out": 0}, u.id)  # modelsiz (eski qator) → Haiku narxi
    await session.commit()

    s = await ai_usage.summary(session)
    assert s["calls"] == 3 and s["by"]["tutor"]["calls"] == 2
    assert s["by_model"][SONNET]["calls"] == 1 and s["by_model"][""]["calls"] == 1
    assert s["by_model"][SONNET]["cost"] == pytest.approx(0.002)
    assert s["by"]["tutor"]["cost"] == pytest.approx(0.003), "sonnet 0.002 + haiku 0.001"
    assert s["cost"] == pytest.approx(0.004)
    row = (await session.execute(__import__("sqlalchemy").select(AiUsage).where(AiUsage.model == SONNET))).scalar_one()
    assert row.feature == "tutor"


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


def _envelope(text: str, usage: dict | None = None) -> dict:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "m",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": usage or {"input_tokens": 10, "output_tokens": 5},
    }


def _patch_anthropic(monkeypatch, handler):
    import anthropic

    orig = anthropic.AsyncAnthropic

    class Patched(orig):
        def __init__(self, **kw):
            super().__init__(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), **kw)

    monkeypatch.setattr(anthropic, "AsyncAnthropic", Patched)


@pytest.mark.asyncio
async def test_call_falls_back_to_base_model(monkeypatch):
    """VIP modeli nomi xato (404) → structured + JSON urinishdan keyin asosiy model bilan davom."""
    from config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "test")
    monkeypatch.setattr(settings, "tutor_vip_model", "claude-yoq-model")
    models: list[str] = []

    def handler(request: httpx.Request):
        m = json.loads(request.content)["model"]
        models.append(m)
        if m == "claude-yoq-model":
            return httpx.Response(
                404, json={"type": "error", "error": {"type": "not_found_error", "message": "model: claude-yoq-model"}}
            )
        return httpx.Response(200, json=_envelope(json.dumps(_REPLY, ensure_ascii=False)))

    _patch_anthropic(monkeypatch, handler)
    out, usage = await tutor.reply(name="N", level="A0", topic_id="oila", history=[], known=[], vip=True)
    assert out.ar == "أَهْلًا"
    assert usage["model"] == settings.tutor_model, "sarf asosiy model bo'yicha"
    assert models[:2] == ["claude-yoq-model", "claude-yoq-model"] and models[-1] == settings.tutor_model


@pytest.mark.asyncio
async def test_call_uses_vip_model_and_records_it(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "test")
    monkeypatch.setattr(settings, "tutor_vip_model", SONNET)
    models: list[str] = []

    def handler(request: httpx.Request):
        models.append(json.loads(request.content)["model"])
        return httpx.Response(200, json=_envelope(json.dumps(_REPLY, ensure_ascii=False)))

    _patch_anthropic(monkeypatch, handler)
    _, usage = await tutor.reply(name="N", level="A0", topic_id="oila", history=[], known=[], vip=True)
    assert usage["model"] == SONNET and models == [SONNET]
    _, usage = await tutor.reply(name="N", level="A0", topic_id="oila", history=[], known=[], vip=False)
    assert usage["model"] == settings.tutor_model and models[-1] == settings.tutor_model


@pytest.mark.asyncio
async def test_turn_api_routes_vip_to_vip_model(session, make_user, monkeypatch):
    """/tutor/turn: VIP → TUTOR_VIP_MODEL, bepul → asosiy; ai_usage.model shunga mos."""
    from sqlalchemy import select

    from config import settings
    from db.session import get_session
    from main import app
    from services import tts
    from services.telegram_auth import get_current_user

    monkeypatch.setattr(settings, "anthropic_api_key", "test")
    monkeypatch.setattr(settings, "tutor_vip_model", SONNET)
    monkeypatch.setattr(tts, "schedule", lambda text, level: "")
    models: list[str] = []

    def handler(request: httpx.Request):
        models.append(json.loads(request.content)["model"])
        return httpx.Response(200, json=_envelope(json.dumps(_REPLY, ensure_ascii=False)))

    _patch_anthropic(monkeypatch, handler)

    async def _session():
        yield session

    state = {"user": await make_user(vip_until=utcnow() + timedelta(days=5))}
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    payload = {"session_key": "abcdefgh1234", "topic_id": "oila", "history": [], "voice": False, "mode": "chat"}
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/api/v2/tutor/turn", json=payload)
            assert r.status_code == 200, r.text
            info = (await c.get("/api/v2/tutor/topics")).json()
            assert info["vip_model"] == "Sonnet 5"
            state["user"] = await make_user()  # bepul
            r = await c.post("/api/v2/tutor/turn", json=payload)
            assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.clear()

    assert models == [SONNET, settings.tutor_model]
    rows = (await session.execute(select(AiUsage).order_by(AiUsage.id))).scalars().all()
    assert [r.model for r in rows] == [SONNET, settings.tutor_model]
