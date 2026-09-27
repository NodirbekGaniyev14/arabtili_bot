"""K27.4 — /javoblar: oxirgi deploydan beri (standart), sanadan beri, N kun; deploy vaqti Meta'da."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

from db.models import AnswerLog, Meta, utcnow
from services import answer_log


class FakeMessage:
    def __init__(self, tg_id: int, text: str):
        self.from_user = SimpleNamespace(id=tg_id, first_name="Admin", username="")
        self.text = text
        self.answers: list[str] = []

    async def answer(self, text, reply_markup=None, **kw):
        self.answers.append(text)


class FakeBot:
    def __init__(self):
        self.sent: list[int] = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append(chat_id)


def test_since_local_date():
    today = date(2026, 9, 30)
    assert answer_log.since_local_date("27.09", today=today) == datetime(2026, 9, 26, 19, 0)  # 00:00 Toshkent
    assert answer_log.since_local_date("15.12", today=today) == datetime(2025, 12, 14, 19, 0)  # kelajak — o'tgan yil
    assert answer_log.since_local_date("31.02", today=today) is None


async def test_deploy_time_recorded_only_on_new_version(session_factory, monkeypatch):
    from services import deploy_notify as dn

    monkeypatch.setattr(dn, "SessionLocal", session_factory)
    monkeypatch.setattr(dn, "current_version", lambda: "abc1234")
    await dn.notify_if_updated(FakeBot())
    async with session_factory() as s:
        t1 = await dn.last_deploy_at(s)
        assert t1 and abs((utcnow() - t1).total_seconds()) < 120
        (await s.get(Meta, dn.DEPLOY_AT_KEY)).value = "2026-01-01T00:00:00"
        await s.commit()
    await dn.notify_if_updated(FakeBot())  # versiya o'sha — vaqt o'zgarmaydi
    async with session_factory() as s:
        assert await dn.last_deploy_at(s) == datetime(2026, 1, 1)
    monkeypatch.setattr(dn, "current_version", lambda: "def5678")
    await dn.notify_if_updated(FakeBot())
    async with session_factory() as s:
        assert (await dn.last_deploy_at(s)) > datetime(2026, 1, 1)


async def test_javoblar_periods(session, make_user, session_factory, monkeypatch):
    import bot.admin as adm
    from config import settings
    from services import deploy_notify

    monkeypatch.setattr(settings, "admin_id", 999)
    monkeypatch.setattr(adm, "SessionLocal", session_factory)
    u = await make_user("A")
    now = utcnow()
    for given, hours in (("eski", 48), ("yangi", 1)):
        session.add(
            AnswerLog(
                user_id=u.id, context="a2-04", ex_type="translate_ar_uz", q="تَكْتُبِينَ",
                expected="sen (ayol) yozasan", given=given, created_at=now - timedelta(hours=hours),
            )
        )
    await session.commit()

    async def run(text: str) -> str:
        m = FakeMessage(999, text)
        await adm.cmd_javoblar(m)
        return "\n".join(m.answers)

    out = await run("/javoblar")  # deploy vaqti hali yo'q — 30 kun
    assert "deploy vaqti hali yozilmagan" in out and "«eski»" in out and "«yangi»" in out

    session.add(Meta(key=deploy_notify.DEPLOY_AT_KEY, value=(now - timedelta(hours=5)).isoformat(timespec="seconds")))
    await session.commit()
    out = await run("/javoblar")
    assert "oxirgi deploydan beri" in out and "«yangi»" in out and "«eski»" not in out
    out = await run("/javoblar yangi 5")
    assert "oxirgi deploydan beri" in out and "«eski»" not in out

    yesterday = (now + answer_log.TASHKENT).date() - timedelta(days=1)
    out = await run(f"/javoblar {yesterday:%d.%m}")
    assert f"{yesterday:%d.%m} dan beri" in out and "«yangi»" in out and "«eski»" not in out

    out = await run("/javoblar 7 5")
    assert "7 kun" in out and "«eski»" in out and "«yangi»" in out
    assert "Sana noto'g'ri" in await run("/javoblar 31.02")

    m = FakeMessage(1, "/javoblar")  # admin emas
    await adm.cmd_javoblar(m)
    assert m.answers == []


async def test_javoblar_splits_on_lines(session, make_user, session_factory, monkeypatch):
    """Uzun hisobot qator chegarasida bo'linadi — HTML teg o'rtasidan kesilmaydi."""
    import bot.admin as adm
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 999)
    monkeypatch.setattr(adm, "SessionLocal", session_factory)
    u = await make_user("A")
    for i in range(40):
        session.add(
            AnswerLog(user_id=u.id, context=f"a2-{i:02d}", ex_type="translate_ar_uz", q="savol " * 15 + str(i),
                      expected="javob " * 10, given="x" * 60)
        )
    await session.commit()
    m = FakeMessage(999, "/javoblar 30 40")
    await adm.cmd_javoblar(m)
    assert len(m.answers) >= 2
    for part in m.answers:
        assert len(part) <= 3900 and part.count("<b>") == part.count("</b>")
