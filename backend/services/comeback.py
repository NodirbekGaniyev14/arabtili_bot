"""Qaytish kampaniyasi (K34, 2026-11-14) — jim o'quvchilarni qiziqtirib qaytarish.

Egasi: «o'rganuvchilar kamaygan» (haftalik digest: faol 77 / 1509). Tanlovi: sovg'a — streak tiklash + 50 XP,
kimga — 7–120 kun kirmaganlar, bir marta (bot bloklanishidan ehtiyot: [[bildirishnoma-bloklash]]).

Oqim:
1. Admin `/qaytarish` — kim tushadi (bo'limlar bo'yicha), namuna xabar adminning o'ziga; `/qaytarish yubor` — yuborish
   (faqat kunduzi SEND_FROM–SEND_TO, Toshkent).
2. Xabar: ism + necha kun + o'zi o'rgangan so'zdan 1 savol (3 ta inline tugma) — ilovani ochmasdan javob beradi.
3. Javobdan keyin xabar o'zgaradi: natija, kutayotgan kartalar, sovg'a sharti, «Darsni boshlash» tugmasi.
4. CLAIM_DAYS ichida 1 dars o'tsa (Progress.passed=1) — winback halqasi sovg'ani beradi: +GIFT_XP va uzilgan kunlar
   muzlatilgan deb belgilanadi (streak davom etadi), o'quvchiga qisqa xabar.
Bir o'quvchiga REPEAT_DAYS ichida bitta taklif; taklif olganlarga winback CLAIM_DAYS davomida yozmaydi.
"""

import asyncio
import json
import logging
import random
from datetime import date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ComebackOffer, Plan, Progress, User, UserWord, XpLog, utcnow
from services import notify_prefs
from services.names import show
from services.stats import TASHKENT_OFFSET, _local_date

log = logging.getLogger(__name__)

MIN_IDLE, MAX_IDLE = 7, 120  # kun (egasi tanlovi)
REPEAT_DAYS = 60  # bir o'quvchiga shuncha kunda ko'pi bilan bitta taklif
CLAIM_DAYS = 7  # sovg'a sharti: shu kun ichida 1 dars
GIFT_XP = 50
SEND_FROM, SEND_TO = 10, 20  # Toshkent soati
SEND_PAUSE = 0.05
WINBACK_GAP_DAYS = 2  # shu kun ichida winback xabari olganlarga yozilmaydi
BUCKETS = ((7, 14), (15, 30), (31, 60), (61, 120))

_running: dict[str, asyncio.Task] = {}


# ── Kim tushadi ──


async def _activity(session: AsyncSession) -> list[tuple[User, datetime]]:
    """(user, oxirgi faollik) — rejasi bor, demo emas; faollik = oxirgi XP, bo'lmasa reja sanasi (winback bilan bir xil)."""
    last_xp = select(XpLog.user_id, func.max(XpLog.created_at).label("last")).group_by(XpLog.user_id).subquery()
    planned = select(Plan.user_id, func.min(Plan.created_at).label("planned")).group_by(Plan.user_id).subquery()
    rows = (
        await session.execute(
            select(User, last_xp.c.last, planned.c.planned)
            .join(planned, planned.c.user_id == User.id)
            .outerjoin(last_xp, last_xp.c.user_id == User.id)
            .where(User.is_demo == 0, User.tg_id > 0)
        )
    ).all()
    return [(u, max(d for d in (last, plan) if d is not None)) for u, last, plan in rows]


