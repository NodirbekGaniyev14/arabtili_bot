"""K26 — bildirishnoma sozlamalari, «Xatolik bormi?» xabari, admin «✅ Tuzatildi», audio matn normalizatsiyasi."""

import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from db.models import Feedback, User
from services import feedback as fs
from services import notify_prefs as np

ROOT = Path(__file__).resolve().parent.parent


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str, object]] = []

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.sent.append((chat_id, text, reply_markup))


# ── notify_prefs ──


def test_prefs_default_on_and_toggle():
    u = SimpleNamespace(notify_off="")
    assert all(np.enabled(u, k) for k in np.KEYS)
    np.set_pref(u, "daily", False)
    np.set_pref(u, "news", False)
    assert u.notify_off == "daily,news"
    assert not np.enabled(u, "daily") and np.enabled(u, "writing")
    np.set_pref(u, "daily", True)
    assert u.notify_off == "news"
    assert np.enabled(u, "nomalum")  # noma'lum kalit — doim ha
    assert np.enabled_raw("daily,news", "writing") and not np.enabled_raw("daily,news", "news")
    assert np.enabled_raw(None, "news")
    with pytest.raises(ValueError):
        np.set_pref(u, "yoq", False)
    pub = np.public(u)
    assert [i["key"] for i in pub["items"]] == [i["key"] for i in np.ITEMS]
    assert {i["key"]: i["on"] for i in pub["items"]}["news"] is False
    assert {i["group"] for i in pub["items"]} == {"types", "other"} and pub["always"]


# ── API ──


@pytest.fixture
def client_for(session, monkeypatch):
    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

    bot = FakeBot()
    monkeypatch.setattr(app.state, "bot", bot, raising=False)

    async def _session():
        yield session

    def make(user):
        app.dependency_overrides[get_session] = _session
        app.dependency_overrides[get_current_user] = lambda: user
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")

    yield make, bot
    app.dependency_overrides.clear()


async def test_notification_settings_api(session, make_user, client_for):
    make, _ = client_for
    user = await make_user("Ali")
    await session.commit()
    async with make(user) as c:
        r = (await c.get("/api/settings/notifications")).json()
        assert all(i["on"] for i in r["items"]) and len(r["items"]) == len(np.ITEMS)
        r = (await c.post("/api/settings/notifications", json={"key": "vip", "on": False})).json()
        assert {i["key"]: i["on"] for i in r["items"]}["vip"] is False
        assert (await c.post("/api/settings/notifications", json={"key": "yoq", "on": False})).status_code == 400
    await session.refresh(user)
    assert user.notify_off == "vip"


async def test_report_issue_notifies_admin_dedupes_and_limits(session, make_user, client_for, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 999)
    make, bot = client_for
    user = await make_user("Zamira")
    await session.commit()
    body = {
        "kind": "audio",
        "context": "a1-03",
        "label": "MIKRO-TEST · 2/5",
        "q": "Bu so'z qanday tarjima qilinadi?",
        "q_ar": "كِتَاب",
        "options": ["kitob", "qalam", "stol"],
        "answer": "kitob",
        "audio": "a0/kitab.mp3",
        "comment": "ovoz boshqa so'zni aytyapti",
    }
    async with make(user) as c:
        assert (await c.post("/api/report-issue", json=body)).json() == {"ok": True}
        assert (await c.post("/api/report-issue", json=body)).json().get("duplicate") is True
        assert (await c.post("/api/report-issue", json={**body, "kind": "yoq"})).status_code == 400
    rows = (await session.execute(select(Feedback))).scalars().all()
    assert len(rows) == 1 and rows[0].source == "issue" and rows[0].context == "a1-03"
    assert "Talaffuz" in rows[0].text and "✓ kitob" in rows[0].text and "a0/kitab.mp3" in rows[0].text
    assert len(bot.sent) == 1
    chat, text, kb = bot.sent[0]
    assert chat == 999 and "Savolda xato" in text and f"#F{rows[0].id}" in text
    assert kb.inline_keyboard[0][0].callback_data == f"fixed:{rows[0].id}"

    monkeypatch.setattr(fs, "ISSUE_DAILY_LIMIT", 1)
    async with make(user) as c:
        assert (await c.post("/api/report-issue", json={**body, "q": "boshqa savol"})).json().get("limited") is True
    assert len((await session.execute(select(Feedback))).scalars().all()) == 1


# ── admin «✅ Tuzatildi» ──


