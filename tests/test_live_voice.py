"""K30 — jonli ovozli suhbat (services/live_voice.py, api/live.py): relay, narx, limitlar, tahlil, WebSocket."""

import asyncio
import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

from config import settings
from db.models import LiveSession, TutorMistake, User, XpLog, utcnow
from services import live_voice as lv

FRAME = b"\x01\x00" * 4800  # 0.3 s, 16 kHz PCM16


class FakeClient:
    """relay() uchun mijoz: skript — ("audio", bytes) | ("end", None) | ("disconnect", None) | predicate(sent) → kutish."""

    def __init__(self, script):
        self.script = list(script)
        self.sent: list[dict] = []

    async def recv(self):
        while self.script:
            item = self.script.pop(0)
            if callable(item):
                for _ in range(400):
                    if item(self.sent):
                        break
                    await asyncio.sleep(0.01)
                continue
            return item
        await asyncio.sleep(3600)

    async def send(self, payload):
        self.sent.append(payload)


def turns(n):
    return lambda sent: sum(1 for m in sent if m["type"] == "turn") >= n


@pytest.fixture
def fake_on(monkeypatch):
    monkeypatch.setattr(settings, "live_fake", True)
    monkeypatch.setattr(settings, "gemini_api_key", "")


# ── prompt va narx ──


def test_prompt_follows_level_topic_and_words():
    p = lv.system_prompt(name="Ali", level="a0", topic={"title_uz": "Tanishish", "goal": "intro", "role": "a classmate"},
                         known=[{"ar": f"w{i}", "uz": "x"} for i in range(200)])
    assert "Name: Ali" in p and "Level: A0" in p and "max 4 Arabic words" in p and "Topic: Tanishish" in p
    assert "w79 (x)" in p and "w80 (x)" not in p, "so'zlar ro'yxati qisqa (prompt arzon)"
    assert "Uzbek" in p and "Never use English" in p
    assert "Level: A0" in lv.system_prompt(name="", level="Z9", topic={}, known=[]), "noma'lum daraja → A0"


def test_cost_and_usage_parsing():
    from google.genai import types

    assert lv.cost_usd({"audio_in": 1500, "audio_out": 1500, "text_in": 0, "text_out": 0}) == pytest.approx(0.0225)
    meta = types.UsageMetadata(
        prompt_token_count=1300,
        response_token_count=500,
        prompt_tokens_details=[
            types.ModalityTokenCount(modality="AUDIO", token_count=1000),
            types.ModalityTokenCount(modality="TEXT", token_count=200),
        ],
        response_tokens_details=[types.ModalityTokenCount(modality="AUDIO", token_count=500)],
    )
    u = lv.usage_from(meta)
    assert u == {"audio_in": 1100, "audio_out": 500, "text_in": 200, "text_out": 0}, "tafsilotsiz 100 token — audio narxida"
    assert lv.estimate_usage(60, 30) == {"audio_in": 1500, "audio_out": 750, "text_in": 0, "text_out": 0}


def test_events_from_sdk_message():
    from google.genai import types

    msg = types.LiveServerMessage(
        server_content=types.LiveServerContent(
            model_turn=types.Content(parts=[types.Part(inline_data=types.Blob(data=b"\x00\x01", mime_type="audio/pcm"))]),
            input_transcription=types.Transcription(text="ana bixayr"),
            output_transcription=types.Transcription(text="مَرْحَبًا"),
            turn_complete=True,
        ),
        usage_metadata=types.UsageMetadata(prompt_token_count=10, response_token_count=5),
    )
    evs = lv._events_from(msg)
    assert [e.kind for e in evs] == ["audio", "in", "out", "turn", "usage"]
    assert evs[0].data == b"\x00\x01" and evs[1].text == "ana bixayr"
    assert lv._events_from(types.LiveServerMessage(go_away=types.LiveServerGoAway()))[0].kind == "go_away"


def test_gemini_config_shape_is_accepted_by_sdk():
    """SDK konfiguratsiyani o'z tipiga o'gira oladi (maydon nomlari to'g'ri)."""
    from google.genai import types

    cfg = types.LiveConnectConfig(**lv.GeminiLive("sys").config())
    assert cfg.response_modalities == [types.Modality.AUDIO]
    assert cfg.speech_config.voice_config.prebuilt_voice_config.voice_name == settings.live_voice
    assert cfg.realtime_input_config.automatic_activity_detection.end_of_speech_sensitivity == types.EndSensitivity.END_SENSITIVITY_LOW


