"""VIP tarif va to'lov (K17.2): muddat, chegirma, chek so'rovi, tasdiqlash."""

from datetime import timedelta

import pytest

from db.models import User, utcnow
from services import billing


def test_vip_grant_and_extend():
    u = User(tg_id=1, name="N")
    assert not billing.is_vip(u) and billing.vip_days_left(u) == 0
    until = billing.grant(u, 30)
    assert billing.is_vip(u) and billing.vip_days_left(u) == 30
    # Faol VIP oxiridan uzayadi, bugundan emas
    until2 = billing.grant(u, 90)
    assert (until2 - until).days == 90


def test_expired_vip():
    u = User(tg_id=1, vip_until=utcnow() - timedelta(days=1))
    assert not billing.is_vip(u)
    billing.grant(u, 10)
    assert 9 <= billing.vip_days_left(u) <= 10


def test_discount_timer(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "pay_price_month", 90_000)
    monkeypatch.setattr(settings, "pay_price_3month", 240_000)
    monkeypatch.setattr(settings, "pay_old_price_month", 180_000)
    monkeypatch.setattr(settings, "pay_discount_hours", 24)
    u = User(tg_id=1)
    assert billing.discount_percent() == 50
    # Paywall hali ochilmagan — taymer yo'q, lekin narx chegirmali emas
    assert not billing.discount_active(u)
    u.paywall_seen_at = utcnow()
    assert billing.discount_active(u)
    assert billing.current_price("1oy", u) == 90_000
    assert billing.current_price("3oy", u) == 240_000
    u.paywall_seen_at = utcnow() - timedelta(hours=25)
    assert not billing.discount_active(u)
    assert billing.current_price("1oy", u) == 180_000
    assert billing.current_price("3oy", u) == 540_000


def test_discount_disabled(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "pay_old_price_month", 0)
    u = User(tg_id=1, paywall_seen_at=utcnow())
    assert not billing.discount_enabled()
    assert billing.discount_percent() == 0
    assert billing.current_price("1oy", u) == settings.pay_price_month


def test_format_card():
    assert billing.format_card("8600123412341234") == "8600 1234 1234 1234"
    assert billing.format_card("8600 1234-1234 1234") == "8600 1234 1234 1234"
    assert billing.format_card("") == ""


@pytest.mark.asyncio
async def test_receipt_flow(session, make_user, tmp_path, monkeypatch):
    monkeypatch.setattr(billing, "receipts_dir", lambda: tmp_path)
    u = await make_user("Nodir")
    await session.commit()

    info = await billing.info(session, u)
    assert info["vip"] is False and info["pending"] is False
    assert u.paywall_seen_at is not None, "taymer boshlanadi"
    assert [p["id"] for p in info["plans"]] == ["1oy", "3oy"]

    req = await billing.create_request(session, u, "1oy", b"\x89PNGfake", "image/png")
    assert req.status == "pending" and req.amount == info["plans"][0]["price"]
    assert (tmp_path / f"{req.id}_{u.tg_id}.png").read_bytes() == b"\x89PNGfake"
    assert await billing.has_pending(session, u.id)
    assert "#" + str(req.id) in billing.admin_caption(req, u)

    row = await billing.load_request(session, req.id)
    assert row is not None
    until = await billing.approve(session, row[0], row[1], 30)
    assert row[0].status == "approved" and row[0].days == 30
    assert billing.is_vip(row[1]) and row[1].vip_until == until
    assert not await billing.has_pending(session, u.id)
    # Qayta bosilsa muddat ikkilanmaydi
    assert await billing.approve(session, row[0], row[1], 30) == until


@pytest.mark.asyncio
async def test_reject_flow(session, make_user, tmp_path, monkeypatch):
    monkeypatch.setattr(billing, "receipts_dir", lambda: tmp_path)
    u = await make_user()
    await session.commit()
    req = await billing.create_request(session, u, "3oy", b"x", "image/jpeg")
    await billing.reject(session, req)
    assert req.status == "rejected" and not billing.is_vip(u)
    assert "tasdiqlanmadi" in billing.user_rejected_text()
    assert not (await billing.pending_list(session))


@pytest.mark.asyncio
async def test_social_proof_counts_real_users(session, make_user):
    await make_user("A")
    await make_user("Demo", is_demo=1)
    await session.commit()
    proof = await billing.social_proof(session)
    assert proof["learners"] == 1 and proof["like_percent"] == 0