async def audience(session: AsyncSession, now: datetime | None = None) -> dict:
    """{"users": [(user, idle_days, last_active)], "off": n, "recent": n, "buckets": {(a, b): n}}."""
    now = now or utcnow()
    today = _local_date(now)
    recent = set(
        (
            await session.execute(
                select(ComebackOffer.user_id).where(ComebackOffer.sent_at >= now - timedelta(days=REPEAT_DAYS))
            )
        ).scalars().all()
    )
    out = {"users": [], "off": 0, "recent": 0, "buckets": {b: 0 for b in BUCKETS}}
    for user, last in await _activity(session):
        days = (today - _local_date(last)).days
        if not MIN_IDLE <= days <= MAX_IDLE:
            continue
        if user.id in recent or (user.winback_at and user.winback_at >= now - timedelta(days=WINBACK_GAP_DAYS)):
            out["recent"] += 1
            continue
        if not notify_prefs.enabled(user, "comeback"):
            out["off"] += 1
            continue
        out["users"].append((user, days, last))
        for a, b in BUCKETS:
            if a <= days <= b:
                out["buckets"][(a, b)] += 1
    return out


# ── Viktorina so'zi ──


def _meaning(uz: str) -> str:
    """«bo — kosacha, pastda 1 nuqta» → «bo»; «kitob (ko'plik: kutub)» → «kitob»."""
    from services.battle_questions import meaning

    return meaning({"uz": uz.split(" — ")[0]}).strip()


def _is_letter(ar: str) -> bool:
    from services.lesson_skills import HARAKAT

    return len(HARAKAT.sub("", ar).strip()) == 1


def _content_pool(letters: bool) -> list[tuple[str, str]]:
    """Zaxira: kurs boshidagi harflar (a0-01..a0-14) yoki so'zlar (a1-01..a1-10) — kartasi kam o'quvchi uchun."""
    from services.curriculum import load_lesson_v2

    ids = [f"a0-{i:02d}" for i in range(1, 15)] if letters else [f"a1-{i:02d}" for i in range(1, 11)]
    out = []
    for lid in ids:
        for c in (load_lesson_v2(lid) or {}).get("srs_cards", []):
            ar, uz = c.get("front", ""), c.get("back", "")
            if c.get("type") == "word" and uz and _is_letter(ar) == letters:
                out.append((ar, uz))
    return out


async def pick_quiz(session: AsyncSession, user: User, rng: random.Random | None = None) -> dict:
    """O'quvchining o'z kartasidan savol: {"ar", "answer", "options", "letter"}; kartasi yo'q bo'lsa — kurs boshidan."""
    from services.battle_questions import senses

    rng = rng or random.Random(user.id)
    cards = [
        (w.ar, w.uz, (w.reps or 0) + (w.lapses or 0))
        for w in (
            await session.execute(
                select(UserWord).where(UserWord.user_id == user.id, UserWord.kind == "word", UserWord.deck == "msa")
            )
        ).scalars().all()
        if w.uz and w.ar
    ]
    words = [c for c in cards if not _is_letter(c[0])]
    pool = words or cards
    if pool:
        practiced = [c for c in pool if c[2] > 0]
        ar, uz, _ = rng.choice(practiced or pool)
    else:
        ar, uz = rng.choice(_content_pool(letters=False))
    letter = _is_letter(ar)
    answer = _meaning(uz)
    taken = senses(answer)
    options = [answer]
    others = [(a, u) for a, u, _ in cards if _is_letter(a) == letter and a != ar]
    rng.shuffle(others)
    fallback = _content_pool(letters=letter)
    rng.shuffle(fallback)
    for a, u in others + fallback:
        m = _meaning(u)
        if a == ar or not m or m in options or senses(m) & taken:
            continue
        options.append(m)
        taken |= senses(m)
        if len(options) == 3:
            break
    rng.shuffle(options)
    return {"ar": ar, "answer": answer, "options": options, "letter": letter}


# ── Streak ──


async def _active_days(session: AsyncSession, user_id: int) -> set[date]:
    rows = (await session.execute(select(XpLog.created_at).where(XpLog.user_id == user_id))).scalars().all()
    return {_local_date(dt) for dt in rows}


def _frozen(user: User) -> set[date]:
    return {date.fromisoformat(s) for s in (user.frozen_days or "").split(",") if s.strip()}