# ── relay ──


@pytest.mark.asyncio
async def test_relay_forwards_audio_both_ways_and_builds_transcript():
    live = lv.FakeLive("sys")
    client = FakeClient([turns(1), *[("audio", FRAME)] * 4, turns(2), ("end", None)])
    res = await lv.relay(client, live, max_seconds=10, idle_seconds=10, tick=0.05)
    assert res.reason == "user"
    assert live.texts == [lv.START_TEXT], "ustoz birinchi bo'lib salomlashadi"
    assert b"".join(live.received) == FRAME * 4 and res.in_bytes == len(FRAME) * 4
    kinds = [m["type"] for m in client.sent]
    assert "audio" in kinds and "in" in kinds and "out" in kinds and kinds.count("turn") == 2
    assert [t["role"] for t in res.transcript] == ["model", "user", "model"] and res.user_turns == 1
    assert res.usage_reported and res.usage["audio_in"] == 60


@pytest.mark.asyncio
async def test_relay_ends_on_idle_time_disconnect():
    res = await lv.relay(FakeClient([]), lv.FakeLive("s"), max_seconds=10, idle_seconds=0.3, tick=0.05)
    assert res.reason == "idle" and res.seconds < 2
    res = await lv.relay(FakeClient([]), lv.FakeLive("s"), max_seconds=0.3, idle_seconds=10, tick=0.05)
    assert res.reason == "time"
    res = await lv.relay(FakeClient([("disconnect", None)]), lv.FakeLive("s"), max_seconds=10, idle_seconds=10, tick=0.05)
    assert res.reason == "disconnect"


class BrokenLive(lv.FakeLive):
    async def events(self):
        yield lv.Event("out", text="سَلَام")
        raise RuntimeError("1011 internal")


class GoAwayLive(lv.FakeLive):
    async def send_text(self, text):
        await self.q.put(lv.Event("audio", data=b"\x00\x00" * 24000))  # 1 s ovoz, usage yo'q
        await self.q.put(lv.Event("go_away"))


@pytest.mark.asyncio
async def test_relay_error_and_go_away_and_usage_estimate():
    res = await lv.relay(FakeClient([]), BrokenLive("s"), max_seconds=10, idle_seconds=10, tick=0.05)
    assert res.reason == "error" and "1011" in res.error and res.transcript == [{"role": "model", "text": "سَلَام"}]
    res = await lv.relay(FakeClient([]), GoAwayLive("s"), max_seconds=10, idle_seconds=10, tick=0.05)
    assert res.reason == "time" and not res.usage_reported
    assert res.final_usage()["audio_out"] == 25, "usage kelmasa — davomiylikdan taxmin (1 s = 25 token)"


# ── DB: saqlash, limit, sarf ──


@pytest.mark.asyncio
async def test_save_allowance_spend_report(session, make_user, monkeypatch):
    u = await make_user("Ali")
    await session.commit()
    res = lv.RelayResult(reason="user", seconds=95.4, user_turns=3, transcript=[{"role": "user", "text": "x" * 30_000}, {"role": "model", "text": "ok"}])
    res.usage_reported = True
    res.usage = {"audio_in": 1500, "audio_out": 1500, "text_in": 0, "text_out": 0}
    row = await lv.save(session, u, "erkin", "A1", res)
    assert row.seconds == 95 and row.cost_usd == pytest.approx(0.0225) and row.reason == "user"
    assert len(row.transcript) <= lv.TRANSCRIPT_MAX_CHARS and json.loads(row.transcript)[-1]["text"] == "ok"

    assert await lv.allowance(session, u) is None, "standart: cheklovsiz"
    monkeypatch.setattr(settings, "live_free_seconds_day", 120)
    assert await lv.allowance(session, u) == 25
    monkeypatch.setattr(settings, "live_vip_seconds_month", 3600)
    u.vip_until = utcnow() + timedelta(days=5)
    assert await lv.allowance(session, u) == 3600 - 95
    assert await lv.spent_today(session) == pytest.approx(0.0225)
    rep = await lv.report(session)
    assert rep["today"] == {"sessions": 1, "minutes": 1.6, "cost": pytest.approx(0.0225), "users": 1}


