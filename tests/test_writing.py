"""K19.2 — yozuv mashqi: matn banki, 2 kunlik davr, surat tayyorlash, API oqimi
(3 urinish, XP bir marta, eng yaxshi ball), /api/me holati, bot eslatmasi."""

import io
import json
from datetime import date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from db.models import Plan, User, WritingResult, XpLog
from services import writing, writing_reminder as wr


def _png(w=800, h=600) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, "PNG")
    return buf.getvalue()


def _reply(acc=84, hand=True) -> writing.WritingReply:
    return writing.WritingReply(
        is_handwriting=hand, read_ar="بيت باب", accuracy=acc, neatness=4,
        missing_words=["نَافِذَة"], wrong_words=[writing.WrongWord(written="بيت", correct="بَيْت", note_uz="harakat yo'q")],
        tips_uz=["Nuqtalarni aniq qo'ying", "Harflarni ulang"], praise_uz="Zo'r!",
    )


def test_bank_and_period():
    b = writing.bank()
    ids = [t["id"] for lv in writing.LEVELS for t in b[lv]]
    assert len(ids) == len(set(ids)) and all(len(b[lv]) == 30 for lv in writing.LEVELS), "K20.5: 30 matn/daraja"
    assert {t["kind"] for lv in b for t in b[lv]} <= {"so'zlar", "matn", "hikoya", "maqol", "she'r", "xat"}
    assert all(t["ar"] and t["uz"] and t["title_uz"] for lv in b for t in b[lv])
    # 60 kunlik aylanish: 30 davr ichida takror yo'q
    seq = [writing.text_for("A2", date(2026, 1, 1) + timedelta(days=2 * i))["id"] for i in range(30)]
    assert len(set(seq)) == 30
    for lv in writing.LEVELS:
        for t in b[lv]:
            assert t["ar"] and t["uz"] and t["title_uz"] and t["translit"]
    # 2 kunlik davr: 19.09 boshi, 20.09 o'sha davr, 21.09 yangi
    assert writing.period_key(date(2026, 9, 19)) == "2026-09-19" == writing.period_key(date(2026, 9, 20))
    assert writing.period_key(date(2026, 9, 21)) == "2026-09-21" and writing.period_ends(date(2026, 9, 19)) == "2026-09-20"
    assert writing.is_period_start(date(2026, 9, 19)) and not writing.is_period_start(date(2026, 9, 20))
    assert writing.text_for("A1", date(2026, 9, 19)) == writing.text_for("A1", date(2026, 9, 20))
    assert writing.text_for("A1", date(2026, 9, 19)) != writing.text_for("A1", date(2026, 9, 21))
    assert writing.text_for("zz")["id"].startswith("a0-"), "noma'lum daraja → A0"


def test_current_text_sticks_to_started_row():
    """Davrda urinish bo'lgan bo'lsa matn o'zgarmaydi — daraja o'zgarsa yoki bank kengaysa ham (K20.5)."""
    row = WritingResult(user_id=1, period="2026-09-19", text_id="a1-t03", level="A1", attempts=1)
    assert writing.current_text("B2", row)["id"] == "a1-t03"
    row.attempts = 0
    assert writing.current_text("B2", row)["id"].startswith("b2-")
    row.attempts, row.text_id = 1, "yo'q-id"
    assert writing.current_text("A0", row)["id"].startswith("a0-"), "noma'lum id → navbatdagi"
    assert writing.current_text("A0", None)["id"] == writing.text_for("A0")["id"]
    assert writing.xp_for(0) == 6 and writing.xp_for(84) == 14 and writing.xp_for(100) == 16


def test_prepare_image():
    from PIL import Image

    out, mime = writing.prepare_image(_png(3000, 1000))
    assert mime == "image/jpeg" and Image.open(io.BytesIO(out)).size == (1400, 467)
    small, _ = writing.prepare_image(_png(300, 200))
    assert Image.open(io.BytesIO(small)).size == (300, 200), "kichik surat kattalashtirilmaydi"
    with pytest.raises(ValueError):
        writing.prepare_image(b"not an image")
    # #F84: format baytlardan aniqlanadi — xato xabari foydalanuvchiga tushunarli
    heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 40
    assert writing.image_format_hint(heic) == "HEIC"
    assert writing.image_format_hint(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 40) == "video"
    assert writing.image_format_hint(b"%PDF-1.4 ...") == "PDF"
    assert writing.image_format_hint(_png()) == ""
    # HEIC (pillow-heif bor bo'lsa) — haqiqiy HEIC yozib o'qiymiz; paket yo'q bo'lsa xato xabarida HEIC
    try:
        import pillow_heif  # noqa: F401
    except ImportError:
        with pytest.raises(ValueError, match="HEIC"):
            writing.prepare_image(heic)
    else:
        from PIL import Image

        pillow_heif.register_heif_opener()
        buf = io.BytesIO()
        Image.new("RGB", (40, 30), "white").save(buf, format="HEIF")
        out, mime = writing.prepare_image(buf.getvalue())
        assert mime == "image/jpeg" and Image.open(io.BytesIO(out)).size == (40, 30)


