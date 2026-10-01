"""K30 VIP so'rovnomasi: auditoriya qoidalari, yuborish (dublikatsiz), tugmali oqim, erkin javob, hisobot, admin buyruqlari."""

import re
from collections import Counter
from datetime import datetime, timedelta

import pytest
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Chat, Message, Update, User as TgUser, Voice
from sqlalchemy import select

from config import settings
from db.models import Feedback, PaymentRequest, TutorTurn, User, VipSurvey, XpLog, utcnow
from services import vip_survey as vs

ADMIN_ID = 777001
L = dict(vs.LIKED)  # yoqqan belgilar yorlig'i (kalit → matn)
I = dict(vs.ISSUES)  # kamchilik belgilari yorlig'i
NOW = datetime(2026, 10, 1, 12, 0, 0)  # 17:00 Toshkent


class FakeBot:
    """Xizmat qatlami uchun: yuborilganlarni yig'adi; `fail` ro'yxatdagi chatlarga yetmaydi (bloklagan)."""

    def __init__(self, fail=()):
        self.sent: list[tuple[int, str, object]] = []
        self.fail = set(fail)

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        if chat_id in self.fail:
            raise RuntimeError("Forbidden: bot was blocked by the user")
        self.sent.append((chat_id, text, reply_markup))


@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    monkeypatch.setattr(settings, "admin_id", ADMIN_ID)
    monkeypatch.setattr(vs, "SEND_PAUSE", 0)