# ── tahlil (Claude) ──


@pytest.mark.asyncio
async def test_review_saves_mistakes_and_xp_once(session, make_user, monkeypatch):
    from services import tutor

    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    calls = []

    async def fake_call(system, msgs, schema, model=None, max_tokens=0):
        calls.append(msgs[0]["content"])
        return schema(
            summary_uz="Yaxshi!",
            mistakes=[lv.LiveMistake(said="انا ذهب", fixed_ar="أَنَا ذَهَبْتُ", note_uz="Fe'l shaxsi: ـتُ")],
            words=[lv.LiveWord(ar="ذَهَبَ", translit="dhahaba", uz="bordi")],
        ), {"in": 100, "out": 50, "cache_read": 0, "cache_write": 0, "model": settings.tutor_model}

    monkeypatch.setattr(tutor, "_call", fake_call)
    u = await make_user("Ali")
    transcript = [{"role": "model", "text": "مرحبا"}, {"role": "user", "text": "انا ذهب"}] * 3
    row = LiveSession(user_id=u.id, topic="erkin", seconds=180, user_turns=3, transcript=json.dumps(transcript, ensure_ascii=False))
    session.add(row)
    await session.commit()

    r = await lv.review(session, row, u)
    assert r["summary_uz"] == "Yaxshi!" and r["words"][0]["ar"] == "ذَهَبَ" and r["xp"] == 9
    assert "LEARNER: انا ذهب" in calls[0] and "TUTOR: مرحبا" in calls[0]
    mistakes = (await session.execute(TutorMistake.__table__.select())).all()
    assert len(mistakes) == 1 and mistakes[0].kind == "live"
    again = await lv.review(session, row, u)
    assert again == r and len(calls) == 1, "ikkinchi marta Claude chaqirilmaydi"
    xp_rows = (await session.execute(XpLog.__table__.select().where(XpLog.source == f"live:{row.id}"))).all()
    assert len(xp_rows) == 1


@pytest.mark.asyncio
async def test_review_short_session_skips_ai(session, make_user, monkeypatch):
    from services import tutor

    async def boom(*a, **k):
        raise AssertionError("chaqirilmasligi kerak")

    monkeypatch.setattr(tutor, "_call", boom)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    u = await make_user("Qisqa")
    row = LiveSession(user_id=u.id, seconds=20, user_turns=1, transcript="[]")
    session.add(row)
    await session.commit()
    r = await lv.review(session, row, u)
    assert "juda qisqa" in r["summary_uz"] and r["xp"] == 0


# ── WebSocket endpoint ──


class FakeWS:
    def __init__(self, first, frames=()):
        self.first = first
        self.frames: asyncio.Queue = asyncio.Queue()
        for f in frames:
            self.frames.put_nowait(f)
        self.sent: list[dict] = []
        self.closed = None
        self.app = SimpleNamespace(state=SimpleNamespace(bot=None))

    async def accept(self):
        pass

    async def receive_json(self):
        return self.first

    async def receive(self):
        item = await self.frames.get()
        if callable(item):
            for _ in range(400):
                if item(self.sent):
                    break
                await asyncio.sleep(0.01)
            return await self.receive()
        return item

    async def send_json(self, payload):
        self.sent.append(payload)

    async def close(self, code=1000):
        self.closed = code


@pytest.fixture
def ws_env(session_factory, monkeypatch, fake_on):
    from api import live as live_api

    monkeypatch.setattr(live_api, "sessions", session_factory)
    monkeypatch.setattr(settings, "bot_token", "")
    monkeypatch.setattr(settings, "dev_auth", True)  # dev foydalanuvchi (tg_id=1)
    fired = []
    monkeypatch.setattr(live_api.alerts, "fire", lambda bot, kind, detail="": fired.append((kind, detail)))
    return live_api, fired


