"""VIP so'rovnomasi (K30) — VIP'ni sinagan o'quvchilardan: nima yoqdi, qanday kamchilik bor, nimani qo'shish kerak.

Nega alohida: umumiy `/sorov` (services/survey.py) butun ilova haqida erkin fikr so'raydi. VIP tarifni (narx, limit,
ustoz sifati) yaxshilash uchun esa taqqoslanadigan javoblar kerak — tugmali savollar hisobotga yig'iladi (qaysi
imkoniyat yoqdi, eng ko'p kamchilik qaysi, to'laganlar va sinovchilar nima deydi), erkin matn esa batafsil taklif uchun.

Oqim — har o'quvchi uchun bitta `VipSurvey` qatori; ekran `step` dan chiziladi, shuning uchun eskirgan/ikki marta
bosilgan tugma hech narsani buzmaydi (joriy qadam qayta ko'rsatiladi):
  invited → rate (⭐1–5) → liked (nima yoqdi) → issues (kamchiliklar) → text (erkin matn yoki ovoz) → done;
  «Hozir emas» → declined.
Tuzilmali qism `issues` da «Tayyor» bosilganda yakunlanadi: shu payt +XP beriladi va javob hisobotga kiradi. Erkin javob
ixtiyoriy («O'tkazib yuborish»): kelsa `Feedback`ga (source="vip_survey") yoziladi — admin shu xabarga reply qilib javob
beradi, yoqqan fikrni /sharh qiladi. Erkin javob kutilayotganda `users.survey_pending = PENDING` (bot/handlers.py).

Auditoriya (`audience`): VIP olgan (sinov, taklif bonusi, to'lov) va ustozdan kamida MIN_TURNS marta foydalangan
o'quvchilar. Davom etayotgan sinov va yaqinda tugagan VIP chetda: ularga shu paytda «tugadi / chegirma» xabari boradi.
Admin: `/vip_sorov` (kim olishi + namuna → tasdiq tugmasi), `/vip_sorov test`, `/vip_natija`.
"""

import asyncio
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from typing import NamedTuple

from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import PaymentRequest, TutorTurn, User, VipSurvey, XpLog, utcnow
from services import feedback as feedback_svc
from services import notify_prefs, referral
from services.names import admin_show, esc, show

log = logging.getLogger(__name__)

SOURCE = "vip_survey"  # Feedback.source va XpLog.source
PENDING = 2  # users.survey_pending: keyingi matn/ovoz — shu so'rovning erkin javobi
XP = 20
MIN_TURNS = 3  # ustoz bilan kamida shuncha javob (1–2 urinish fikr aytishga yetmaydi)
COOL_OFF = timedelta(days=1)  # VIP tugaganidan keyin shuncha kutamiz — «VIP tugadi» xabari bilan to'qnashmasin
TEXT_TTL = timedelta(days=3)  # erkin javob shuncha kutiladi; keyin tasodifiy xabar fikr bo'lib qolmasin
MAX_TEXT = 1000
SEND_PAUSE = 0.05  # Telegram limitidan oshmaslik uchun (admin._blast bilan bir xil)
ANSWERED = ("text", "done")  # tuzilmali qism yakunlangan qadamlar — hisobotga shular kiradi

