"""Fikrga anonim javob — faqat yozgan odamga boradi, admin ismi ko'rinmaydi."""

import pytest

from services import feedback as fs


async def test_save_stores_feedback(session, make_user):
    user = await make_user()
    fb = await fs.save(session, user.id, "salom", source="app", context="profil")
    assert fb.id > 0
    assert fb.source == "app"
    assert fb.reply_text == ""
    assert fb.replied_at is None


async def test_save_truncates_long_text(session, make_user):
    user = await make_user()
    fb = await fs.save(session, user.id, "x" * 5000, source="bot")
    assert len(fb.text) == 2000


# ── Adminga xabar ──


async def test_admin_notice_has_id_tag(session, make_user):
    user = await make_user(name="Zamira")
    fb = await fs.save(session, user.id, "ismim xato", source="app", context="profil")
    text = fs.admin_notice(fb, user)
    assert f"#F{fb.id}" in text
    assert "ismim xato" in text
    assert str(user.tg_id) in text


async def test_admin_notice_escapes_html(session, make_user):
    user = await make_user()
    fb = await fs.save(session, user.id, "<b>qalin</b>", source="app")
    assert "&lt;b&gt;" in fs.admin_notice(fb, user)
    assert "<b>qalin</b>" not in fs.admin_notice(fb, user)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("💬 Yangi fikr #F42\nsalom", 42),
        ("#F1", 1),
        ("hech qanday yorliq yo'q", None),
        ("", None),
        ("#FF", None),
    ],
)
def test_feedback_id_parsing(text, expected):
    assert fs.feedback_id_from_text(text) == expected


# ── Foydalanuvchiga javob ──


async def test_reply_notice_is_anonymous(session, make_user):
    user = await make_user(name="Zamira")
    fb = await fs.save(session, user.id, "ismim xato", source="app")
    notice = fs.reply_notice(fb, "Profil sahifasidan o'zgartira olasiz")

    assert "Arabiy jamoasi" in notice
    assert "Profil sahifasidan" in notice
    assert "ismim xato" in notice  # o'z fikri eslatiladi
    assert "admin" not in notice.lower()


async def test_reply_notice_escapes_html(session, make_user):
    user = await make_user()
    fb = await fs.save(session, user.id, "salom", source="app")
    assert "&lt;script&gt;" in fs.reply_notice(fb, "<script>x</script>")


async def test_load_with_user_returns_pair(session, make_user):
    user = await make_user(name="Aziz")
    fb = await fs.save(session, user.id, "salom", source="app")
    row = await fs.load_with_user(session, fb.id)
    assert row is not None
    assert row[0].id == fb.id
    assert row[1].id == user.id


async def test_load_with_user_missing_returns_none(session):
    assert await fs.load_with_user(session, 999999) is None


async def test_mark_replied_records_text_and_time(session, make_user):
    user = await make_user()
    fb = await fs.save(session, user.id, "salom", source="app")
    await fs.mark_replied(session, fb, "javob matni")
    assert fb.reply_text == "javob matni"
    assert fb.replied_at is not None


async def test_mark_replied_truncates(session, make_user):
    user = await make_user()
    fb = await fs.save(session, user.id, "salom", source="app")
    await fs.mark_replied(session, fb, "y" * 9999)
    assert len(fb.reply_text) == fs.MAX_REPLY


# ── Admin handleri: javob to'g'ri odamga ketadimi ──


class FakeBot:
    def __init__(self, fail: bool = False):
        self.sent: list[tuple[int, str]] = []
        self.fail = fail

    async def send_message(self, chat_id, text, **kw):
        if self.fail:
            raise RuntimeError("bloklangan")
        self.sent.append((chat_id, text))


@pytest.fixture
def admin_mod(session_factory, monkeypatch):
    from bot import admin as mod

    monkeypatch.setattr(mod, "SessionLocal", session_factory)
    return mod


async def test_reply_goes_only_to_author(session, make_user, admin_mod):
    author = await make_user(name="Zamira")
    other = await make_user(name="Boshqa")
    fb = await fs.save(session, author.id, "ismim xato", source="app")

    bot = FakeBot()
    out = await admin_mod._send_reply(bot, fb.id, "Profildan o'zgartiring")

    assert len(bot.sent) == 1
    chat_id, text = bot.sent[0]
    assert chat_id == author.tg_id
    assert chat_id != other.tg_id
    assert "Profildan o'zgartiring" in text
    assert "Arabiy jamoasi" in text
    assert "✅" in out


async def test_reply_marks_feedback_replied(session, make_user, admin_mod):
    user = await make_user()
    fb = await fs.save(session, user.id, "savol", source="bot")
    await admin_mod._send_reply(FakeBot(), fb.id, "javob")

    async with admin_mod.SessionLocal() as s:
        row = await fs.load_with_user(s, fb.id)
    assert row[0].reply_text == "javob"
    assert row[0].replied_at is not None


async def test_reply_to_unknown_feedback_reports_error(admin_mod):
    bot = FakeBot()
    out = await admin_mod._send_reply(bot, 999999, "javob")
    assert out.startswith("❌")
    assert bot.sent == []


async def test_blocked_user_not_marked_replied(session, make_user, admin_mod):
    """Yetkazilmasa — javob berilgan deb belgilanmasin, qayta urinish mumkin."""
    user = await make_user()
    fb = await fs.save(session, user.id, "savol", source="app")
    out = await admin_mod._send_reply(FakeBot(fail=True), fb.id, "javob")

    assert out.startswith("❌")
    async with admin_mod.SessionLocal() as s:
        row = await fs.load_with_user(s, fb.id)
    assert row[0].reply_text == ""
    assert row[0].replied_at is None