@pytest.mark.asyncio
async def test_ws_full_session_saved(ws_env, session_factory, monkeypatch):
    live_api, fired = ws_env
    monkeypatch.setattr(settings, "live_daily_budget_usd", 0.0000001)
    frames = [turns(1)] + [{"type": "websocket.receive", "bytes": FRAME}] * 4 + [turns(2), {"type": "websocket.receive", "text": '{"type": "end"}'}]
    ws = FakeWS({"type": "start", "init_data": "", "topic_id": "erkin"}, frames)
    await live_api.live_ws(ws)
    kinds = [m["type"] for m in ws.sent]
    assert kinds[0] == "ready" and kinds[-1] == "end" and "audio" in kinds
    end = ws.sent[-1]
    assert end["reason"] == "user" and end["session_id"] > 0 and ws.closed == 1000
    async with session_factory() as s:
        row = await s.get(LiveSession, end["session_id"])
        assert row.user_turns == 1 and row.model == "fake" and row.cost_usd > 0
        assert (await s.get(User, row.user_id)).tg_id == 1
    assert fired == [("live_budget", fired[0][1])], "kunlik chegaradan oshdi — adminga ogohlantirish"


@pytest.mark.asyncio
async def test_ws_rejects_bad_auth_off_and_limit(ws_env, session_factory, monkeypatch):
    live_api, _ = ws_env
    ws = FakeWS({"type": "hello"})
    await live_api.live_ws(ws)
    assert ws.closed == 4001 and ws.sent == []

    monkeypatch.setattr(settings, "dev_auth", False)
    monkeypatch.setattr(settings, "bot_token", "123:abc")
    ws = FakeWS({"type": "start", "init_data": "user=%7B%22id%22%3A5%7D&hash=bad"})
    await live_api.live_ws(ws)
    assert ws.sent[0]["code"] == "auth" and ws.closed == 4003

    monkeypatch.setattr(settings, "dev_auth", True)
    monkeypatch.setattr(settings, "bot_token", "")
    monkeypatch.setattr(settings, "live_fake", False)  # kalit ham yo'q
    ws = FakeWS({"type": "start"})
    await live_api.live_ws(ws)
    assert ws.sent[0]["code"] == "off" and ws.closed == 4004

    monkeypatch.setattr(settings, "live_fake", True)
    monkeypatch.setattr(settings, "live_free_seconds_day", 60)
    from sqlalchemy import select

    async with session_factory() as s:
        u = (await s.execute(select(User).where(User.tg_id == 1))).scalar_one()  # «off» qadamida yaratilgan dev foydalanuvchi
        s.add(LiveSession(user_id=u.id, seconds=60))
        await s.commit()
    ws = FakeWS({"type": "start"})
    await live_api.live_ws(ws)
    assert ws.sent[0]["code"] == "limit" and ws.closed == 4002


@pytest.mark.asyncio
async def test_ws_gemini_unavailable_alerts_admin(ws_env, monkeypatch):
    live_api, fired = ws_env

    class Down:
        def __init__(self, system):
            pass

        async def __aenter__(self):
            raise lv.LiveUnavailable("Jonli suhbat hozircha ishlamayapti.", "auth")

        async def __aexit__(self, *a):
            pass

    monkeypatch.setattr(lv, "open_live", lambda system: Down(system))
    ws = FakeWS({"type": "start"})
    await live_api.live_ws(ws)
    assert ws.sent[-1]["code"] == "unavailable" and fired[0][0] == "live_auth"


@pytest.mark.asyncio
async def test_review_endpoint_only_own_session(session, make_user):
    from fastapi import HTTPException

    from api.live import LiveReviewBody, live_review

    a, b = await make_user("A"), await make_user("B")
    row = LiveSession(user_id=a.id, seconds=10, user_turns=0, transcript="[]")
    session.add(row)
    await session.commit()
    with pytest.raises(HTTPException) as e:
        await live_review(LiveReviewBody(session_id=row.id), b, session)
    assert e.value.status_code == 404
    r = await live_review(LiveReviewBody(session_id=row.id), a, session)
    assert r["transcript"] == [] and "qisqa" in r["summary_uz"]


# ── /tekshir ──