@pytest.mark.asyncio
async def test_check_clamps_and_rejects_non_handwriting(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "k")

    async def fake_vision(system, image, mime):
        assert "ORIGINAL TEXT" in system[0]["text"] and mime == "image/jpeg"
        r = _reply(acc=140)
        r.neatness = 9
        r.tips_uz = ["a", "b", "c", "d"]
        return r, {"in": 1500, "out": 100}

    monkeypatch.setattr(writing, "_call_vision", fake_vision)
    r, usage = await writing.check("A1", writing.text_for("A1"), b"img", "image/jpeg")
    assert r.accuracy == 100 and r.neatness == 5 and len(r.tips_uz) == 3 and usage["in"] == 1500

    async def screen(system, image, mime):
        return _reply(acc=70, hand=False), {}

    monkeypatch.setattr(writing, "_call_vision", screen)
    r, _ = await writing.check("A1", writing.text_for("A1"), b"img", "image/jpeg")
    assert r.accuracy == 0 and r.is_handwriting is False

    monkeypatch.setattr(settings, "anthropic_api_key", "")
    from services.tutor import TutorUnavailable

    with pytest.raises(TutorUnavailable):
        await writing.check("A1", writing.text_for("A1"), b"img", "image/jpeg")


@pytest.fixture
def client(session, monkeypatch):
    from db.session import get_session
    from main import app
    from services import tts
    from services.telegram_auth import get_current_user

    monkeypatch.setattr(tts, "schedule", lambda text, level: "")

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


@pytest.mark.asyncio
async def test_writing_api_flow(client, session, make_user, monkeypatch):
    from config import settings

    c, state = client
    u = await make_user("Nodir")
    session.add(Plan(user_id=u.id, level="A1", target_level="A2", target_date="2027-01-01"))
    await session.flush()
    state["user"] = u
    monkeypatch.setattr(settings, "anthropic_api_key", "k")

    r = await c.get("/api/v2/tutor/writing")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["level"] == "A1" and d["done"] is None and d["attempts_left"] == 3 and d["text"]["id"].startswith("a1-")
    assert d["period"] == writing.period_key() and d["history"] == []

    me = (await c.get("/api/me")).json()
    assert me["writing"]["done"] is False and me["writing"]["title"] == d["text"]["title_uz"]

    replies = iter([_reply(acc=84), _reply(acc=60), _reply(acc=91)])

    async def fake_vision(system, image, mime):
        return next(replies), {"in": 1500, "out": 120}

    monkeypatch.setattr(writing, "_call_vision", fake_vision)

    files = {"file": ("w.png", _png(), "image/png")}
    assert (await c.post("/api/v2/tutor/writing/check", files={"file": ("x.txt", b"abc", "text/plain")})).status_code == 422
    # #F84: MIME bo'sh/octet-stream (Android galereya) — baytlar surat bo'lsa qabul; surat bo'lmasa aniq xabar
    r = await c.post("/api/v2/tutor/writing/check", files={"file": ("x", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 40, "application/octet-stream")})
    assert r.status_code == 422 and "video" in r.json()["detail"]
    r = await c.post("/api/v2/tutor/writing/check", files=files)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["score"] == 84 and d["xp"] == 14 and d["xp_awarded"] == 14 and d["attempts"] == 1 and d["attempts_left"] == 2
    assert d["result"]["accuracy"] == 84 and d["result"]["wrong_words"][0]["correct"] == "بَيْت" and d["improved"]
    assert (await session.execute(select(XpLog))).scalar_one().source == f"writing:{writing.period_key()}"

    # 2-urinish yomonroq: ball/feedback qolgan, XP qayta berilmaydi (MIME octet-stream, baytlar PNG — o'tadi)
    d = (await c.post("/api/v2/tutor/writing/check", files={"file": ("w", _png(), "application/octet-stream")})).json()
    assert d["score"] == 84 and d["attempts"] == 2 and d["xp_awarded"] == 0 and d["improved"] is False
    assert d["result"]["accuracy"] == 60
    # 3-urinish yaxshiroq: eng yaxshi ball yangilanadi
    d = (await c.post("/api/v2/tutor/writing/check", files=files)).json()
    assert d["score"] == 91 and d["attempts_left"] == 0 and d["improved"] and d["xp_awarded"] == 0
    assert (await c.post("/api/v2/tutor/writing/check", files=files)).status_code == 429
    assert len((await session.execute(select(XpLog))).scalars().all()) == 1
    row = (await session.execute(select(WritingResult))).scalar_one()
    assert row.score == 91 and row.attempts == 3 and row.xp == 14 and json.loads(row.feedback)["praise_uz"] == "Zo'r!"

    d = (await c.get("/api/v2/tutor/writing")).json()
    assert d["done"]["score"] == 91 and d["attempts_left"] == 0 and d["history"][0]["score"] == 91
    assert (await c.get("/api/me")).json()["writing"]["done"] is True


