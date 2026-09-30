"""K29.3 — qalbaki cheklarga qarshi (haqiqiy voronkada 6 chekdan 3 tasi «pul tushmadi» edi) va chek tasdiqlash va'dasi."""

import io
from datetime import datetime, timedelta

import httpx
import pytest

from config import settings
from db.models import PaymentRequest, utcnow
from services import billing
from services import vip_reminders as vr

NOON = datetime(2026, 9, 15, 7, 0, 0)  # 12:00 Toshkent


def _png(color="white", software: str = "") -> bytes:
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo

    buf = io.BytesIO()
    meta = PngInfo()
    if software:
        meta.add_text("Software", software)
    Image.new("RGB", (40, 40), color).save(buf, "PNG", pnginfo=meta)
    return buf.getvalue()


@pytest.fixture
def client(session, tmp_path, monkeypatch):
    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

    monkeypatch.setattr(billing, "receipts_dir", lambda: tmp_path)
    monkeypatch.setattr(settings, "support_username", "arabiy_admin")

    async def _session():
        yield session

    state = {"user": None}
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    try:
        yield c, state
    finally:
        app.dependency_overrides.clear()


async def _send(c, data: bytes):
    return await c.post("/api/pay/receipt", data={"plan": "1oy"}, files={"file": ("a.png", data, "image/png")})


@pytest.mark.asyncio
async def test_same_receipt_image_cannot_be_reused(client, session, make_user):
    c, state = client
    a, b = await make_user("Birinchi"), await make_user("Ikkinchi")
    state["user"] = a
    fake = _png("red")
    r = await _send(c, fake)
    assert r.status_code == 200
    req = await session.get(PaymentRequest, r.json()["request_id"])
    assert req.receipt_hash == billing.receipt_sha(fake)
    await billing.reject(session, req, "blur")
    r = await _send(c, fake)  # aynan shu fayl qayta
    assert r.status_code == 409 and "avval ko'rib chiqilgan" in r.json()["detail"] and "@arabiy_admin" in r.json()["detail"]
    state["user"] = b  # boshqa hisobdan ham
    assert (await _send(c, fake)).status_code == 409
    assert (await _send(c, _png("blue"))).status_code == 200, "yangi rasm — o'tadi"


@pytest.mark.asyncio
async def test_repeat_fake_receipts_block_app_submissions(client, session, make_user):
    c, state = client
    u = await make_user("Yolgon")
    state["user"] = u
    for i, color in enumerate(("red", "green")):
        r = await _send(c, _png(color))
        assert r.status_code == 200
        await billing.reject(session, await session.get(PaymentRequest, r.json()["request_id"]), "none")
    r = await _send(c, _png("black"))
    assert r.status_code == 403 and "@arabiy_admin" in r.json()["detail"]


@pytest.mark.asyncio
async def test_low_or_blur_rejections_do_not_block_honest_buyer(client, session, make_user):
    c, state = client
    u = await make_user("Halol")
    state["user"] = u
    for color, reason in (("red", "low"), ("green", "blur"), ("blue", "low")):
        r = await _send(c, _png(color))
        assert r.status_code == 200
        await billing.reject(session, await session.get(PaymentRequest, r.json()["request_id"]), reason)
    assert (await _send(c, _png("black"))).status_code == 200, "«summa kam/noaniq» — jarima yo'q"


@pytest.mark.asyncio
async def test_old_fake_rejections_expire_and_daily_cap(client, session, make_user):
    c, state = client
    u = await make_user("Eski")
    state["user"] = u
    for i in range(2):
        session.add(PaymentRequest(
            user_id=u.id, plan="1oy", amount=40_000, status="rejected", reject_reason="none",
            created_at=utcnow() - timedelta(days=billing.FRAUD_DAYS + 5),
        ))
    await session.commit()
    assert (await _send(c, _png("red"))).status_code == 200, "30 kundan eski rad hisobga olinmaydi"

    v = await make_user("Spam")
    state["user"] = v
    for i in range(billing.RECEIPTS_PER_DAY):
        session.add(PaymentRequest(user_id=v.id, plan="1oy", amount=40_000, status="rejected", reject_reason="blur"))
    await session.commit()
    r = await _send(c, _png("green"))
    assert r.status_code == 429 and "Ertaga" in r.json()["detail"]