@pytest.mark.asyncio
async def test_diag_live_states(monkeypatch):
    from services import diag

    monkeypatch.setattr(settings, "live_fake", False)
    monkeypatch.setattr(settings, "gemini_api_key", "")
    assert (await diag.check_live()).startswith("⚪")
    monkeypatch.setattr(settings, "live_fake", True)
    assert (await diag.check_live()).startswith("⚠️")
    monkeypatch.setattr(settings, "live_fake", False)

    probe = {"ok": False, "status": 400, "error": "API key not valid. Please pass a valid API key.", "live_models": []}

    async def fake_probe():
        return probe

    monkeypatch.setattr(lv, "probe_key", fake_probe)
    # 1) kalit noto'g'ri (shakli ham boshqa) — aniq sabab va yo'l
    monkeypatch.setattr(settings, "gemini_api_key", "GOCSPX-oauth-secret")
    line = await diag.check_live()
    assert line.startswith("❌") and "rad etdi" in line and "API key not valid" in line and "«GOC…»" in line
    assert "Create API key" in line

    # 2) kalit ishlaydi, model nomi yo'q — mavjudlari taklif qilinadi
    monkeypatch.setattr(settings, "gemini_api_key", '"AQ.Ab8Good"')  # qo'shtirnoq bilan ko'chirilgan
    assert lv.api_key() == "AQ.Ab8Good"
    probe.update(ok=True, status=200, error="", live_models=["gemini-live-x", "gemini-live-y"])
    monkeypatch.setattr(settings, "live_model", "gemini-3.8-live")
    line = await diag.check_live()
    assert line.startswith("❌") and "LIVE_MODEL=gemini-3.8-live bu kalitda yo'q" in line and "LIVE_MODEL=gemini-live-x" in line

    # 3) REST ishlaydi, WebSocket ikkala usulda ham rad etadi (kalit ham, vaqtinchalik token ham)
    monkeypatch.setattr(settings, "live_model", "gemini-live-x")
    tried = []

    async def denied(mode):
        tried.append(mode)
        return "ConnectionClosedError(1008 Request had invalid authentication credentials)"

    monkeypatch.setattr(lv, "try_connect", denied)
    line = await diag.check_live()
    assert line.startswith("❌") and "REST'da ishlaydi" in line and "bilan boshlanadi" not in line, "AQ. — to'g'ri shakl"
    assert tried == ["key", "token"], "kalit rad etilsa token yo'li ham sinaladi"

    # 4) hammasi joyida
    async def ok(mode):
        return ""

    monkeypatch.setattr(lv, "try_connect", ok)
    line = await diag.check_live()
    assert line.startswith("✅") and "token" not in line