def streak_until(active: set[date], frozen: set[date], last: date) -> int:
    """`last` kuni bilan tugagan streak (muzlatilgan kunlar zanjirni uzmaydi, songa qo'shilmaydi)."""
    n, day = 0, last
    while day in active or day in frozen:
        n += day in active
        day -= timedelta(days=1)
    return n


# ── Matnlar ──


def offer_text(user: User, days: int, quiz: dict) -> str:
    name = show(user.name, "do'stim")
    ask = "Bu harf qanday o'qiladi?" if quiz["letter"] else "nima degani?"
    return (
        f"{name}, {days} kundan beri ko'rinmadingiz 🐪\n\n"
        "Bitta savol — esingizdami? Siz o'rgangan:\n\n"
        f"<b>{quiz['ar']}</b> — {ask}\n\n"
        "Tugmani bosing — natija va kichik sovg'a shu yerda chiqadi 🎁"
    )


def gift_line(prior_streak: int) -> str:
    fire = f"🔥 <b>{prior_streak} kunlik streakingiz tiklanadi</b>" if prior_streak >= 2 else "🔥 streak yana yonadi"
    return f"🎁 <b>Qaytish sovg'asi:</b> {CLAIM_DAYS} kun ichida 1 ta dars o'tsangiz — {fire} va <b>+{GIFT_XP} XP</b>."


def _quiz_kb(offer_id: int, options: list[str]):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=o[:60], callback_data=f"cbk:{offer_id}:{i}")] for i, o in enumerate(options)]
    )


def _open_kb(text: str = "📚 Darsni boshlash"):
    from services.winback import _kb

    return _kb([(text, "")])


# ── Yuborish ──


def in_send_hours(now: datetime) -> bool:
    return SEND_FROM <= (now + TASHKENT_OFFSET).hour < SEND_TO


async def make_offer(session: AsyncSession, user: User, days: int, last: datetime, campaign: str, now: datetime) -> ComebackOffer:
    quiz = await pick_quiz(session, user)
    active = await _active_days(session, user.id)
    offer = ComebackOffer(
        user_id=user.id, campaign=campaign, sent_at=now, idle_days=days, last_active=last,
        prior_streak=streak_until(active, _frozen(user), _local_date(last)),
        quiz_ar=quiz["ar"], quiz_answer=quiz["answer"], options_json=json.dumps(quiz["options"], ensure_ascii=False),
    )
    session.add(offer)
    await session.flush()
    return offer


BLOCKED_HINTS = ("blocked", "deactivated", "chat not found", "user is deactivated", "kicked")


async def _deliver(bot, user: User, offer: ComebackOffer) -> str:
    """Taklif xabari. Qaytaradi: "sent" | "blocked" (botni bloklagan / hisob o'chirilgan) | "failed" (boshqa xato).
    2026-11-22: birinchi kampaniyada 1053 dan 363 tasi «yetmadi» — hammasi «bloklagan» deb sanalgan edi; Telegram
    tezlik cheklovi (429) ham shunga tushardi. Endi 429 da kutib qayta uriniladi va sabab ajratiladi."""
    quiz = {"ar": offer.quiz_ar, "letter": _is_letter(offer.quiz_ar)}
    kb = _quiz_kb(offer.id, json.loads(offer.options_json))
    for attempt in range(2):
        try:
            await bot.send_message(user.tg_id, offer_text(user, offer.idle_days, quiz), parse_mode="HTML", reply_markup=kb)
            return "sent"
        except Exception as e:  # noqa: BLE001
            wait = getattr(e, "retry_after", None)
            if wait is not None and attempt == 0:
                await asyncio.sleep(min(float(wait), 60) + 1)
                continue
            text = str(e).lower()
            log.info("qaytish taklifi yetmadi (%s): %r", user.tg_id, e)
            if type(e).__name__ == "TelegramForbiddenError" or any(h in text for h in BLOCKED_HINTS):
                return "blocked"
            return "failed"
    return "failed"


