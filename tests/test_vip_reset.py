"""2026-11-28 egasi: VIP hammadan olinadi, faqat 6519846998 da 30 kun qoladi (`/vip_tozalash`)."""

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

from config import settings
from db.models import PaymentRequest, User, utcnow
from services import billing

KEEP = 6519846998


class FakeMessage:
    def __init__(self, tg_id, text):
        self.from_user = SimpleNamespace(id=tg_id)
        self.chat = SimpleNamespace(id=tg_id)
        self.text = text
        self.answers = []

    async def answer(self, text, **kw):
        self.answers.append(text)


async def _users(session):
    now = utcnow()
    paid = User(tg_id=1, name="Tolagan", vip_until=now + timedelta(days=20))
    trial = User(tg_id=2, name="Sinov", vip_until=now + timedelta(days=2), trial_until=now + timedelta(days=2))
    keep = User(tg_id=KEEP, name="Egasi tanlagan", vip_until=None)
    plain = User(tg_id=3, name="Oddiy")
    expired = User(tg_id=4, name="Tugagan", vip_until=now - timedelta(days=3))
    session.add_all([paid, trial, keep, plain, expired])
    await session.flush()
    session.add(PaymentRequest(user_id=paid.id, plan="1oy", amount=40000, status="approved", days=30))
    await session.commit()
    return paid, trial, keep


@pytest.mark.asyncio
async def test_preview_changes_nothing_apply_keeps_one_for_30_days(session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "arabiy.db"))
    paid, trial, keep = await _users(session)

    res = await billing.reset_vip(session, KEEP, 30)
    assert sorted(u.name for u, _ in res["remove"]) == ["Sinov", "Tolagan"]
    assert [u.name for u, p in res["remove"] if p] == ["Tolagan"], "to'laganlar alohida ko'rsatiladi"
    assert billing.is_vip(paid) and res["backup"] is None, "ko'rish — hech narsa o'zgarmaydi"

    now = utcnow()
    res = await billing.reset_vip(session, KEEP, 30, now=now, apply=True)
    assert not billing.is_vip(paid) and not billing.is_vip(trial)
    assert keep.vip_until == now + timedelta(days=30) and billing.vip_days_left(keep) in (30, 31)
    backup = json.loads((tmp_path / res["backup"].split("\\")[-1].split("/")[-1]).read_text(encoding="utf-8"))
    assert {r["tg_id"] for r in backup} == {1, 2, KEEP} and any(r.get("paid") for r in backup)
    assert trial.trial_until is not None, "sinov ishlatilgani yozuvi qoladi — qayta sinov ochilmaydi"


@pytest.mark.asyncio
async def test_admin_command(session, session_factory, tmp_path, monkeypatch):
    import bot.admin as adm

    monkeypatch.setattr(settings, "admin_id", 999)
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "arabiy.db"))
    monkeypatch.setattr(adm, "SessionLocal", session_factory)
    await _users(session)

    m = FakeMessage(999, "/vip_tozalash")
    await adm.cmd_vip_reset(m)
    assert "Olinadi: <b>2</b>" in m.answers[0] and "TO'LAGAN" in m.answers[0] and "/vip_tozalash tasdiq" in m.answers[0]
    m = FakeMessage(999, "/vip_tozalash tasdiq")
    await adm.cmd_vip_reset(m)
    assert "VIP olib tashlandi" in m.answers[0] and "30 kun" in m.answers[0] and "vip_backup_" in m.answers[0]
    async with session_factory() as s:
        vips = [u.tg_id for u in (await s.execute(User.__table__.select())).all() if u.vip_until and u.vip_until > utcnow()]
    assert vips == [KEEP]

    m = FakeMessage(1, "/vip_tozalash tasdiq")  # admin emas
    await adm.cmd_vip_reset(m)
    assert m.answers == []
