"""K18.0 — /tekshir tizim tekshiruvi: kalitlar jonli (mock transport), TTS, DB,
sozlamalar, fon halqalari, hisobot yig'indisi, admin buyrug'i."""

import asyncio
from datetime import datetime

import httpx
import pytest

from services import diag


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    monkeypatch.setattr(settings, "stt_api_key", "gsk_test")
    monkeypatch.setattr(settings, "stt_base_url", "https://api.groq.com/openai/v1")
    monkeypatch.setattr(settings, "stt_model", "whisper-large-v3-turbo")


import anthropic as _anthropic

_ORIG_CLIENT = _anthropic.AsyncAnthropic  # bir test ichida qayta patch — asl klass saqlanadi


def _patch_anthropic(monkeypatch, response: httpx.Response):
    import anthropic

    orig = _ORIG_CLIENT

    class Patched(orig):
        def __init__(self, **kw):
            super().__init__(
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: response)), **kw
            )

    monkeypatch.setattr(anthropic, "AsyncAnthropic", Patched)


def _msg(text: str, usage=None) -> dict:
    return {
        "id": "m", "type": "message", "role": "assistant", "model": "m",
        "content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
        "stop_sequence": None, "usage": usage or {"input_tokens": 1, "output_tokens": 1},
    }


# ── Anthropic ──


@pytest.mark.asyncio
async def test_anthropic_ok_and_errors(monkeypatch):
    from config import settings

    _patch_anthropic(monkeypatch, httpx.Response(200, json=_msg("hi")))
    line = await diag.check_anthropic()
    assert line.startswith("✅") and settings.tutor_model in line

    err = {"type": "error", "error": {"type": "invalid_request_error", "message": "Your credit balance is too low"}}
    _patch_anthropic(monkeypatch, httpx.Response(400, json=err))
    line = await diag.check_anthropic()
    assert line.startswith("❌") and "kredit" in line and "Billing" in line

    err = {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
    _patch_anthropic(monkeypatch, httpx.Response(401, json=err))
    assert "rad etildi" in await diag.check_anthropic()

    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert (await diag.check_anthropic()).startswith("❌")
    monkeypatch.setattr(settings, "anthropic_api_key", "gsk_wrong")
    assert (await diag.check_anthropic()).startswith("⚠️")


# ── STT ──


_ORIG_HTTPX_CLIENT = httpx.AsyncClient


def _patch_httpx(monkeypatch, handler):
    class Client(_ORIG_HTTPX_CLIENT):
        def __init__(self, **kw):
            kw.pop("timeout", None)
            super().__init__(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(diag.httpx, "AsyncClient", Client)


@pytest.mark.asyncio
async def test_stt_checks(monkeypatch):
    from config import settings

    seen = {}

    def ok(request: httpx.Request):
        seen["auth"] = request.headers.get("Authorization")
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"data": [{"id": "whisper-large-v3-turbo"}, {"id": "llama"}]})

    _patch_httpx(monkeypatch, ok)
    line = await diag.check_stt()
    assert line.startswith("✅") and seen["auth"] == "Bearer gsk_test" and seen["url"].endswith("/models")

    monkeypatch.setattr(settings, "stt_model", "whisper-9")
    assert "ro'yxatda yo'q" in await diag.check_stt()

    _patch_httpx(monkeypatch, lambda r: httpx.Response(401, json={"error": "bad key"}))
    monkeypatch.setattr(settings, "stt_model", "whisper-large-v3-turbo")
    assert "rad etildi" in await diag.check_stt()

    # Anthropic kaliti Groq o'rnida — jonli so'rovsiz aniqlanadi
    monkeypatch.setattr(settings, "stt_api_key", "sk-ant-api03-xyz")
    line = await diag.check_stt()
    assert line.startswith("❌") and "Anthropic kaliti" in line and "gsk_" in line

    monkeypatch.setattr(settings, "stt_api_key", "")
    assert "bo'sh" in await diag.check_stt()

    def boom(request):
        raise httpx.ConnectError("no net")

    monkeypatch.setattr(settings, "stt_api_key", "gsk_x")
    _patch_httpx(monkeypatch, boom)
    assert "tarmoq" in await diag.check_stt()


# ── TTS ──