async def send_campaign(session: AsyncSession, bot, now: datetime | None = None) -> dict:
    """Hamma mos o'quvchiga taklif. Qaytaradi: {"campaign", "sent", "blocked", "failed"}."""
    now = now or utcnow()
    campaign = (now + TASHKENT_OFFSET).date().isoformat()
    out = {"campaign": campaign, "sent": 0, "blocked": 0, "failed": 0}
    for user, days, last in (await audience(session, now))["users"]:
        offer = await make_offer(session, user, days, last, campaign, now)
        status = await _deliver(bot, user, offer)
        offer.status = status
        out[status] += 1
        await session.commit()
        await asyncio.sleep(SEND_PAUSE)
    return out


async def retry_failed(session: AsyncSession, bot, now: datetime | None = None) -> dict:
    """Oxirgi kampaniyada yetmagan (failed) takliflarni qayta yuboradi. Bloklaganlarga xabar baribir yetmaydi —
    ularga hech narsa ko'rinmaydi, faqat holati «blocked» bo'lib aniqlanadi. Yetganlarda sovg'a muddati shu paytdan."""
    now = now or utcnow()
    campaign = (
        await session.execute(select(func.max(ComebackOffer.campaign)))
    ).scalar()
    out = {"campaign": campaign or "—", "sent": 0, "blocked": 0, "failed": 0}
    if not campaign:
        return out
    offers = (
        await session.execute(
            select(ComebackOffer).where(ComebackOffer.campaign == campaign, ComebackOffer.status == "failed")
        )
    ).scalars().all()
    for offer in offers:
        user = await session.get(User, offer.user_id)
        if user is None:
            continue
        status = await _deliver(bot, user, offer)
        offer.status = status
        if status == "sent":
            offer.sent_at = now
        out[status] += 1
        await session.commit()
        await asyncio.sleep(SEND_PAUSE)
    return out


def start_background(bot, admin_chat: int, retry: bool = False) -> bool:
    """`/qaytarish yubor` (yoki `qayta`) — fonda yuboradi, tugagach adminga hisobot. Bir vaqtda bittasi."""
    task = _running.get("send")
    if task and not task.done():
        return False

    async def run():
        from db.session import SessionLocal

        try:
            async with SessionLocal() as session:
                res = await (retry_failed(session, bot) if retry else send_campaign(session, bot))
            await bot.send_message(
                admin_chat,
                f"↩️ Qaytish kampaniyasi ({res['campaign']}){' — qayta' if retry else ''}: yetdi {res['sent']}, "
                f"bloklagan {res['blocked']}, boshqa xato {res['failed']}.\nNatija: /qaytarish natija",
            )
        except Exception as e:  # noqa: BLE001
            log.warning("qaytish kampaniyasi xatosi: %r", e)

    _running["send"] = asyncio.create_task(run())
    return True


# ── Javob (inline tugma) ──