def _data(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def _texts_of(markup) -> list[str]:
    return [b.text for row in markup.inline_keyboard for b in row]


async def _vip(session, make_user, name="Ali", *, until, trial=False, turns=vs.MIN_TURNS, **kw):
    u = await make_user(name, vip_until=until, **kw)
    if trial:
        u.trial_until = until
    session.add_all([TutorTurn(user_id=u.id, session_key="s") for _ in range(turns)])
    await session.commit()
    return u


async def _invited(session, make_user, name="Zamira", segment="paid", **kw):
    u = await make_user(name, **kw)
    session.add(VipSurvey(user_id=u.id, segment=segment))
    await session.commit()
    return u


async def _row(session, user) -> VipSurvey:
    await session.refresh(user)
    return (await session.execute(select(VipSurvey).where(VipSurvey.user_id == user.id))).scalar_one()


# ─────────────────────────── Auditoriya ───────────────────────────


async def test_audience_rules_and_segments(session, make_user):
    paid = await _vip(session, make_user, "Paid", until=NOW + timedelta(days=10))
    session.add(PaymentRequest(user_id=paid.id, plan="1oy", amount=40_000, status="approved"))
    trial_ended = await _vip(session, make_user, "TrialEnded", until=NOW - timedelta(days=3), trial=True)
    gift = await _vip(session, make_user, "Gift", until=NOW + timedelta(days=2))
    # chetda qoladiganlar
    await _vip(session, make_user, "TrialRunning", until=NOW + timedelta(days=1), trial=True)  # sinov davom etmoqda
    await _vip(session, make_user, "JustExpired", until=NOW - timedelta(hours=3))  # «VIP tugadi» xabari hozirgina ketgan
    await _vip(session, make_user, "Few", until=NOW + timedelta(days=10), turns=vs.MIN_TURNS - 1)
    await _vip(session, make_user, "Muted", until=NOW + timedelta(days=10), notify_off="survey")
    asked = await _vip(session, make_user, "Asked", until=NOW + timedelta(days=10))
    session.add(VipSurvey(user_id=asked.id))
    # umuman tanlanmaydiganlar
    await make_user("NeverVip")
    await _vip(session, make_user, "Demo", until=NOW + timedelta(days=10), is_demo=1)
    admin = await _vip(session, make_user, "Admin", until=NOW + timedelta(days=10))
    session.add(User(tg_id=-7, name="Neg", vip_until=NOW + timedelta(days=5)))
    await session.commit()

    import config

    config.settings.admin_id = admin.tg_id
    aud = await vs.audience(session, NOW)
    assert [(t.name, t.segment) for t in aud.targets] == [
        ("Paid", "paid"), ("TrialEnded", "trial"), ("Gift", "gift"),
    ]
    assert aud.skipped == Counter(early=2, few=1, muted=1, asked=1)
    assert aud.targets[0].tg_id == paid.tg_id and aud.targets[1].user_id == trial_ended.id and aud.targets[2].user_id == gift.id


async def test_preview_text(session, make_user):
    empty = vs.preview_text(await vs.audience(session, NOW))
    assert "Hozircha yuboriladigan o'quvchi yo'q" in empty and "blockquote" not in empty

    await _vip(session, make_user, "Paid", until=NOW + timedelta(days=10))
    await _vip(session, make_user, "Trial", until=NOW - timedelta(days=3), trial=True)
    await _vip(session, make_user, "Few", until=NOW + timedelta(days=10), turns=0)
    text = vs.preview_text(await vs.audience(session, NOW), "Admin")
    assert "Yuboriladi: <b>2</b>" in text and "🎁 Sinovchi: 1" in text and "🎀 Sovg'a VIP: 1" in text
    assert "ustozdan 3 martadan kam foydalangan: 1" in text
    assert "<blockquote>" in text and "/vip_sorov test" in text


# ─────────────────────────── Yuborish ───────────────────────────


async def test_send_invites_personal_failures_retry_and_no_duplicates(session, make_user):
    a = await _vip(session, make_user, "Ali", until=NOW + timedelta(days=10))
    b = await _vip(session, make_user, "Bobur", until=NOW + timedelta(days=10))
    bot = FakeBot(fail={b.tg_id})
    aud = await vs.audience(session, NOW)
    assert await vs.send_invites(session, bot, aud.targets) == (1, 1)
    chat, text, kb = bot.sent[0]
    assert chat == a.tg_id and "Ali" in text and "VIP haqida fikringiz kerak" in text and "+20 XP" in text
    assert _data(kb) == ["vs:go", "vs:no"]
    row = await _row(session, a)
    assert row.step == "invited" and row.segment == "gift"
    # yetmagan odamga qator qolmaydi — «yuborilgan» soni to'g'ri; keyingi safar qayta uriniladi
    assert (await session.execute(select(VipSurvey).where(VipSurvey.user_id == b.id))).scalar_one_or_none() is None
    aud2 = await vs.audience(session, NOW)
    assert [t.name for t in aud2.targets] == ["Bobur"] and aud2.skipped["asked"] == 1
    good = FakeBot()
    assert await vs.send_invites(session, good, aud2.targets) == (1, 0)
    assert (await vs.audience(session, NOW)).targets == []


async def test_send_invites_skips_already_invited_by_parallel_run(session, make_user):
    a = await _vip(session, make_user, "Ali", until=NOW + timedelta(days=10))
    aud = await vs.audience(session, NOW)
    # ikkinchi jarayon (ikki marta bosish) shu orada qatorni yozib ulgurdi
    session.add(VipSurvey(user_id=a.id))
    await session.commit()
    bot = FakeBot()
    assert await vs.send_invites(session, bot, aud.targets) == (0, 0)
    assert bot.sent == []


async def test_send_test_resets_and_is_excluded_from_report(session, make_user):
    admin = await make_user("Admin")
    settings.admin_id = admin.tg_id
    bot = FakeBot()
    assert await vs.send_test(session, bot, admin)
    row = await _row(session, admin)
    row.step, row.rating = "done", 5
    await session.commit()
    assert await vs.send_test(session, bot, admin)  # qayta sinash — noldan
    assert (await _row(session, admin)).step == "invited" and len(bot.sent) == 2
    assert bot.sent[0][0] == admin.tg_id and _data(bot.sent[0][2]) == ["vs:go", "vs:no"]
    assert (await vs.report(session)).invited == 0


# ─────────────────────────── Oqim ───────────────────────────


async def test_full_flow_structured_then_free_text(session, make_user):
    u = await _invited(session, make_user, "Zamira", username="zam", segment="paid")
    bot = FakeBot()

    s = await vs.handle(session, bot, u, "vs:go")
    assert "1/4" in s.text and _data(s.markup) == [f"vs:r:{n}" for n in range(1, 6)]
    s = await vs.handle(session, bot, u, "vs:r:4")
    assert "2/4" in s.text and "vs:l:chat" in _data(s.markup)
    await vs.handle(session, bot, u, "vs:l:voice")
    s = await vs.handle(session, bot, u, "vs:l:chat")
    assert (await _row(session, u)).liked == "chat,voice"  # katalog tartibida
    assert f"✅ {L['voice']}" in _texts_of(s.markup) and f"✅ {L['chat']}" in _texts_of(s.markup)
    await vs.handle(session, bot, u, "vs:l:voice")  # qayta bosish — belgini oladi
    assert (await _row(session, u)).liked == "chat"

    s = await vs.handle(session, bot, u, "vs:n")
    assert "3/4" in s.text and "vs:i:none" in _data(s.markup)
    await vs.handle(session, bot, u, "vs:i:limit")
    await vs.handle(session, bot, u, "vs:i:price")
    assert (await _row(session, u)).issues == "price,limit"
    await vs.handle(session, bot, u, "vs:i:none")  # «Kamchilik yo'q» boshqalarni siqib chiqaradi
    assert (await _row(session, u)).issues == "none"
    await vs.handle(session, bot, u, "vs:i:price")  # va aksincha
    assert (await _row(session, u)).issues == "price"

    assert bot.sent == []  # erkin javobgacha adminga bildirishnoma ketmaydi
    s = await vs.handle(session, bot, u, "vs:n")
    row = await _row(session, u)
    assert row.step == "text" and row.answered_at is not None and u.survey_pending == vs.PENDING
    assert "4/4" in s.text and "+20 XP" in s.text and s.toast == "+20 XP" and _data(s.markup) == ["vs:sk"]
    xps = (await session.execute(select(XpLog.amount).where(XpLog.user_id == u.id, XpLog.source == "vip_survey"))).scalars().all()
    assert xps == [20]

    reply = await vs.record_text(session, bot, u, "  Limitni oshiring, ustoz tezroq bo'lsin  ")
    assert "Rahmat" in reply.text and "o'qib chiqamiz" in reply.text
    row = await _row(session, u)
    fb = (await session.execute(select(Feedback))).scalar_one()
    assert (fb.source, fb.context, fb.text, fb.user_id) == ("vip_survey", "vip", "Limitni oshiring, ustoz tezroq bo'lsin", u.id)
    assert row.step == "done" and row.text == fb.text and row.feedback_id == fb.id and u.survey_pending == 0
    chat, admin_msg, _ = bot.sent[-1]
    assert chat == ADMIN_ID and f"#F{fb.id}" in admin_msg and "4/5" in admin_msg
    assert L["chat"] in admin_msg and I["price"] in admin_msg and "💳 To'lagan" in admin_msg
    assert "Limitni oshiring" in admin_msg and f"/sharh {fb.id}" in admin_msg  # 4 ball — sharh sifatida taklif


async def test_skip_text_notifies_admin_without_feedback_and_xp_once(session, make_user):
    u = await _invited(session, make_user, "Vali")
    session.add(XpLog(user_id=u.id, amount=20, source="vip_survey"))  # allaqachon olingan (masalan, test)
    await session.commit()
    bot = FakeBot()
    for data in ("vs:go", "vs:r:2", "vs:n", "vs:n"):
        s = await vs.handle(session, bot, u, data)
    assert "+20 XP" not in s.text and s.toast == ""  # ikkinchi marta XP berilmaydi
    s = await vs.handle(session, bot, u, "vs:sk")
    row = await _row(session, u)
    assert row.step == "done" and u.survey_pending == 0 and "Rahmat" in s.text and "o'qib chiqamiz" not in s.text
    assert (await session.execute(select(Feedback))).scalars().all() == []
    assert len((await session.execute(select(XpLog).where(XpLog.user_id == u.id))).scalars().all()) == 1
    chat, msg, _ = bot.sent[-1]
    assert chat == ADMIN_ID and "#F" not in msg and "2/5" in msg and "👍 —" in msg and "/sharh" not in msg


async def test_stale_and_invalid_buttons_change_nothing(session, make_user):
    u = await _invited(session, make_user, "Ali")
    bot = FakeBot()
    # taklif bosqichida baho/belgi tugmalari ishlamaydi — taklif qayta ko'rsatiladi
    s = await vs.handle(session, bot, u, "vs:r:5")
    assert "VIP haqida fikringiz kerak" in s.text and (await _row(session, u)).rating == 0
    await vs.handle(session, bot, u, "vs:go")
    await vs.handle(session, bot, u, "vs:go")  # ikki marta «Boshlash»
    assert (await _row(session, u)).step == "rate"
    for bad in ("vs:r:9", "vs:r:0", "vs:r:x", "vs:r", "vs:zzz", "vs:", "vs:l:chat", "vs:n"):
        await vs.handle(session, bot, u, bad)
    row = await _row(session, u)
    assert (row.step, row.rating, row.liked) == ("rate", 0, "")
    await vs.handle(session, bot, u, "vs:r:5")
    await vs.handle(session, bot, u, "vs:r:1")  # eskirgan baho tugmasi — o'zgartirmaydi
    await vs.handle(session, bot, u, "vs:l:bogus")  # katalogda yo'q kalit
    assert (await _row(session, u)).rating == 5 and (await _row(session, u)).liked == ""
    # «Orqaga»
    assert "1/4" in (await vs.handle(session, bot, u, "vs:b")).text
    await vs.handle(session, bot, u, "vs:r:3")
    await vs.handle(session, bot, u, "vs:n")
    assert "2/4" in (await vs.handle(session, bot, u, "vs:b")).text  # issues → liked
    # yakunlangandan keyin hech narsa o'zgarmaydi
    await vs.handle(session, bot, u, "vs:n")
    await vs.handle(session, bot, u, "vs:n")
    await vs.handle(session, bot, u, "vs:n")
    await vs.handle(session, bot, u, "vs:sk")
    s = await vs.handle(session, bot, u, "vs:r:1")
    row = await _row(session, u)
    assert (row.step, row.rating) == ("done", 3) and "Rahmat" in s.text
    assert (await vs.handle(session, bot, u, "vs:b")).text == s.text


async def test_decline_is_final_and_excluded_from_audience(session, make_user):
    u = await _vip(session, make_user, "Ali", until=NOW + timedelta(days=10))
    assert await vs.send_invites(session, FakeBot(), (await vs.audience(session, NOW)).targets) == (1, 0)
    s = await vs.handle(session, FakeBot(), u, "vs:no")
    assert "/fikr" in s.text and (await _row(session, u)).step == "declined"
    await vs.handle(session, FakeBot(), u, "vs:go")  # rad etgandan keyin «Boshlash» eskirgan
    assert (await _row(session, u)).step == "declined"
    assert (await vs.audience(session, NOW)).targets == []  # qayta so'ralmaydi


async def test_missing_row_gives_only_a_toast(session, make_user):
    u = await make_user("Yangi")
    s = await vs.handle(session, FakeBot(), u, "vs:go")
    assert s.text == "" and s.toast == "So'rovnoma eskirgan"


async def test_free_text_ttl_wrong_step_empty_and_voice(session, make_user):
    bot = FakeBot()
    # eskirgan kutish: tasodifiy xabar fikr bo'lib ketmaydi, kutish tozalanadi, tuzilmali javob saqlanadi
    old = await _invited(session, make_user, "Old")
    row = await _row(session, old)
    row.step, row.rating, row.answered_at = "text", 4, NOW
    row.updated_at = utcnow() - vs.TEXT_TTL - timedelta(hours=1)
    old.survey_pending = vs.PENDING
    await session.commit()
    assert await vs.record_text(session, bot, old, "salom") is None
    assert old.survey_pending == 0 and (await _row(session, old)).step == "text"
    # so'rov qadamida emas
    mid = await _invited(session, make_user, "Mid")
    mid.survey_pending = vs.PENDING
    await session.commit()
    assert await vs.record_text(session, bot, mid, "salom") is None and mid.survey_pending == 0
    # bo'sh xabar — kutish davom etadi
    fresh = await _invited(session, make_user, "Fresh")
    row = await _row(session, fresh)
    row.step, row.rating = "text", 5
    fresh.survey_pending = vs.PENDING
    await session.commit()
    assert await vs.record_text(session, bot, fresh, "   ") is None and fresh.survey_pending == vs.PENDING
    # ovozdan o'girilgan matn — 🎤 belgisi bilan (STT xatosi bo'lishi mumkin)
    r = await vs.record_text(session, bot, fresh, "Ustoz zo'r", kind="voice")
    assert r is not None
    assert (await session.execute(select(Feedback.text))).scalar_one() == "🎤 Ustoz zo'r"
    assert bot.sent and bot.sent[-1][0] == ADMIN_ID
    # uzun matn qisqartiriladi
    long = await _invited(session, make_user, "Long")
    row = await _row(session, long)
    row.step, row.rating = "text", 3
    await session.commit()
    await vs.record_text(session, bot, long, "x" * 5000)
    assert len((await _row(session, long)).text) == vs.MAX_TEXT


def test_keyboards_fit_telegram_limits_and_html_is_escaped():
    row = VipSurvey(user_id=1, liked="", issues="", text="")  # bazaga yozilmagan: standart qiymatlar INSERT paytida qo'llanadi
    for step in ("invited", "rate", "liked", "issues", "text", "done", "declined"):
        row.step = step
        scr = vs.screen_for(row, "Ali", xp=20)
        for cd in (_data(scr.markup) if scr.markup else []):
            assert len(cd.encode()) <= 64
        for label in (_texts_of(scr.markup) if scr.markup else []):
            assert len(label) <= 40
    assert "&lt;b&gt;x" in vs.invite_text("<b>x") and "<b>x" not in vs.invite_text("<b>x")
    assert "do'stim" in vs.invite_text("...")  # harfsiz ism o'rniga zaxira
    assert vs.toggle("issues", "price", "none") == "none" and vs.toggle("liked", "", "none") == ""


# ─────────────────────────── Hisobot ───────────────────────────


async def _answered(session, make_user, name, *, rating, liked="", issues="", text="", segment="paid", **kw):
    u = await make_user(name, **kw)
    fb_id = 0
    if text:
        fb = Feedback(user_id=u.id, text=text, source="vip_survey", context="vip")
        session.add(fb)
        await session.flush()
        fb_id = fb.id
    session.add(VipSurvey(
        user_id=u.id, step="done" if text else "text", segment=segment, rating=rating, liked=liked, issues=issues,
        text=text, feedback_id=fb_id, answered_at=NOW,
    ))
    await session.commit()
    return u


async def test_report_aggregates_excludes_admin_and_formats(session, make_user):
    await _answered(session, make_user, "Ali", rating=5, liked="chat,mock", issues="none", text="Zo'r <b>ustoz</b>")
    await _answered(session, make_user, "Vali", rating=3, liked="chat", issues="price,limit", segment="trial")
    await _invited(session, make_user, "Declined")
    row = (await session.execute(select(VipSurvey).order_by(VipSurvey.id.desc()))).scalars().first()
    row.step = "declined"
    await _invited(session, make_user, "Unopened")
    mid = await _invited(session, make_user, "Mid")
    (await _row(session, mid)).step = "liked"
    admin = await _answered(session, make_user, "Admin", rating=1, liked="price", issues="bug", text="admin sinovi")
    settings.admin_id = admin.tg_id
    await session.commit()

    rep = await vs.report(session)
    assert (rep.invited, rep.answered, rep.declined, rep.unopened, rep.in_progress) == (5, 2, 1, 1, 1)
    assert rep.rating_avg == 4.0 and rep.rating_dist == Counter({5: 1, 3: 1})
    assert rep.liked == Counter(chat=2, mock=1) and rep.issues == Counter(none=1, price=1, limit=1)
    assert rep.segments == {"paid": (1, 5.0), "trial": (1, 3.0)}
    assert rep.with_text == 1 and [c[1].name for c in rep.comments] == ["Ali"]

    text = vs.report_text(rep)
    assert "Yuborilgan: <b>5</b>" in text and "Javob berdi: <b>2</b> (40%)" in text
    assert "yarim qoldirdi: 1" in text and "rad etdi: 1" in text and "ochmadi: 1" in text
    assert "O'rtacha baho: <b>4.0</b>/5" in text
    assert f"{L['chat']} — <b>2</b> (100%)" in text and f"{L['mock']} — <b>1</b> (50%)" in text
    assert text.index(L["chat"]) < text.index(L["mock"])  # ko'pi birinchi
    assert f"{I['price']} — <b>1</b> (50%)" in text and f"{I['none']} — <b>1</b>" in text
    assert "💳 To'lagan: 1 ta · ⭐ 5.0" in text and "🎁 Sinovchi: 1 ta · ⭐ 3.0" in text
    assert "Zo'r &lt;b&gt;ustoz&lt;/b&gt;" in text and "admin sinovi" not in text
    assert vs.report_text(await vs.report(session, 0)).count("#F") == 0  # takliflarsiz

    assert vs.report_text(vs.Report()).startswith("👑 VIP so'rovnomasi hali yuborilmagan")
    only_sent = await vs.report(session)
    only_sent.answered = 0
    assert "Tugallangan javob hali yo'q" in vs.report_text(only_sent)


_TG_TAGS = re.compile(r"</?(b|i|u|s|code|pre|blockquote)>")
_TG_ENTITIES = re.compile(r"&(lt|gt|amp|quot);")


def _assert_telegram_html(text: str):
    """Telegram HTML: faqat ruxsat etilgan teglar, hammasi yopilgan, qolgan `<` `>` `&` — entity ko'rinishida.
    Buzilsa Telegram butun xabarni rad etadi (ommaviy yuborishda hech kimga yetmaydi)."""
    stack = []
    for m in re.finditer(r"<(/?)(\w+)>", text):
        closing, tag = m.group(1) == "/", m.group(2)
        assert tag in {"b", "i", "u", "s", "code", "pre", "blockquote"}, f"ruxsat etilmagan teg <{tag}>"
        if closing:
            assert stack and stack.pop() == tag, f"yopilish mos emas: </{tag}>"
        else:
            stack.append(tag)
    assert not stack, f"yopilmagan teglar: {stack}"
    bare = _TG_ENTITIES.sub("", _TG_TAGS.sub("", text))
    assert not re.search(r"[<>&]", bare), f"ekranlanmagan belgi: {bare!r}"


async def test_every_outgoing_html_text_is_valid_for_telegram(session, make_user):
    nasty = "<b>Ali</b> & <i>Vali"
    u = await make_user(nasty, username="a&b")
    u.vip_until = NOW + timedelta(days=5)
    session.add_all([TutorTurn(user_id=u.id, session_key="s") for _ in range(vs.MIN_TURNS)])
    await session.commit()

    texts = [vs.invite_text(nasty), vs.invite_text(None), vs.invite_text("...")]
    row = VipSurvey(user_id=u.id, liked="chat,voice", issues="price,none", text="<script>&x</script> 5 > 3", rating=5, segment="paid")
    for step in ("invited", "rate", "liked", "issues", "text", "done", "declined"):
        row.step = step
        texts.append(vs.screen_for(row, nasty, xp=20).text)
    fb = Feedback(id=7, user_id=u.id, text=row.text, source="vip_survey")
    texts += [vs.admin_text(row, u, fb), vs.admin_text(row, u)]
    texts.append(vs.preview_text(await vs.audience(session, NOW), nasty))
    texts.append(vs.preview_text(vs.Audience([])))
    rep = vs.Report(invited=3, answered=2, rating_avg=4.5, rating_dist=Counter({5: 1, 4: 1}), liked=Counter(chat=2),
                    issues=Counter(price=1), segments={"paid": (2, 4.5)}, with_text=1, comments=[(row, u)])
    row.feedback_id = 7
    texts += [vs.report_text(rep), vs.report_text(vs.Report()), vs.report_text(vs.Report(invited=2))]
    assert len(texts) > 12
    for t in texts:
        _assert_telegram_html(t)
        assert len(t) < 4096


def test_html_checker_itself_catches_problems():
    for bad in ("<b>ochiq", "yopiq</b>", "<br>", "a < b", "Q&A", "<b><i></b></i>"):
        with pytest.raises(AssertionError):
            _assert_telegram_html(bad)
    _assert_telegram_html("<b>ok</b> &lt;x&gt; &amp; <blockquote>y</blockquote>")


def test_chunks_split_on_line_boundaries():
    text = "\n".join(f"<b>qator {i}</b> " + "x" * 50 for i in range(200))
    parts = vs.chunks(text, 1000)
    assert len(parts) > 5 and all(len(p) <= 1000 for p in parts)
    assert "\n".join(parts) == text and all(p.count("<b>") == p.count("</b>") for p in parts)


# ─────────────────────────── Bot orqali (handlerlar + admin buyruqlari) ───────────────────────────


class FakeSession:
    def __init__(self):
        self.calls = []

    async def __call__(self, bot, method, timeout=None):
        self.calls.append(method)
        return None

    async def close(self):
        pass


def _msg(text, from_id, voice=None):
    chat = Chat(id=from_id, type="private")
    u = TgUser(id=from_id, is_bot=False, first_name="Admin" if from_id == ADMIN_ID else "X")
    return Message(message_id=2, date=datetime.now(), chat=chat, from_user=u, text=text, voice=voice)


def _cb(data, from_id):
    chat = Chat(id=from_id, type="private")
    u = TgUser(id=from_id, is_bot=False, first_name="X")
    m = Message(message_id=3, date=datetime.now(), chat=chat, from_user=u, text="so'rov")
    return CallbackQuery(id="1", from_user=u, chat_instance="c", data=data, message=m)


@pytest.fixture
def wired(session_factory, monkeypatch):
    from bot import admin as admin_mod, handlers as h_mod
    from bot.admin import router as admin_router
    from bot.handlers import router as bot_router

    monkeypatch.setattr(admin_mod, "SessionLocal", session_factory)
    monkeypatch.setattr(h_mod, "SessionLocal", session_factory)
    bot = Bot(token="42:TESTTOKEN")
    bot.session = FakeSession()
    dp = Dispatcher()
    dp.include_router(admin_router)
    dp.include_router(bot_router)
    yield dp, bot
    admin_router._parent_router = None
    bot_router._parent_router = None


async def _feed(wired, message=None, callback=None):
    dp, bot = wired
    upd = Update(update_id=1, message=message) if message else Update(update_id=1, callback_query=callback)
    await dp.feed_update(bot, upd)
    return bot.session.calls


def _calls(calls, kind):
    return [c for c in calls if type(c).__name__ == kind]


def _sent(calls):
    return [(c.chat_id, c.text) for c in _calls(calls, "SendMessage")]


async def test_user_walks_the_whole_flow_via_buttons(session, make_user, wired):
    u = await _invited(session, make_user, "Nodir")
    tg = u.tg_id
    calls = await _feed(wired, callback=_cb("vs:go", tg))
    edit = _calls(calls, "EditMessageText")[-1]
    assert "1/4" in edit.text and edit.parse_mode == "HTML" and _data(edit.reply_markup)[0] == "vs:r:1"
    assert _calls(calls, "AnswerCallbackQuery")
    for data in ("vs:r:5", "vs:l:chat", "vs:n", "vs:i:price"):
        calls = await _feed(wired, callback=_cb(data, tg))
    assert "3/4" in _calls(calls, "EditMessageText")[-1].text
    calls = await _feed(wired, callback=_cb("vs:n", tg))
    assert "4/4" in _calls(calls, "EditMessageText")[-1].text
    assert _calls(calls, "AnswerCallbackQuery")[-1].text == "+20 XP"
    await session.refresh(u)
    assert u.survey_pending == vs.PENDING

    # keyingi oddiy matn — erkin javob (umumiy so'rov emas)
    before = len(_sent(calls))
    calls = await _feed(wired, message=_msg("Mock imtihonlar ko'proq bo'lsin", tg))
    sent = _sent(calls)[before:]
    assert any(chat == tg and "Rahmat" in text for chat, text in sent)
    assert any(chat == ADMIN_ID and "Mock imtihonlar ko'proq bo'lsin" in text and "5/5" in text for chat, text in sent)
    fbs = (await session.execute(select(Feedback))).scalars().all()
    assert [(f.source, f.text) for f in fbs] == [("vip_survey", "Mock imtihonlar ko'proq bo'lsin")]
    await session.refresh(u)
    assert u.survey_pending == 0
    # kutish tugadi — keyingi matn e'tiborsiz
    n = len(_calls(calls, "SendMessage"))
    calls = await _feed(wired, message=_msg("yana nimadir", tg))
    assert len(_calls(calls, "SendMessage")) == n


async def test_unmodified_edit_error_is_swallowed(session, make_user, wired):
    class Raising(FakeSession):
        async def __call__(self, bot, method, timeout=None):
            self.calls.append(method)
            if type(method).__name__ == "EditMessageText":
                raise TelegramBadRequest(method=method, message="Bad Request: message is not modified")

    u = await _invited(session, make_user, "Nodir")
    wired[1].session = Raising()
    calls = await _feed(wired, callback=_cb("vs:go", u.tg_id))
    assert _calls(calls, "AnswerCallbackQuery") and (await _row(session, u)).step == "rate"
    assert _calls(calls, "SendMessage") == []  # «o'zgarmadi» — qo'shimcha xabar kerak emas


async def test_edit_failure_falls_back_to_a_new_message(session, make_user, wired):
    class Raising(FakeSession):
        async def __call__(self, bot, method, timeout=None):
            self.calls.append(method)
            if type(method).__name__ == "EditMessageText":
                raise TelegramBadRequest(method=method, message="Bad Request: message to edit not found")

    u = await _invited(session, make_user, "Nodir")
    wired[1].session = Raising()
    calls = await _feed(wired, callback=_cb("vs:go", u.tg_id))
    (sent,) = _calls(calls, "SendMessage")
    assert sent.chat_id == u.tg_id and "1/4" in sent.text and _data(sent.reply_markup)[0] == "vs:r:1"


async def test_voice_answer_is_transcribed_into_vip_survey(session, make_user, wired, monkeypatch):
    from services import stt

    u = await _invited(session, make_user, "Ali")
    row = await _row(session, u)
    row.step, row.rating = "text", 4
    u.survey_pending = vs.PENDING
    await session.commit()
    monkeypatch.setattr(stt, "available", lambda: True)

    async def fake_transcribe(audio, filename="", mime="", prompt="", lang="ar"):
        assert lang == "uz"
        return "Ovoz tanish yaxshi bo'lsin"

    monkeypatch.setattr(stt, "transcribe", fake_transcribe)

    class F:
        file_path = "voice/1.ogg"

    class Buf:
        def read(self):
            return b"OggS"

    dp, bot = wired

    async def get_file(file_id):
        return F()

    async def download_file(path):
        return Buf()

    monkeypatch.setattr(bot, "get_file", get_file)
    monkeypatch.setattr(bot, "download_file", download_file)
    calls = await _feed(wired, message=_msg(None, u.tg_id, voice=Voice(file_id="v1", file_unique_id="u1", duration=9)))
    assert any(chat == u.tg_id and "Rahmat" in text for chat, text in _sent(calls))
    fb = (await session.execute(select(Feedback))).scalar_one()
    assert fb.source == "vip_survey" and fb.text == "🎤 Ovoz tanish yaxshi bo'lsin"


async def test_general_survey_text_path_still_works(session, make_user, wired):
    u = await make_user("Umumiy")
    u.survey_pending = 1
    await session.commit()
    calls = await _feed(wired, message=_msg("Hammasi zo'r", u.tg_id))
    assert any("Rahmat" in text and "+10 XP" in text for _, text in _sent(calls))
    assert (await session.execute(select(Feedback.source))).scalar_one() == "survey"


async def test_stale_pending_without_text_step_is_ignored_and_cleared(session, make_user, wired):
    u = await _invited(session, make_user, "Ali")  # qator «invited» — erkin javob kutilmayapti
    u.survey_pending = vs.PENDING
    await session.commit()
    calls = await _feed(wired, message=_msg("shunchaki xabar", u.tg_id))
    assert _sent(calls) == [] and (await session.execute(select(Feedback))).scalars().all() == []
    await session.refresh(u)
    assert u.survey_pending == 0


async def test_admin_preview_confirm_send_and_double_tap(session, make_user, wired):
    a = await _vip(session, make_user, "Ali", until=NOW + timedelta(days=10))
    b = await _vip(session, make_user, "Bobur", until=NOW - timedelta(days=5), trial=True)
    await _vip(session, make_user, "Few", until=NOW + timedelta(days=10), turns=0)
    # admin emas — jim
    calls = await _feed(wired, message=_msg("/vip_sorov", a.tg_id))
    assert _sent(calls) == []
    # admin: oldindan ko'rish — yubormaydi
    calls = await _feed(wired, message=_msg("/vip_sorov", ADMIN_ID))
    (chat, preview), = _sent(calls)
    kb = _calls(calls, "SendMessage")[-1].reply_markup
    assert chat == ADMIN_ID and "Yuboriladi: <b>2</b>" in preview and "Admin" in preview
    assert _data(kb) == ["vsa:send", "vsa:no"] and "2 ta o'quvchiga yuborish" in _texts_of(kb)[0]
    assert (await session.execute(select(VipSurvey))).scalars().all() == []
    # begona tugmani bossa — rad
    calls = await _feed(wired, callback=_cb("vsa:send", a.tg_id))
    assert _calls(calls, "AnswerCallbackQuery")[-1].show_alert and (await session.execute(select(VipSurvey))).scalars().all() == []
    # bekor — yuborilmaydi
    await _feed(wired, callback=_cb("vsa:no", ADMIN_ID))
    assert (await session.execute(select(VipSurvey))).scalars().all() == []
    # tasdiq — ikkalasiga, shaxsiy matn va tugmalar bilan
    calls = await _feed(wired, callback=_cb("vsa:send", ADMIN_ID))
    invites = {c.chat_id: c for c in _calls(calls, "SendMessage") if c.chat_id in (a.tg_id, b.tg_id)}
    assert set(invites) == {a.tg_id, b.tg_id}
    assert "Ali" in invites[a.tg_id].text and "Bobur" in invites[b.tg_id].text
    assert _data(invites[a.tg_id].reply_markup) == ["vs:go", "vs:no"]
    assert any(chat == ADMIN_ID and "Yuborildi: 2" in text and "/vip_natija" in text for chat, text in _sent(calls))
    assert {r.user_id: r.segment for r in (await session.execute(select(VipSurvey))).scalars()} == {a.id: "gift", b.id: "trial"}
    # ikkinchi bosish (ikki marta tap) — hech kimga qayta ketmaydi
    n = len([c for c in _calls(calls, "SendMessage") if c.chat_id in (a.tg_id, b.tg_id)])
    calls = await _feed(wired, callback=_cb("vsa:send", ADMIN_ID))
    assert len([c for c in _calls(calls, "SendMessage") if c.chat_id in (a.tg_id, b.tg_id)]) == n
    assert any("Yuborildi: 0" in text for _, text in _sent(calls))


async def test_admin_preview_with_nobody_has_no_send_button(session, make_user, wired):
    calls = await _feed(wired, message=_msg("/vip_sorov", ADMIN_ID))
    assert _calls(calls, "SendMessage")[-1].reply_markup is None
    assert "Hozircha yuboriladigan o'quvchi yo'q" in _sent(calls)[-1][1]


async def test_admin_test_walkthrough_and_results(session, make_user, wired):
    admin = await make_user("Admin")
    settings.admin_id = admin.tg_id
    await session.commit()
    # admin o'zini yaratmagan bo'lsa ham test ishlaydi (tg_id bo'yicha); bu yerda mavjud
    calls = await _feed(wired, message=_msg("/vip_sorov test", admin.tg_id))
    sent = _calls(calls, "SendMessage")
    assert sent[0].chat_id == admin.tg_id and _data(sent[0].reply_markup) == ["vs:go", "vs:no"]
    assert "hisobotga kirmaydi" in sent[-1].text
    # real javob berilgan o'quvchi va /vip_natija
    await _answered(session, make_user, "Ali", rating=5, liked="chat", issues="none", text="Zo'r")
    calls = await _feed(wired, message=_msg("/vip_natija", admin.tg_id))
    report = _sent(calls)[-1][1]
    assert "Yuborilgan: <b>1</b>" in report and "Zo'r" in report and "O'rtacha baho: <b>5.0</b>/5" in report
    # admin emas — jim
    n = len(_calls(calls, "SendMessage"))
    calls = await _feed(wired, message=_msg("/vip_natija", 12345))
    assert len(_calls(calls, "SendMessage")) == n


async def test_general_sorov_does_not_clobber_vip_text_wait(session, make_user, wired, monkeypatch):
    from bot import admin as admin_mod

    waiting = await _invited(session, make_user, "Waiting")
    waiting.survey_pending = vs.PENDING
    other = await make_user("Other")
    await session.commit()

    async def fake_blast(bot, ids, text, **kw):
        return len(ids), 0

    monkeypatch.setattr(admin_mod, "_blast", fake_blast)
    await _feed(wired, message=_msg("/sorov", ADMIN_ID))
    await session.refresh(waiting)
    await session.refresh(other)
    assert waiting.survey_pending == vs.PENDING and other.survey_pending == 1