@pytest.mark.asyncio
async def test_diag_live_reason_codes_billing_and_token_fallback(monkeypatch):
    """2026-10-03: «AQ.» kalit hali ham 401 — /tekshir Google sabab kodini, to'lov qaysi loyihada bo'lishi kerakligini
    va jonli ulanishning qaysi usuli ishlaganini ko'rsatadi."""
    from services import diag

    monkeypatch.setattr(settings, "live_fake", False)
    monkeypatch.setattr(settings, "gemini_api_key", "AQ.Ab8" + "x" * 40)
    monkeypatch.setattr(settings, "live_model", "gemini-3.8-live")
    probe = {"ok": False, "status": 401, "error": "Request had invalid authentication credentials.",
             "reason": "ACCESS_TOKEN_TYPE_UNSUPPORTED", "live_models": [], "gen_models": []}

    async def fake_probe():
        return probe

    monkeypatch.setattr(lv, "probe_key", fake_probe)
    # 1) REST 401 + sabab kodi → kalit/loyiha yo'riqnomasi; kalitning o'zi chiqmaydi, faqat shakli
    line = await diag.check_live()
    assert line.startswith("❌") and "401 ACCESS_TOKEN_TYPE_UNSUPPORTED" in line and "to'lov qilingan loyiha" in line
    assert "to'liq ko'chirilmagan yoki o'chirilgan kalitda ham" in line, "Google bu xatoni noto'g'ri kalitga ham beradi"
    assert "«AQ.…», 46 belgi" in line and "x" * 10 not in line
    assert "to'liq ko'chirilmagan bo'lishi mumkin" in line, "haqiqiy AQ. kalit 53 belgi"
    monkeypatch.setattr(settings, "gemini_api_key", "AQ.Ab8" + "x" * 47)
    assert "to'liq ko'chirilmagan bo'lishi mumkin" not in await diag.check_live()
    monkeypatch.setattr(settings, "gemini_api_key", "AQ.Ab8" + "x" * 40)

    # 2) API o'chiq — aniq yo'l
    probe.update(status=403, reason="SERVICE_DISABLED", error="Generative Language API has not been used")
    assert "Generative Language API» → Enable" in await diag.check_live()

    # 3) ro'yxat ochiq, lekin javob olish rad etiladi → billing
    probe.update(ok=True, status=200, error="", reason="", live_models=["gemini-3.8-live"],
                 gen_models=["gemini-3.6-flash", "gemini-3.8-flash-tts"])
    gen_calls = []

    async def gen_denied(model):
        gen_calls.append(model)
        return {"ok": False, "status": 403, "error": "Your project has been denied access.", "reason": "PERMISSION_DENIED"}

    monkeypatch.setattr(lv, "probe_generate", gen_denied)
    line = await diag.check_live()
    assert gen_calls == ["gemini-3.6-flash"] and "javob bermadi" in line and "billing" in line

    # 4) kalit bilan WebSocket rad etadi, token bilan ishlaydi → ✅ (usul eslab qolinadi)
    async def gen_ok(model):
        return {"ok": True, "status": 200, "error": "", "reason": ""}

    async def token_only(mode):
        return "" if mode == "token" else "1008 Request had invalid authentication credentials"

    monkeypatch.setattr(lv, "probe_generate", gen_ok)
    monkeypatch.setattr(lv, "try_connect", token_only)
    monkeypatch.setitem(lv.AUTH_MODE, "mode", "key")
    line = await diag.check_live()
    assert line.startswith("✅") and "vaqtinchalik token" in line and lv.AUTH_MODE["mode"] == "token"

    # 5) loyihaga Live yopiq (billing'siz) — token sinalmaydi, billing yo'riqnomasi
    tried = []

    async def project_denied(mode):
        tried.append(mode)
        return "1008 Your project has been denied access. Please contact support."

    monkeypatch.setattr(lv, "try_connect", project_denied)
    line = await diag.check_live()
    assert tried == ["key"] and "loyihaga jonli ulanish yopiq" in line and "billing" in line


