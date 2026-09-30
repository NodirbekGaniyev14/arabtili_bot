"""K29 — paywall matni haqiqatga mos: limitlar serverdan, va'da faqat mahsulotda bor narsalar haqida."""

from datetime import timedelta
from pathlib import Path

import pytest

from config import settings
from db.models import utcnow

ROOT = Path(__file__).resolve().parent.parent
PAYWALL = (ROOT / "webapp" / "src" / "pages" / "Paywall.tsx").read_text(encoding="utf-8")
TUTOR_PAGE = (ROOT / "webapp" / "src" / "pages" / "Tutor.tsx").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_pay_info_carries_real_limits(session, make_user, monkeypatch):
    from services import billing, tutor

    monkeypatch.setattr(settings, "tutor_daily_turns", 27)
    monkeypatch.setattr(settings, "tutor_free_turns", 4)
    info = await billing.info(session, await make_user("Ali"))
    assert (info["vip_turns"], info["free_turns"]) == (27, 4), "paywall serverdagi limitni ko'rsatadi"
    assert info["topic_count"] == len(tutor.TOPIC_BY_ID) and info["mock_count"] == len(tutor.MOCK_BY_ID)


def test_paywall_has_no_hardcoded_or_false_claims():
    for text in (PAYWALL, TUTOR_PAGE):
        assert "Kuniga 40 javob" not in text, "limit serverdan olinadi (sozlamada 30)"
        assert "cheksiz suhbat" not in text.lower() and "CHEKSIZ" not in text, "kunlik limit bor — «cheksiz» noto'g'ri"
    assert "pullik tarif" not in PAYWALL, "sarlavha pul so'ramasin — natijani va'da qilsin"
    assert "featuresFor(info)" in PAYWALL and "HERO_CHIPS" in PAYWALL


def test_hero_promises_exist_in_the_product():
    """Hero'dagi mavzular (umra, safar, ish, shifokor) Ustoz mavzulari ichida bo'lishi shart — bo'lmagan narsa va'da qilinmaydi."""
    from services import tutor

    for topic_id in ("umra", "safar", "ish", "shifokor"):
        assert topic_id in tutor.TOPIC_BY_ID, topic_id
    for mock_id in ("shifokor", "haydovchi", "gid", "bank"):
        assert mock_id in tutor.MOCK_BY_ID, mock_id  # «Shifokor, haydovchi, umra gidi, bank…»
    # Ustoz promptida hijoziy lahja yo'q — paywallda «hijoziy» deb va'da qilinmaydi
    assert "hijoziy" not in PAYWALL.lower() and "saudiya" not in PAYWALL.lower()


def test_discount_reminder_states_the_real_limit(monkeypatch):
    from db.models import User
    from services import vip_reminders

    monkeypatch.setattr(settings, "tutor_daily_turns", 27)
    u = User(tg_id=9, name="Ali", paywall_seen_at=utcnow() - timedelta(hours=2))
    text = vip_reminders.discount_text(u, utcnow())
    assert "kuniga 27 javob" in text and "cheksiz" not in text