# (kalit, tugma yorlig'i) — tugma va hisobotda bir xil yorliq; tartib tugmalar tartibi
LIKED = [
    ("chat", "🤖 Ustoz suhbati"),
    ("voice", "🎤 Speaking"),
    ("mock", "🎯 Mock imtihon"),
    ("uz", "💬 O'zbekcha izoh"),
    ("fix", "✏️ Xato tuzatish"),
    ("quality", "🧠 Javob sifati"),
    ("limit", "🔋 Limit yetarli"),
    ("price", "💰 Narxi mos"),
]
ISSUES = [
    ("price", "💸 Narxi qimmat"),
    ("limit", "🔋 Limit kam"),
    ("slow", "🐢 Sekin ishlaydi"),
    ("wrong", "❌ Ustoz adashadi"),
    ("stt", "🎤 Ovoz tanilmadi"),
    ("few", "📚 Mavzu/mock kam"),
    ("hard", "🤔 Tushunarsiz"),
    ("pay", "💳 To'lash noqulay"),
    ("bug", "🐞 Nosozliklar"),
    ("same", "🤷 Bepuldan farqsiz"),
    ("none", "👌 Kamchilik yo'q"),
]
CATALOG = {"liked": LIKED, "issues": ISSUES}
PREFIX = {"liked": "l", "issues": "i"}  # callback_data: vs:l:<kalit> / vs:i:<kalit>
EXCLUSIVE = {"liked": "", "issues": "none"}  # boshqa belgilar bilan birga turmaydigan javob

SEGMENTS = {"paid": "💳 To'lagan", "trial": "🎁 Sinovchi", "gift": "🎀 Sovg'a VIP"}
SKIP_LABELS = {
    "asked": "avval so'ralgan",
    "muted": "so'rov xabarlarini o'chirgan",
    "few": f"ustozdan {MIN_TURNS} martadan kam foydalangan",
    "early": "hali erta (sinov davom etmoqda yoki VIP yaqinda tugagan)",
}


@dataclass
class Screen:
    """Foydalanuvchiga ko'rsatiladigan ekran: matn + tugmalar (+ qalqib chiquvchi qisqa xabar)."""

    text: str
    markup: InlineKeyboardMarkup | None = None
    toast: str = ""


# ─────────────────────────── Ekranlar ───────────────────────────


def _who(name: str | None) -> str:
    return show(name, "do'stim")


def invite_text(name: str | None) -> str:
    return (
        f"👑 <b>{_who(name)}, VIP haqida fikringiz kerak!</b>\n\n"
        "VIP imkoniyatlaridan (🤖 AI ustoz, 🎤 speaking, 🎯 mock imtihonlar) foydalandingiz — "
        "uni yaxshilashda sizning fikringiz hal qiluvchi.\n\n"
        "4 ta qisqa savol, taxminan 1 daqiqa, asosan tugmalar:\n"
        "👍 nima yoqdi\n"
        "👎 qanday kamchiliklar bor\n"
        "✍️ nimani yaxshilash yoki qo'shish kerak\n\n"
        f"🎁 Javob uchun +{XP} XP."
    )


def invite_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="👑 Boshlash", callback_data="vs:go"),
            InlineKeyboardButton(text="Hozir emas", callback_data="vs:no"),
        ]]
    )


def _rate_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=f"{n}⭐", callback_data=f"vs:r:{n}") for n in range(1, 6)]]
    )