async def answer(session: AsyncSession, offer_id: int, tg_id: int, idx: int, now: datetime | None = None):
    """Viktorina javobi. Qaytaradi: (yangi matn | None, toast). None — xabar o'zgarmaydi."""
    from services.stats import user_stats

    now = now or utcnow()
    offer = await session.get(ComebackOffer, offer_id)
    user = await session.get(User, offer.user_id) if offer else None
    if offer is None or user is None or user.tg_id != tg_id:
        return None, "Bu savol sizga emas"
    options = json.loads(offer.options_json or "[]")
    if not 0 <= idx < len(options):
        return None, "Eskirgan tugma"
    if offer.answered:
        return None, "Javob berilgan — ilovada davom eting 👇"
    ok = options[idx] == offer.quiz_answer
    offer.answered, offer.answered_at = (1 if ok else 2), now
    await session.commit()

    st = await user_stats(session, user.id)
    head = (
        f"✅ <b>To'g'ri!</b> {offer.quiz_ar} — {offer.quiz_answer}. Xotirangiz joyida 👏"
        if ok
        else f"❌ Afsus, «{options[idx]}» emas. <b>{offer.quiz_ar}</b> — {offer.quiz_answer}.\nUnutila boshlagan — takrorlash vaqti keldi."
    )
    lines = [head, ""]
    if st.get("due_count"):
        lines.append(f"🔁 {st['due_count']} ta kartangiz takrorlashni kutmoqda.")
    nxt = (st.get("next_lesson") or {}).get("title")
    if nxt:
        lines.append(f"📖 Navbatdagi dars: «{nxt}»")
    lines += ["", gift_line(offer.prior_streak)]
    return "\n".join(lines), ("✅ To'g'ri!" if ok else "❌ Xato")


# ── Sovg'a ──


async def claim_due(session: AsyncSession, bot, now: datetime | None = None) -> int:
    """Taklifdan keyin CLAIM_DAYS ichida dars o'tganlarga sovg'a. Qaytaradi: nechta berildi."""
    from services.stats import resolve_streak

    now = now or utcnow()
    offers = (
        await session.execute(
            select(ComebackOffer).where(
                ComebackOffer.status == "sent",
                ComebackOffer.claimed_at.is_(None),
                ComebackOffer.sent_at >= now - timedelta(days=CLAIM_DAYS),
            )
        )
    ).scalars().all()
    given = 0
    for offer in offers:
        passed_at = (
            await session.execute(
                select(func.min(Progress.completed_at)).where(
                    Progress.user_id == offer.user_id, Progress.passed == 1, Progress.completed_at >= offer.sent_at
                )
            )
        ).scalar()
        if passed_at is None:
            continue
        user = await session.get(User, offer.user_id)
        if user is None:
            continue
        # Uzilgan kunlar (oxirgi faollikdan qaytgan kungacha) — muzlatilgan: streak davom etadi
        back = _local_date(passed_at)
        if offer.last_active and offer.prior_streak:
            frozen = _frozen(user)
            day = _local_date(offer.last_active) + timedelta(days=1)
            while day < back:
                frozen.add(day)
                day += timedelta(days=1)
            user.frozen_days = ",".join(sorted(d.isoformat() for d in frozen))
        session.add(XpLog(user_id=user.id, amount=GIFT_XP, source=f"comeback:{offer.campaign}"))
        offer.claimed_at, offer.xp = now, GIFT_XP
        await session.commit()
        streak, _ = await resolve_streak(session, user.id, await _active_days(session, user.id), _local_date(now))
        offer.restored = streak
        await session.commit()
        given += 1
        fire = f"🔥 Streak tiklandi: <b>{streak} kun</b>" if offer.prior_streak >= 2 else f"🔥 Streak: <b>{streak} kun</b>"
        try:
            await bot.send_message(
                user.tg_id,
                f"🎁 <b>Qaytganingiz uchun sovg'a!</b>\n\n{fire}\n⭐ <b>+{GIFT_XP} XP</b>\n\nErtaga ham 5 daqiqa — zanjir uzilmasin 🐪",
                parse_mode="HTML",
            )
        except Exception as e:  # noqa: BLE001
            log.info("qaytish sovg'asi xabari yetmadi (%s): %r", user.tg_id, e)
    return given


async def recent_offer_users(session: AsyncSession, now: datetime) -> set[int]:
    """Taklif olgan (CLAIM_DAYS ichida) — winback ularga alohida yozmaydi."""
    return set(
        (
            await session.execute(
                select(ComebackOffer.user_id).where(ComebackOffer.sent_at >= now - timedelta(days=CLAIM_DAYS))
            )
        ).scalars().all()
    )


# ── Admin ──