@pytest.mark.asyncio
async def test_risk_notes_and_caption(session, make_user):
    u = await make_user("Shubhali <b>")
    u.created_at = utcnow() - timedelta(days=10)
    session.add_all([
        PaymentRequest(user_id=u.id, plan="1oy", amount=40_000, status="rejected", reject_reason="none"),
        PaymentRequest(user_id=u.id, plan="3oy", amount=100_000, status="approved"),
    ])
    req = PaymentRequest(user_id=u.id, plan="1oy", amount=40_000)
    session.add(req)
    await session.commit()
    notes = await billing.risk_notes(session, req, u, _png("red", software="Adobe Photoshop 25.0"))
    text = "\n".join(notes)
    assert "«pul tushmadi» deb rad etilgan: 1 marta" in text
    assert "1 marta to'lagan mijoz" in text
    assert "tahrirlash dasturida saqlangan: Adobe Photoshop" in text
    assert billing.edit_software(_png("red", software="Android")) == "", "oddiy skrinshot belgisi — xavf emas"
    cap = billing.admin_caption(req, u, notes)
    assert "OLDIN" in cap and "40 000" in cap and "(Toshkent)" in cap and "<b>Shubhali" not in cap
    assert "kutmoqda" in billing.admin_caption(req, u, notes, waiting_min=95)


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_photo(self, chat_id, photo, caption=None, **kw):
        self.sent.append((chat_id, caption))

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


@pytest.mark.asyncio
async def test_admin_is_nudged_once_before_sla_expires(session, make_user, monkeypatch):
    monkeypatch.setattr(settings, "admin_id", 42)
    u = await make_user("Kutmoqda")
    fresh = PaymentRequest(user_id=u.id, plan="1oy", amount=40_000, created_at=NOON - timedelta(minutes=30))
    stale = PaymentRequest(user_id=u.id, plan="1oy", amount=40_000, created_at=NOON - timedelta(minutes=100))
    done = PaymentRequest(user_id=u.id, plan="1oy", amount=40_000, status="approved", created_at=NOON - timedelta(hours=5))
    session.add_all([fresh, stale, done])
    await session.commit()
    bot = FakeBot()
    r = await vr.process(session, bot, NOON)
    assert r["sla"] == 1 and len(bot.sent) == 1
    chat, text = bot.sent[0]
    assert chat == 42 and f"#{stale.id}" in text and "100 daqiqadan beri kutmoqda" in text
    assert stale.admin_nudged == 1 and fresh.admin_nudged == 0
    assert (await vr.process(session, bot, NOON + timedelta(minutes=15)))["sla"] == 0, "qayta yubormaydi"
    # 30 daqiqa o'tib «yangi» chek ham 90 daqiqadan oshadi — u ham bir marta eslatiladi
    r = await vr.process(session, bot, NOON + timedelta(minutes=70))
    assert r["sla"] == 1 and fresh.admin_nudged == 1


@pytest.mark.asyncio
async def test_no_sla_nudge_at_night(session, make_user, monkeypatch):
    monkeypatch.setattr(settings, "admin_id", 42)
    night = datetime(2026, 9, 15, 19, 0, 0)  # 00:00 Toshkent
    u = await make_user("Tunda")
    session.add(PaymentRequest(user_id=u.id, plan="1oy", amount=40_000, created_at=night - timedelta(hours=3)))
    await session.commit()
    bot = FakeBot()
    assert (await vr.process(session, bot, night))["sla"] == 0 and bot.sent == []
    assert (await vr.process(session, bot, night + timedelta(hours=9)))["sla"] == 1, "ertalab eslatiladi"


@pytest.mark.asyncio
async def test_info_exposes_sla(session, make_user):
    u = await make_user("Info")
    assert (await billing.info(session, u))["sla_hours"] == billing.SLA_HOURS == 2