def _chips_kb(kind: str, chosen_csv: str) -> InlineKeyboardMarkup:
    """Ko'p tanlov: tanlanganlar ✅ bilan, ikki ustun; pastda «Orqaga» va «Tayyor»."""
    chosen = set(chosen_csv.split(","))
    rows: list[list[InlineKeyboardButton]] = []
    pair: list[InlineKeyboardButton] = []
    for key, label in CATALOG[kind]:
        pair.append(
            InlineKeyboardButton(
                text=("✅ " if key in chosen else "") + label, callback_data=f"vs:{PREFIX[kind]}:{key}"
            )
        )
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([
        InlineKeyboardButton(text="◀️ Orqaga", callback_data="vs:b"),
        InlineKeyboardButton(text="Tayyor ➜", callback_data="vs:n"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def screen_for(row: VipSurvey, name: str | None, xp: int = 0) -> Screen:
    """`row.step` ga mos ekran. `xp` — shu bosishda berilgan XP (faqat «Tayyor» dan keyingi ekranda ko'rinadi)."""
    step = row.step
    if step == "rate":
        return Screen(
            "⭐ <b>1/4 — Umuman VIP sizga qanday?</b>\n\n1 — umuman yoqmadi, 5 — juda zo'r.", _rate_kb()
        )
    if step == "liked":
        return Screen(
            "👍 <b>2/4 — Nima yoqdi?</b>\n\nBir nechtasini belgilang, keyin «Tayyor» ni bosing.",
            _chips_kb("liked", row.liked),
        )
    if step == "issues":
        return Screen(
            "👎 <b>3/4 — Qanday kamchiliklar sezdingiz?</b>\n\nBir nechtasini belgilang, keyin «Tayyor» ni bosing.",
            _chips_kb("issues", row.issues),
        )
    if step == "text":
        got = f"✅ Javoblaringiz qabul qilindi — hisobingizga <b>+{xp} XP</b> qo'shildi!\n\n" if xp else ""
        return Screen(
            f"{got}✍️ <b>4/4 — Nimani yaxshilash yoki qo'shish kerak?</b> <i>(ixtiyoriy)</i>\n\n"
            "Shu chatga bitta xabar yozing — matn yoki ovozli. Qanday imkoniyat kerak, nima qiynadi, "
            "nimani o'zgartirardingiz — hammasi muhim.",
            InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="O'tkazib yuborish", callback_data="vs:sk")]]
            ),
            toast=f"+{xp} XP" if xp else "",
        )
    if step == "done":
        more = "\nYozganlaringizni o'qib chiqamiz, kerak bo'lsa javob beramiz." if row.text else ""
        return Screen(
            f"🙏 <b>Rahmat, {_who(name)}!</b>\n\nFikringiz yetib bordi — VIP tarifni aynan sizning javoblaringiz "
            f"asosida yaxshilaymiz.{more}"
        )
    if step == "declined":
        return Screen("Tushunarli, rahmat! 🙂 Fikringiz paydo bo'lsa — istalgan payt /fikr buyrug'i bilan yozing.")
    return Screen(invite_text(name), invite_kb())  # invited


def toggle(kind: str, current: str, key: str) -> str:
    """Belgini qo'yadi yoki oladi. Mutlaq javob («Kamchilik yo'q») boshqalar bilan birga turmaydi; natija katalog tartibida."""
    order = [k for k, _ in CATALOG[kind]]
    if key not in order:
        return current
    chosen = {k for k in current.split(",") if k in order}
    exclusive = EXCLUSIVE[kind]
    if key in chosen:
        chosen.discard(key)
    elif key == exclusive:
        chosen = {key}
    else:
        chosen.discard(exclusive)
        chosen.add(key)
    return ",".join(k for k in order if k in chosen)


def labels(kind: str, csv: str) -> list[str]:
    chosen = set(csv.split(","))
    return [label for key, label in CATALOG[kind] if key in chosen]


# ─────────────────────────── Oqim ───────────────────────────


async def get_row(session: AsyncSession, user: User) -> VipSurvey | None:
    return (await session.execute(select(VipSurvey).where(VipSurvey.user_id == user.id))).scalar_one_or_none()


async def _grant_xp(session: AsyncSession, user: User) -> int:
    """+XP bir marta (qayta urinish/ikki bosish ikkilantirmaydi)."""
    has = (
        await session.execute(select(XpLog.id).where(XpLog.user_id == user.id, XpLog.source == SOURCE).limit(1))
    ).scalar_one_or_none()
    if has is not None:
        return 0
    session.add(XpLog(user_id=user.id, amount=XP, source=SOURCE))
    return XP