class FakeCb:
    def __init__(self, admin_id: int, data: str):
        self.from_user = SimpleNamespace(id=admin_id)
        self.data = data
        self.answers: list[str] = []
        self.markups: list[object] = []
        self.message = SimpleNamespace(edit_reply_markup=self._edit)

    async def _edit(self, reply_markup=None):
        self.markups.append(reply_markup)

    async def answer(self, text: str = "", **kw):
        self.answers.append(text)


@pytest.mark.parametrize("fixed_on", [True, False])
async def test_fixed_callback_notifies_user(session, make_user, session_factory, monkeypatch, fixed_on):
    import bot.admin as adm
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 999)
    monkeypatch.setattr(adm, "SessionLocal", session_factory)
    user = await make_user("Zamira")
    if not fixed_on:
        user.notify_off = "fixed"
    fb = await fs.save(session, user.id, fs.issue_text("text", q="kitob", q_ar="كِتَاب"), source="issue")
    await session.commit()

    bot = FakeBot()
    cb = FakeCb(999, f"fixed:{fb.id}")
    await adm.cb_issue_fixed(cb, bot)
    if fixed_on:
        assert len(bot.sent) == 1 and bot.sent[0][0] == user.tg_id
        assert "xato tuzatildi" in bot.sent[0][1] and "كِتَاب" in bot.sent[0][1]
    else:
        assert bot.sent == []
    async with session_factory() as s2:
        row = await s2.get(Feedback, fb.id)
        assert row.replied_at is not None and row.reply_text == "✅ Tuzatildi"
    # Qayta bosish — takror xabar yo'q
    cb2 = FakeCb(999, f"fixed:{fb.id}")
    await adm.cb_issue_fixed(cb2, bot)
    assert cb2.answers == ["Allaqachon belgilangan"] and len(bot.sent) == (1 if fixed_on else 0)
    # Admin bo'lmagan odam bossa — hech narsa
    cb3 = FakeCb(1, f"fixed:{fb.id}")
    await adm.cb_issue_fixed(cb3, bot)
    assert cb3.answers == [""]


# ── yuboruvchilar sozlamani hurmat qiladi ──


async def test_senders_respect_prefs(session, make_user, session_factory, monkeypatch):
    from services import admin, battle, battle_season, vip_reminders

    a = await make_user("Ali")
    b = await make_user("Vali", notify_off="news,oktagon,vip")
    await session.commit()
    ids = await admin.all_real_tg_ids(session, "news")
    assert a.tg_id in ids and b.tg_id not in ids
    assert set(await admin.all_real_tg_ids(session)) >= {a.tg_id, b.tg_id}

    bot = FakeBot()
    assert await vip_reminders._send(bot, b, "matn", "👑") is False and bot.sent == []

    monkeypatch.setattr(battle, "SESSION_FACTORY", session_factory)
    board = [
        {"user_id": a.id, "name": "Ali", "points": 40, "games": 2, "wins": 2, "rank": 1},
        {"user_id": b.id, "name": "Vali", "points": 20, "games": 2, "wins": 1, "rank": 2},
    ]
    out = await battle_season.announce(bot, "week", "21.09 — 27.09", board[:1], board)
    assert out["sent"] == 1 and [c for c, _t, _k in bot.sent] == [a.tg_id]


# ── audio: aytiladigan matn ──


def test_spoken_text_normalization():
    sys.path.insert(0, str(ROOT / "content"))
    import build_audio as ba

    assert ba.spoken("عَ ـ حَ ـ عَرَب") == "عَ، حَ، عَرَب"
    assert ba.spoken("فَازَ بِـ") == "فَازَ بِ"
    assert ba.spoken("تَمَام / زَيْن") == "تَمَام، زَيْن"
    assert ba.spoken("وَمَعَ ذٰلِكَ") == "وَمَعَ ذَالِكَ"
    assert ba.spoken("سِفارة") == "سِفارَة"  # ta marbuta oldi — fatha
    assert ba.spoken("حَيَاة") == "حَيَاة"  # alifdan keyin — tegilmaydi
    assert ba.spoken("مَدْرَسَةٌ") == "مَدْرَسَةٌ"
    # Harakatsiz hijoz so'zlari endi audio_text bilan (TTS taxmin qilmasin)
    import json

    phrases = json.loads((ROOT / "content" / "hejazi.json").read_text(encoding="utf-8"))["phrases"]
    bare = [p["audio"] for p in phrases if not any(0x064B <= ord(ch) <= 0x0652 for ch in p.get("audio_text") or p["hejazi_ar"])]
    assert bare == [], bare