def test_google_error_reason_and_classification():
    class R:
        def __init__(self, body):
            self.body = body
            self.text = str(body)

        def json(self):
            return self.body

    body = {"error": {"code": 401, "message": "Request had invalid authentication credentials.", "status": "UNAUTHENTICATED",
                      "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "ACCESS_TOKEN_TYPE_UNSUPPORTED"}]}}
    assert lv._google_error(R(body)) == ("Request had invalid authentication credentials.", "ACCESS_TOKEN_TYPE_UNSUPPORTED")
    assert lv._google_error(R({"error": {"message": "x", "status": "PERMISSION_DENIED"}}))[1] == "PERMISSION_DENIED"
    assert lv.classify_error("1008 Request had invalid authentication credentials") == "auth"
    assert lv.classify_error("1008 Your project has been denied access") == "project"
    assert lv.classify_error("1008 models/gemini-x is not found for API version v1beta") == "model"
    assert lv.classify_error("TimeoutError()") == "down"
    assert lv.pick_text_model(["gemini-3.8-flash-tts", "gemini-3.5-flash", "gemini-3.6-flash"]) == "gemini-3.6-flash"
    assert lv.pick_text_model(["gemini-9-flash-live", "gemini-9-flash"]) == "gemini-9-flash"


class _Cm:
    async def __aexit__(self, *a):
        return None


@pytest.mark.asyncio
async def test_gemini_live_falls_back_to_ephemeral_token(monkeypatch):
    monkeypatch.setitem(lv.AUTH_MODE, "mode", "key")
    calls = []

    async def fake_open(mode, config):
        calls.append(mode)
        if mode == "key":
            raise RuntimeError("1008 Request had invalid authentication credentials. Expected OAuth 2 access token")
        return _Cm(), object()

    monkeypatch.setattr(lv, "open_session", fake_open)
    async with lv.GeminiLive("sys") as g:
        assert g.mode == "token"
    assert calls == ["key", "token"] and lv.AUTH_MODE["mode"] == "token"
    calls.clear()
    async with lv.GeminiLive("sys"):
        pass
    assert calls == ["token"], "ishlagan usul eslab qolinadi — keyingi suhbat darhol token bilan"


@pytest.mark.asyncio
async def test_gemini_live_no_token_retry_for_model_errors(monkeypatch):
    monkeypatch.setitem(lv.AUTH_MODE, "mode", "key")
    calls = []

    async def fake_open(mode, config):
        calls.append(mode)
        raise RuntimeError("1008 models/gemini-x is not found for API version v1beta")

    monkeypatch.setattr(lv, "open_session", fake_open)
    with pytest.raises(lv.LiveUnavailable) as e:
        async with lv.GeminiLive("sys"):
            pass
    assert calls == ["key"] and e.value.kind == "down"


def test_auth_error_detection_matches_google_websocket_message():
    """Serverdagi haqiqiy xato (2026-10-02): «1008 None. Request had invalid authentication credentials…» — bu kalit
    muammosi, «model nomi» emas."""
    assert lv.is_auth_error("ConnectionClosedError(1008 None. Request had invalid authentication credentials. Expected OAuth 2")
    assert lv.is_auth_error("API key not valid")
    assert not lv.is_auth_error("1008 models/gemini-x is not found for API version v1beta")


# ── suiiste'molga qarshi ──


@pytest.mark.asyncio
async def test_relay_drops_oversized_and_too_fast_audio():
    live = lv.FakeLive("s")
    live.HEARD_BYTES = 10**9  # javob bermasin — faqat qabul qilingan baytlar sanaladi
    big = b"\x00" * (lv.MAX_FRAME_BYTES + 2)
    flood = [("audio", FRAME)] * 40  # 12 s ovoz bir zumda (real vaqtdan ancha tez)
    res = await lv.relay(FakeClient([("audio", big), *flood, ("end", None)]), live, max_seconds=10, idle_seconds=10, tick=0.05)
    assert res.reason == "user"
    limit = (lv.RATE_BURST_SECONDS + 1) * lv.IN_RATE * 2 * lv.RATE_SLACK
    assert res.in_bytes <= limit and res.dropped_bytes >= len(big) + len(FRAME) * 20
    assert sum(len(b) for b in live.received) == res.in_bytes, "tashlangan ovoz Gemini'ga ketmaydi (pullik)"


@pytest.mark.asyncio
async def test_ws_one_call_per_user_and_global_cap(ws_env, monkeypatch):
    live_api, _ = ws_env
    live_api.ACTIVE.clear()
    live_api.ACTIVE.add(1)  # dev foydalanuvchining boshqa qo'ng'irog'i ochiq
    ws = FakeWS({"type": "start"})
    await live_api.live_ws(ws)
    assert ws.sent[0]["code"] == "busy" and ws.closed == 4005
    assert live_api.ACTIVE == {1}, "boshqa qo'ng'iroq yozuvi o'chirilmaydi"

    live_api.ACTIVE.clear()
    monkeypatch.setattr(live_api, "MAX_CONCURRENT", 2)
    live_api.ACTIVE.update({901, 902})
    ws = FakeWS({"type": "start"})
    await live_api.live_ws(ws)
    assert ws.sent[0]["code"] == "busy" and "band" in ws.sent[0]["detail"]

    live_api.ACTIVE.clear()
    ws = FakeWS({"type": "start"}, [{"type": "websocket.receive", "text": '{"type": "end"}'}])
    await live_api.live_ws(ws)
    assert ws.sent[-1]["type"] == "end" and live_api.ACTIVE == set(), "suhbat tugagach o'rin bo'shaydi"


@pytest.mark.asyncio
async def test_review_ai_unavailable_message(session, make_user, monkeypatch):
    from services import tutor

    async def down(*a, **k):
        raise tutor.TutorUnavailable("Ustoz hozircha band (server sozlanmoqda).", "auth")

    monkeypatch.setattr(tutor, "_call", down)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    u = await make_user("Band")
    row = LiveSession(user_id=u.id, seconds=120, user_turns=4, transcript='[{"role": "user", "text": "x"}]')
    session.add(row)
    await session.commit()
    r = await lv.review(session, row, u)
    assert "Tahlil hozircha tayyorlanmadi" in r["summary_uz"] and "Ustoz hozircha band" not in r["summary_uz"]
    assert r["xp"] > 0, "AI tahlili bo'lmasa ham suhbat uchun XP beriladi"
