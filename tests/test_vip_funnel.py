"""K29 — /vip_voronka: to'lov voronkasi (paywall → sinov → chek → tasdiq) admin hisoboti."""

from datetime import timedelta

import pytest

from db.models import PaymentRequest, TutorTurn, XpLog, utcnow
from services import admin




@pytest.mark.asyncio
async def test_vip_funnel_counts_each_stage(session, make_user):
    now = utcnow()
    ali = await make_user("Ali")  # faol, ustozga kirgan, limitga yetgan, paywall, sinov, chek → tasdiq
    vali = await make_user("Vali")  # faol, faqat paywall
    sami = await make_user("Sami")  # faqat ro'yxatdan o'tgan
    old = await make_user("Eski")  # oynadan tashqari
    demo = await make_user("Demo", is_demo=1)  # hisobga olinmaydi
    for u in (ali, vali, demo):
        session.add(XpLog(user_id=u.id, amount=10, source="lesson:a0-01", created_at=now - timedelta(days=1)))
    session.add(XpLog(user_id=old.id, amount=10, source="lesson:a0-01", created_at=now - timedelta(days=90)))
    for i in range(3):  # kuniga 3 javob = bepul limit
        session.add(TutorTurn(user_id=ali.id, session_key="k1", created_at=now - timedelta(hours=2, minutes=i)))
    ali.paywall_seen_at = now - timedelta(days=1)
    vali.paywall_seen_at = now - timedelta(days=2)
    old.paywall_seen_at = now - timedelta(days=80)
    ali.trial_until = now - timedelta(hours=1)  # 2 kunlik sinov ~2 kun oldin boshlangan
    ali.vip_until = now + timedelta(days=30)
    session.add(PaymentRequest(user_id=ali.id, plan="1oy", amount=40000, status="approved", days=30,
                               created_at=now - timedelta(hours=5), decided_at=now - timedelta(hours=4, minutes=30)))
    session.add(PaymentRequest(user_id=vali.id, plan="1oy", amount=40000, status="pending",
                               created_at=now - timedelta(hours=4)))
    await session.commit()

    text = await admin.vip_funnel(session, 30)
    assert "oxirgi 30 kun" in text
    assert "Foydalanuvchi: <b>4</b> jami" in text, "demo hisobga olinmaydi"
    assert "Faol (XP olgan): <b>2</b>" in text
    assert "AI ustozga kirgan: <b>1</b>" in text
    assert "limitga yetgan (kuniga 3+ javob): <b>1</b>" in text
    assert "Paywall ochgan: <b>2</b>" in text, "oynadan tashqaridagi hisoblanmaydi"
    assert "sinovni yoqqan: <b>1</b>" in text
    assert "Chek yuborgan: <b>2</b>" in text
    assert "Tasdiqlangan: <b>1</b> · rad: 0 · kutmoqda: 1" in text
    assert "Daromad: <b>40 000</b> so'm" in text
    assert "median <b>30</b> daq" in text
    assert "Eng eski kutayotgan chek: <b>4.0</b> soat" in text
    assert "3 soatdan oshgan tasdiqlanmagan chek bor — /payments" in text
    assert "Umr bo'yi to'lagan: 1" in text and "sinovdan keyin chek yuborgan: 1" in text


@pytest.mark.asyncio
async def test_vip_funnel_empty_and_hints(session, make_user):
    text = await admin.vip_funnel(session, 7)
    assert "oxirgi 7 kun" in text and "Chek tasdiqlash: —" in text and "Aniq uzilish belgisi yo'q" in text
    assert "\n⏳" not in text

    # 25 faol, paywall ko'rgan yo'q → «Ustoz bo'limiga kirmayapti» xulosasi
    now = utcnow()
    for i in range(25):
        u = await make_user(f"U{i}")
        session.add(XpLog(user_id=u.id, amount=5, source="review", created_at=now))
    await session.commit()
    text = await admin.vip_funnel(session, 30)
    assert "Paywallni ko'rganlar kam" in text


@pytest.mark.asyncio
async def test_vip_funnel_days_are_clamped(session):
    assert "oxirgi 365 kun" in await admin.vip_funnel(session, 100000)
    assert "oxirgi 1 kun" in await admin.vip_funnel(session, 0)