@pytest.mark.asyncio
async def test_tts_check(monkeypatch, tmp_path):
    from services import tts

    monkeypatch.setattr(tts, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(tts, "path_for", lambda key: tmp_path / f"{key}.mp3")

    async def fake_ok(text, level):
        (tmp_path / "abc.mp3").write_bytes(b"\x00" * 2048)
        return "abc"

    monkeypatch.setattr(tts, "synthesize", fake_ok)
    line = await diag.check_tts()
    assert line.startswith("✅") and "1 fayl" in line

    async def fake_fail(text, level):
        return ""

    monkeypatch.setattr(tts, "synthesize", fake_fail)
    assert (await diag.check_tts()).startswith("❌")


# ── DB ──


@pytest.mark.asyncio
async def test_db_check_against_test_engine(session, make_user, monkeypatch):
    from db import session as dbs

    await make_user()
    await session.commit()
    monkeypatch.setattr(dbs, "engine", session.bind)
    monkeypatch.setattr(dbs, "DB_PATH", str(session.bind.url).split("///")[-1])
    lines = await diag.check_db()
    assert lines[0].startswith("✅") and "kerakli" in lines[0]
    assert not any(line.startswith("❌") for line in lines)
    assert "1 foydalanuvchi" in lines[-1]

    # Jadval yo'qolgan bo'lsa — ❌
    monkeypatch.setattr(diag, "REQUIRED_TABLES", diag.REQUIRED_TABLES + ("yoq_jadval",))
    lines = await diag.check_db()
    assert any("yoq_jadval" in line and line.startswith("❌") for line in lines)


# ── Sozlamalar, fon halqalari, hisobot ──


def test_settings_lines(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 5)
    monkeypatch.setattr(settings, "bot_token", "t")
    monkeypatch.setattr(settings, "pay_card_number", "8600 1234 5678 9012")
    monkeypatch.setattr(settings, "pay_card_holder", "N. G.")
    monkeypatch.setattr(settings, "support_username", "@nbwvvy")
    lines = diag.check_settings()
    joined = "\n".join(lines)
    assert "…9012" in joined and "8600 1234" not in joined, "karta raqami to'liq chiqmasin"
    assert "@nbwvvy" in joined and not any(line.startswith("❌") for line in lines)

    monkeypatch.setattr(settings, "admin_id", 0)
    monkeypatch.setattr(settings, "pay_card_number", "")
    lines = diag.check_settings()
    assert sum(1 for line in lines if line.startswith("❌")) == 2


@pytest.mark.asyncio
async def test_tasks_check():
    diag._tasks.clear()
    assert diag.check_tasks()[0].startswith("⚠️")

    async def forever():
        await asyncio.sleep(3600)

    async def crash():
        raise RuntimeError("halqa yiqildi")

    alive = asyncio.create_task(forever())
    dead = asyncio.create_task(crash())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    diag.register_task("reminder", alive)
    diag.register_task("vip", dead)
    diag.register_task("none", None)
    lines = diag.check_tasks()
    assert any(line.startswith("✅") and "reminder" in line for line in lines)
    assert any(line.startswith("❌") and "vip" in line and "yiqildi" in line for line in lines)
    alive.cancel()
    diag._tasks.clear()


@pytest.mark.asyncio
async def test_run_all_summary_and_escaping(monkeypatch):
    async def a():
        return diag._bad("Anthropic: <xato>")

    async def s():
        return diag._ok("STT")

    async def t():
        return diag._warn("TTS sekin")

    async def d():
        return [diag._ok("DB")]

    monkeypatch.setattr(diag, "check_anthropic", a)
    monkeypatch.setattr(diag, "check_stt", s)
    monkeypatch.setattr(diag, "check_tts", t)
    monkeypatch.setattr(diag, "check_db", d)
    monkeypatch.setattr(diag, "check_disk", lambda: diag._ok("Disk"))
    monkeypatch.setattr(diag, "check_webapp", lambda: [diag._ok("Webapp")])
    monkeypatch.setattr(diag, "check_settings", lambda: [diag._ok("Sozlama")])
    monkeypatch.setattr(diag, "check_tasks", lambda: [diag._ok("Halqa")])
    monkeypatch.setattr(diag, "check_alerts", lambda: diag._ok("Ogoh"))
    text = await diag.run_all()
    assert "<b>Tizim tekshiruvi</b>" in text and "&lt;xato&gt;" in text
    assert "🔴 1 xato · 1 ogohlantirish" in text


# ── Bot buyrug'i ──


class FakeSession:
    def __init__(self):
        self.calls = []

    async def __call__(self, bot, method, timeout=None):
        self.calls.append(method)
        if type(method).__name__ == "SendMessage":
            from aiogram.types import Chat, Message

            return Message(
                message_id=9, date=datetime.now(), chat=Chat(id=method.chat_id, type="private"), text=method.text
            ).as_(bot)  # haqiqiy aiogram'dagidek bot'ga bog'langan — edit_text ishlaydi
        return None

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_tekshir_command(session_factory, monkeypatch):
    from aiogram import Bot, Dispatcher
    from aiogram.types import Chat, Message, Update, User as TgUser

    from bot import admin as mod
    from bot.admin import router as admin_router
    from config import settings

    monkeypatch.setattr(mod, "SessionLocal", session_factory)
    monkeypatch.setattr(settings, "admin_id", 777001)

    async def fake_run_all():
        return "🩺 <b>Tizim tekshiruvi</b>\n✅ hammasi"

    monkeypatch.setattr(diag, "run_all", fake_run_all)
    bot = Bot(token="42:TESTTOKEN")
    bot.session = FakeSession()
    dp = Dispatcher()
    dp.include_router(admin_router)
    try:
        def msg(text, uid):
            chat = Chat(id=uid, type="private")
            return Message(message_id=1, date=datetime.now(), chat=chat, from_user=TgUser(id=uid, is_bot=False, first_name="A"), text=text)

        await dp.feed_update(bot, Update(update_id=1, message=msg("/tekshir", 777001)))
        names = [type(m).__name__ for m in bot.session.calls]
        assert "SendMessage" in names and "EditMessageText" in names
        edit = next(m for m in bot.session.calls if type(m).__name__ == "EditMessageText")
        assert "hammasi" in edit.text and edit.parse_mode == "HTML"

        bot.session.calls.clear()
        await dp.feed_update(bot, Update(update_id=2, message=msg("/tekshir", 555)))
        assert bot.session.calls == [], "admin emas — jim"
    finally:
        admin_router._parent_router = None