async def preview_text(session: AsyncSession, now: datetime | None = None) -> str:
    now = now or utcnow()
    aud = await audience(session, now)
    buckets = " · ".join(f"{a}–{b} kun: {n}" for (a, b), n in aud["buckets"].items())
    hours = "" if in_send_hours(now) else f"\n⏰ Hozir yuborilmaydi — faqat {SEND_FROM}:00–{SEND_TO}:00 (Toshkent)."
    return (
        f"↩️ <b>Qaytish kampaniyasi</b> — {MIN_IDLE}–{MAX_IDLE} kun kirmaganlar\n\n"
        f"Yuboriladi: <b>{len(aud['users'])}</b> kishi ({buckets})\n"
        f"Tushmaydi: «Qaytish eslatmalari» o'chiq — {aud['off']}, yaqinda xabar olgan — {aud['recent']}\n\n"
        f"Xabar: o'zi o'rgangan so'zdan 1 savol (tugmalar) → natija + sovg'a sharti. {CLAIM_DAYS} kun ichida 1 dars o'tsa: "
        f"streak tiklanadi + {GIFT_XP} XP. Bir kishiga {REPEAT_DAYS} kunda bir marta.\n"
        f"Namuna xabar sizga yuborildi (javob bering — qanday ko'rinishini ko'rasiz).{hours}\n\n"
        "Yuborish: <code>/qaytarish yubor</code> · natija: <code>/qaytarish natija</code>"
    )


async def sample_for_admin(session: AsyncSession, bot, admin_tg: int) -> None:
    """Namuna: admin foydalanuvchi bo'lsa — o'z kartasidan, aks holda kurs boshidan; yozuv saqlanmaydi."""
    user = (await session.execute(select(User).where(User.tg_id == admin_tg))).scalar_one_or_none()
    quiz = await pick_quiz(session, user or User(id=0, name="Namuna", tg_id=admin_tg))
    text = offer_text(user or User(name="Namuna"), 14, quiz)
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=o, callback_data=f"cbk:demo:{int(o == quiz['answer'])}")] for o in quiz["options"]]
    )
    await bot.send_message(admin_tg, "👀 <i>Namuna (o'quvchi shunday ko'radi):</i>\n\n" + text, parse_mode="HTML", reply_markup=kb)


async def results_text(session: AsyncSession) -> str:
    rows = (
        await session.execute(
            select(
                ComebackOffer.campaign,
                func.count(),
                func.sum(case((ComebackOffer.status.in_(("failed", "blocked")), 1), else_=0)),
                func.sum(case((ComebackOffer.status == "failed", 1), else_=0)),
                func.sum(case((ComebackOffer.answered > 0, 1), else_=0)),
                func.sum(case((ComebackOffer.answered == 1, 1), else_=0)),
                func.count(ComebackOffer.claimed_at),
            )
            .group_by(ComebackOffer.campaign)
            .order_by(ComebackOffer.campaign.desc())
            .limit(6)
        )
    ).all()
    if not rows:
        return "↩️ Qaytish kampaniyasi hali yuborilmagan. Ko'rish: /qaytarish"
    lines = ["↩️ <b>Qaytish kampaniyalari</b>\n"]
    for camp, n, missed, other, answered, right, claimed in rows:
        sent = n - (missed or 0)
        pct = lambda x: f"{round(100 * (x or 0) / sent)}%" if sent else "—"  # noqa: E731
        retry = f" (shundan aniqlanmagan xato {other} — <code>/qaytarish qayta</code>)" if other else ""
        lines.append(
            f"<b>{camp}</b>: yetdi {sent} · yetmadi {missed or 0}{retry}\n"
            f"   🧩 javob berdi {answered or 0} ({pct(answered)}, to'g'ri {right or 0}) · "
            f"📚 qaytib dars o'tdi {claimed or 0} ({pct(claimed)})"
        )
    return "\n".join(lines)