async def handle(session: AsyncSession, bot, user: User, data: str) -> Screen:
    """`vs:<amal>[:<arg>]` tugmasi. Qaytaradi: ko'rsatiladigan ekran; qator yo'q bo'lsa — matnsiz, faqat qisqa xabar."""
    parts = (data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""
    arg = parts[2] if len(parts) > 2 else ""
    row = await get_row(session, user)
    if row is None:
        return Screen("", toast="So'rovnoma eskirgan")

    step, xp, finished = row.step, 0, False
    if action == "go" and step == "invited":
        row.step = "rate"
    elif action == "no" and step == "invited":
        row.step = "declined"
    elif action == "r" and step == "rate" and arg in ("1", "2", "3", "4", "5"):
        row.rating, row.step = int(arg), "liked"
    elif action == "l" and step == "liked":
        row.liked = toggle("liked", row.liked, arg)
    elif action == "i" and step == "issues":
        row.issues = toggle("issues", row.issues, arg)
    elif action == "b" and step in ("liked", "issues"):
        row.step = "rate" if step == "liked" else "liked"
    elif action == "n" and step == "liked":
        row.step = "issues"
    elif action == "n" and step == "issues":
        # Tuzilmali qism tayyor: hisobotga kiradi, XP beriladi, keyingi xabar — erkin javob
        row.step, row.answered_at = "text", row.answered_at or utcnow()
        user.survey_pending = PENDING
        xp = await _grant_xp(session, user)
    elif action == "sk" and step == "text":
        row.step, finished = "done", True
        if user.survey_pending == PENDING:
            user.survey_pending = 0
    # boshqa holat — eskirgan tugma: hech narsa o'zgarmaydi, joriy qadam qayta ko'rsatiladi
    row.updated_at = utcnow()
    await session.commit()
    if finished:
        await notify_admin(bot, row, user)
    return screen_for(row, user.name, xp)


async def record_text(session: AsyncSession, bot, user: User, body: str, kind: str = "text") -> Screen | None:
    """Erkin javob (matn yoki ovozdan o'girilgan). Qabul qilinmasa (so'rov yo'q/eskirgan/bo'sh) — None, xabar e'tiborsiz."""
    row = await get_row(session, user)
    text = (body or "").strip()[:MAX_TEXT]
    if row is None or row.step != "text" or utcnow() - row.updated_at > TEXT_TTL:
        user.survey_pending = 0
        await session.commit()
        return None
    if not text:
        return None
    text = ("🎤 " if kind == "voice" else "") + text
    fb = await feedback_svc.save(session, user.id, text, source=SOURCE, context="vip")
    row.text, row.feedback_id, row.step, row.updated_at = text, fb.id, "done", utcnow()
    user.survey_pending = 0
    await session.commit()
    await notify_admin(bot, row, user, fb)
    return screen_for(row, user.name)


def admin_text(row: VipSurvey, user: User, fb=None) -> str:
    """Adminga: bitta o'quvchining javobi. Erkin matn bo'lsa `#F<id>` yorlig'i bilan — reply qilib javob berish mumkin."""
    uname = f"@{user.username}" if user.username else "—"
    seg = f" · {SEGMENTS[row.segment]}" if row.segment in SEGMENTS else ""
    lines = [
        "👑 <b>VIP so'rovi</b>" + (f" #F{fb.id}" if fb else ""),
        f"{admin_show(user.name, user.username, user.tg_id)}, {esc(uname)}, ID <code>{user.tg_id}</code>{seg}",
        "",
        f"⭐ Baho: <b>{row.rating}/5</b>",
        f"👍 {esc(', '.join(labels('liked', row.liked)) or '—')}",
        f"👎 {esc(', '.join(labels('issues', row.issues)) or '—')}",
    ]
    if fb:
        lines += ["", esc(fb.text), "", f"<i>Javob berish: shu xabarga reply qiling yoki /javob {fb.id} matn</i>"]
        if row.rating >= 4:
            lines.append(f"<i>Ilovada sharh sifatida ko'rsatish: /sharh {fb.id}</i>")
    return "\n".join(lines)


async def notify_admin(bot, row: VipSurvey, user: User, fb=None) -> None:
    if not (bot and settings.admin_id):
        return
    try:
        await bot.send_message(settings.admin_id, admin_text(row, user, fb), parse_mode="HTML")
    except Exception as e:
        log.info("VIP so'rovi adminga yetmadi: %r", e)


# ─────────────────────────── Auditoriya va yuborish ───────────────────────────


class Target(NamedTuple):
    user_id: int
    tg_id: int
    name: str
    segment: str


@dataclass
class Audience:
    targets: list[Target]
    skipped: Counter = field(default_factory=Counter)  # sabab (SKIP_LABELS) → soni


def _settled(user: User, now) -> bool:
    """Fikr so'rash uchun payt keldimi: sinov davom etmayapti va VIP hozirgina tugamagan."""
    if user.vip_until > now:
        return not referral.on_trial(user)
    return now - user.vip_until >= COOL_OFF


def _segment(user: User, paid_ids: set[int]) -> str:
    if user.id in paid_ids:
        return "paid"
    return "trial" if user.trial_until is not None else "gift"


async def audience(session: AsyncSession, now=None) -> Audience:
    """Kimga yuboriladi (qoidalar modul docstring'ida). Hech narsa yozmaydi."""
    now = now or utcnow()
    q = select(User).where(User.is_demo == 0, User.tg_id > 0, User.vip_until.is_not(None))
    if settings.admin_id:
        q = q.where(User.tg_id != settings.admin_id)
    users = (await session.execute(q.order_by(User.id))).scalars().all()
    skipped: Counter = Counter()
    if not users:
        return Audience([], skipped)
    asked = set((await session.execute(select(VipSurvey.user_id))).scalars().all())
    turns = dict(
        (await session.execute(select(TutorTurn.user_id, func.count(TutorTurn.id)).group_by(TutorTurn.user_id))).all()
    )
    paid = set(
        (await session.execute(select(PaymentRequest.user_id).where(PaymentRequest.status == "approved")))
        .scalars()
        .all()
    )
    targets: list[Target] = []
    for u in users:
        if u.id in asked:
            skipped["asked"] += 1
        elif not notify_prefs.enabled(u, "survey"):
            skipped["muted"] += 1
        elif turns.get(u.id, 0) < MIN_TURNS:
            skipped["few"] += 1
        elif not _settled(u, now):
            skipped["early"] += 1
        else:
            targets.append(Target(u.id, u.tg_id, u.name, _segment(u, paid)))
    return Audience(targets, skipped)


def preview_text(aud: Audience, sample_name: str | None = None) -> str:
    """`/vip_sorov` — kimga ketishi va xabar namunasi (yuborishdan oldin admin ko'radi)."""
    n = len(aud.targets)
    lines = ["👑 <b>VIP so'rovnomasi</b>\n"]
    if n:
        by_seg = Counter(t.segment for t in aud.targets)
        lines.append(f"Yuboriladi: <b>{n}</b> ta o'quvchiga")
        lines.append(" · ".join(f"{label}: {by_seg[seg]}" for seg, label in SEGMENTS.items() if by_seg[seg]))
    else:
        lines.append("Hozircha yuboriladigan o'quvchi yo'q.")
    if aud.skipped:
        lines.append("\nChetda qolganlar:")
        lines += [f"• {label}: {aud.skipped[key]}" for key, label in SKIP_LABELS.items() if aud.skipped[key]]
    lines.append(
        f"\n<i>Kimga: VIP olgan (sinov, taklif bonusi yoki to'lov) va ustozdan kamida {MIN_TURNS} marta foydalangan "
        "o'quvchilar. Davom etayotgan sinov va yaqinda tugagan VIP kirmaydi.</i>"
    )
    if n:
        lines.append(f"\n<b>Xabar namunasi:</b>\n<blockquote>{invite_text(sample_name)}</blockquote>")
        lines.append("Tugmalar bilan sinab ko'rish: /vip_sorov test")
    return "\n".join(lines)


async def _deliver(bot, chat_id: int, text: str, markup: InlineKeyboardMarkup) -> bool:
    """Bitta xabar; Telegram limiti (429) bo'lsa kutib bir marta qayta urinadi."""
    for attempt in (1, 2):
        try:
            await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
            return True
        except TelegramRetryAfter as e:
            if attempt == 2:
                return False
            await asyncio.sleep(e.retry_after + 1)
        except Exception as e:  # botni bloklagan / chatni o'chirgan
            log.info("VIP so'rovi yetmadi (%s): %r", chat_id, e)
            return False
    return False


async def send_invites(session: AsyncSession, bot, targets: list[Target]) -> tuple[int, int]:
    """Taklif yuboradi. Qator xabardan OLDIN yoziladi: unikal user_id tufayli ikki marta bosish yoki ikki jarayon bir
    odamga ikki xabar yubora olmaydi; yetmagan bo'lsa qator o'chiriladi (yuborilganlar soni to'g'ri qoladi).
    Natija: (yuborildi, yetmadi)."""
    sent = failed = 0
    for t in targets:
        now = utcnow()
        session.add(VipSurvey(user_id=t.user_id, segment=t.segment, step="invited", invited_at=now, updated_at=now))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()  # boshqa jarayon allaqachon yubordi
            continue
        if await _deliver(bot, t.tg_id, invite_text(t.name), invite_kb()):
            sent += 1
        else:
            failed += 1
            await session.execute(delete(VipSurvey).where(VipSurvey.user_id == t.user_id))
            await session.commit()
        await asyncio.sleep(SEND_PAUSE)
    return sent, failed


async def send_test(session: AsyncSession, bot, user: User) -> bool:
    """Admin o'zida to'liq oqimni sinaydi (har safar noldan). Bu javob hisobotga kirmaydi (report adminni chiqarib tashlaydi)."""
    tg_id, name = user.tg_id, user.name
    await session.execute(delete(VipSurvey).where(VipSurvey.user_id == user.id))
    now = utcnow()
    session.add(VipSurvey(user_id=user.id, segment="", step="invited", invited_at=now, updated_at=now))
    if user.survey_pending == PENDING:
        user.survey_pending = 0
    await session.commit()
    return await _deliver(bot, tg_id, invite_text(name), invite_kb())


# ─────────────────────────── Hisobot ───────────────────────────


@dataclass
class Report:
    invited: int = 0
    answered: int = 0
    in_progress: int = 0
    declined: int = 0
    unopened: int = 0
    rating_avg: float = 0.0
    rating_dist: Counter = field(default_factory=Counter)
    liked: Counter = field(default_factory=Counter)
    issues: Counter = field(default_factory=Counter)
    segments: dict[str, tuple[int, float]] = field(default_factory=dict)  # segment → (javoblar, o'rtacha baho)
    with_text: int = 0
    comments: list[tuple[VipSurvey, User]] = field(default_factory=list)  # eng yangisi birinchi


async def report(session: AsyncSession, comments: int = 10) -> Report:
    """Javoblar yig'indisi. Admin o'zi sinab ko'rgan javoblar kirmaydi."""
    q = select(VipSurvey, User).join(User, User.id == VipSurvey.user_id)
    if settings.admin_id:
        q = q.where(User.tg_id != settings.admin_id)
    rows = (await session.execute(q.order_by(VipSurvey.id))).all()
    rep = Report(invited=len(rows))
    answered: list[tuple[VipSurvey, User]] = []
    for vs, u in rows:
        if vs.step in ANSWERED and vs.rating:
            answered.append((vs, u))
        elif vs.step == "declined":
            rep.declined += 1
        elif vs.step == "invited":
            rep.unopened += 1
        else:
            rep.in_progress += 1
    rep.answered = len(answered)
    seg_ratings: dict[str, list[int]] = {}
    for vs, _ in answered:
        rep.rating_dist[vs.rating] += 1
        rep.liked.update(k for k in vs.liked.split(",") if k)
        rep.issues.update(k for k in vs.issues.split(",") if k)
        seg_ratings.setdefault(vs.segment, []).append(vs.rating)
    if answered:
        rep.rating_avg = sum(v.rating for v, _ in answered) / len(answered)
    rep.segments = {s: (len(r), sum(r) / len(r)) for s, r in seg_ratings.items() if s in SEGMENTS}
    texts = [(v, u) for v, u in answered if v.text]
    rep.with_text = len(texts)
    texts.sort(key=lambda x: x[0].updated_at, reverse=True)
    rep.comments = texts[: max(comments, 0)]
    return rep


def _pct(n: int, base: int) -> int:
    return round(100 * n / base) if base else 0


def _bar(frac: float, width: int = 10) -> str:
    filled = round(frac * width)
    return "█" * filled + "░" * (width - filled)


def _counter_lines(kind: str, counts: Counter, base: int) -> list[str]:
    order = {k: i for i, (k, _) in enumerate(CATALOG[kind])}
    name = dict(CATALOG[kind])
    items = sorted(((k, n) for k, n in counts.items() if k in name and n), key=lambda kv: (-kv[1], order[kv[0]]))
    if not items:
        return ["—"]
    return [f"{esc(name[k])} — <b>{n}</b> ({_pct(n, base)}%)" for k, n in items]


def report_text(rep: Report) -> str:
    if not rep.invited:
        return "👑 VIP so'rovnomasi hali yuborilmagan. Yuborish: /vip_sorov"
    lines = [
        "👑 <b>VIP so'rovnomasi — natijalar</b>\n",
        f"📤 Yuborilgan: <b>{rep.invited}</b>",
        f"✅ Javob berdi: <b>{rep.answered}</b> ({_pct(rep.answered, rep.invited)}%) · "
        f"🔄 yarim qoldirdi: {rep.in_progress} · 🚫 rad etdi: {rep.declined} · 💤 ochmadi: {rep.unopened}",
    ]
    if not rep.answered:
        return "\n".join(lines + ["\nTugallangan javob hali yo'q."])
    lines.append(f"\n⭐ O'rtacha baho: <b>{rep.rating_avg:.1f}</b>/5")
    for n in range(5, 0, -1):
        c = rep.rating_dist.get(n, 0)
        lines.append(f"<code>{n}⭐ {_bar(c / rep.answered)} {c}</code>")
    lines.append(f"\n👍 <b>Nima yoqdi</b> ({rep.answered} ta javobdan)")
    lines += _counter_lines("liked", rep.liked, rep.answered)
    lines.append("\n👎 <b>Kamchiliklar</b>")
    lines += _counter_lines("issues", rep.issues, rep.answered)
    if rep.segments:
        lines.append("\n👥 <b>Kim qanday baholadi</b>")
        for seg, label in SEGMENTS.items():
            if seg in rep.segments:
                n, avg = rep.segments[seg]
                lines.append(f"{label}: {n} ta · ⭐ {avg:.1f}")
    if rep.comments:
        lines.append(f"\n💬 <b>Takliflar</b> (oxirgi {len(rep.comments)} / jami {rep.with_text}):")
        for vs, u in rep.comments:
            seg = SEGMENTS.get(vs.segment, "").split(" ")[0]
            lines.append(
                f"• <b>{admin_show(u.name, u.username, u.tg_id)}</b> ⭐{vs.rating} {seg} #F{vs.feedback_id}: "
                f"{esc(vs.text[:300])}"
            )
        lines.append("\n<i>Javob berish: /javob &lt;raqam&gt; matn · sharh: /sharh &lt;raqam&gt;</i>")
    return "\n".join(lines)


def chunks(text: str, limit: int = 3900) -> list[str]:
    """Qator chegarasida bo'ladi — <b>…</b> teg o'rtasidan kesilmasin (Telegram 4096 belgi)."""
    out: list[str] = []
    cur = ""
    for line in text.split("\n"):
        if cur and len(cur) + len(line) + 1 > limit:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out