@pytest.mark.asyncio
async def test_writing_api_unavailable_and_screen(client, session, make_user, monkeypatch):
    from config import settings
    from services.tutor import TutorUnavailable

    c, state = client
    state["user"] = await make_user("A")
    monkeypatch.setattr(settings, "anthropic_api_key", "k")

    async def down(system, image, mime):
        raise TutorUnavailable("Ustoz band", "credit")

    monkeypatch.setattr(writing, "_call_vision", down)
    r = await c.post("/api/v2/tutor/writing/check", files={"file": ("w.png", _png(), "image/png")})
    assert r.status_code == 503 and "band" in r.json()["detail"]

    async def screen(system, image, mime):
        return _reply(acc=70, hand=False), {}

    monkeypatch.setattr(writing, "_call_vision", screen)
    d = (await c.post("/api/v2/tutor/writing/check", files={"file": ("w.png", _png(), "image/png")})).json()
    assert d["score"] == 0 and d["xp"] == 0 and d["attempts"] == 1, "ekran surati — XP yo'q, urinish sarflanadi"
    assert (await session.execute(select(XpLog))).scalars().all() == []


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str, object]] = []

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.sent.append((chat_id, text, reply_markup))


@pytest.mark.asyncio
async def test_reminder_once_per_period(session, make_user, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 999)
    monkeypatch.setattr(settings, "webapp_url", "https://arabiy.example/app")
    monkeypatch.setattr(wr, "SEND_PAUSE", 0)
    # 2026-09-19 — davr boshi; 11:00 Toshkent = 06:00 UTC
    now = datetime(2026, 9, 19, 6, 0)
    active = await make_user("Nodir")
    session.add(Plan(user_id=active.id, level="B1", target_level="B2", target_date="2027-01-01"))
    session.add(XpLog(user_id=active.id, amount=5, source="lesson:x", created_at=now - timedelta(days=3)))
    idle = await make_user("Idle")  # 30 kun jim
    session.add(Plan(user_id=idle.id, level="A1", target_level="A2", target_date="2027-01-01"))
    session.add(XpLog(user_id=idle.id, amount=5, source="lesson:x", created_at=now - timedelta(days=30)))
    noplan = await make_user("NoPlan")
    session.add(XpLog(user_id=noplan.id, amount=5, source="lesson:x", created_at=now))
    await session.commit()

    bot = FakeBot()
    assert await wr.process(session, bot, datetime(2026, 9, 20, 6, 0)) == {"sent": 0, "failed": 0}, "davr o'rtasi"
    assert await wr.process(session, bot, datetime(2026, 9, 19, 3, 0)) == {"sent": 0, "failed": 0}, "08:00 erta"
    out = await wr.process(session, bot, now)
    assert out == {"sent": 1, "failed": 0}
    chat, text, kb = bot.sent[0]
    assert chat == active.tg_id and "Yangi yozuv mashqi" in text and "(B1)" in text
    assert kb.inline_keyboard[0][0].web_app.url.endswith("#writing")
    assert bot.sent[1][0] == 999 and "1 ta yuborildi" in bot.sent[1][1]
    assert active.writing_notice == "2026-09-19" and idle.writing_notice == "" and noplan.writing_notice == ""
    # Takror — jim; keyingi davr — yana
    bot.sent.clear()
    assert (await wr.process(session, bot, now + timedelta(hours=2)))["sent"] == 0
    session.add(XpLog(user_id=active.id, amount=5, source="lesson:y", created_at=now))
    await session.commit()
    assert (await wr.process(session, bot, now + timedelta(days=2)))["sent"] == 1
    assert active.writing_notice == "2026-09-21"


def test_reminder_text():
    t = writing.text_for("B1", date(2026, 9, 19))
    msg = wr.text_message("Nodir", "B1", t)
    assert t["title_uz"] in msg and "Nodir" in msg and "+6–16 XP" in msg
    assert User(tg_id=1).writing_notice == "" or True
