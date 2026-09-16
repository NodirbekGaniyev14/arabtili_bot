"""Taklif dasturi va VIP sinov (K18.1) — o'sish VIP orqali.

Taklif: har foydalanuvchining shaxsiy havolasi `t.me/<bot>?start=ref<tg_id>`.
Yangi foydalanuvchi shu havola bilan kelsa `users.invited_by` yoziladi; u
BIRINCHI darsni o'tganda ikkalasiga ham REF_DAYS kun VIP (haqiqiy o'quvchi
belgisi — soxta akkaunt bilan olish qiyin). Taklifchi ko'pi bilan
REF_MAX_REWARDS marta mukofot oladi.

Sinov: har foydalanuvchi bir marta TRIAL_DAYS kun VIP ni bepul yoqadi
(`users.trial_until`) — mock va cheksiz suhbatni tatib ko'radi, keyin paywall.
"""

import logging
from datetime import datetime
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import User
from services import billing

log = logging.getLogger(__name__)

REF_DAYS = 3
REF_MAX_REWARDS = 10
TRIAL_DAYS = 2

SHARE_TEXT = (
    "Arab tilini noldan o'rganyapman — Arabiy 🐪 A0–B2 darslar, 6000 so'z, AI ustoz bilan "
    "gaplashish. Shu havola bilan kirsang, ikkalamizga 3 kun VIP bepul:"
)


def link_for(user: User) -> str:
    return f"https://t.me/{settings.bot_username}?start=ref{user.tg_id}"


def share_url(user: User) -> str:
    return f"https://t.me/share/url?url={quote(link_for(user))}&text={quote(SHARE_TEXT)}"


def parse_start_arg(args: str) -> int | None:
    """`/start ref123` → 123; boshqa argument → None."""
    a = (args or "").strip()
    if a.startswith("ref") and a[3:].isdigit():
        return int(a[3:])
    return None


async def attach(session: AsyncSession, new_user: User, referrer_tg_id: int) -> bool:
    """Yangi foydalanuvchini taklifchiga bog'laydi (o'zini o'zi, mavjud bog'lanish — yo'q)."""
    if new_user.invited_by is not None or referrer_tg_id == new_user.tg_id:
        return False
    referrer = (
        await session.execute(select(User).where(User.tg_id == referrer_tg_id))
    ).scalar_one_or_none()
    if referrer is None or referrer.id == new_user.id:
        return False
    new_user.invited_by = referrer.id
    return True


async def rewarded_count(session: AsyncSession, referrer_id: int) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(User).where(
                User.invited_by == referrer_id, User.ref_rewarded == 1
            )
        )
    ).scalar_one()


async def on_lesson_passed(session: AsyncSession, user: User, bot=None) -> dict | None:
    """Taklif qilingan foydalanuvchi birinchi darsni o'tdi → ikkalasiga VIP.
    Bir marta; taklifchi limiti to'lgan bo'lsa faqat yangi foydalanuvchi oladi."""
    if user.invited_by is None or user.ref_rewarded:
        return None
    referrer = await session.get(User, user.invited_by)
    user.ref_rewarded = 1
    until_user = billing.grant(user, REF_DAYS)
    referrer_paid = False
    until_ref = None
    if referrer is not None and await rewarded_count(session, referrer.id) <= REF_MAX_REWARDS:
        until_ref = billing.grant(referrer, REF_DAYS)
        referrer_paid = True
    await session.commit()

    if bot is not None:
        try:
            await bot.send_message(
                user.tg_id,
                f"🎁 <b>Taklif bonusi: {REF_DAYS} kun VIP!</b>\n\n"
                f"Birinchi darsni tugatdingiz — {until_user:%d.%m} gacha 🤖 AI ustoz, "
                "🎤 speaking va 🎯 mock imtihonlar ochiq. Sinab ko'ring!",
                parse_mode="HTML",
                reply_markup=_open_kb("🤖 AI ustozni ochish", "#tutor"),
            )
        except Exception:
            pass
        if referrer_paid and referrer is not None:
            try:
                await bot.send_message(
                    referrer.tg_id,
                    f"🎉 Do'stingiz <b>{user.name or 'yangi o’quvchi'}</b> birinchi darsni tugatdi — "
                    f"sizga <b>{REF_DAYS} kun VIP</b> qo'shildi ({until_ref:%d.%m} gacha).\n\n"
                    "Yana taklif qiling: /taklif",
                    parse_mode="HTML",
                    reply_markup=_open_kb("🤖 AI ustozni ochish", "#tutor"),
                )
            except Exception:
                pass
    return {"days": REF_DAYS, "referrer_paid": referrer_paid}


def _open_kb(text: str, hash_: str):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    from services.deploy_notify import webapp_url_versioned

    url = webapp_url_versioned()
    if not url.startswith("https://"):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url + hash_))]]
    )


async def stats(session: AsyncSession, user: User) -> dict:
    invited = (
        await session.execute(
            select(func.count()).select_from(User).where(User.invited_by == user.id)
        )
    ).scalar_one()
    rewarded = await rewarded_count(session, user.id)
    return {
        "link": link_for(user),
        "share_url": share_url(user),
        "invited": invited,
        "rewarded": rewarded,
        "days_earned": min(rewarded, REF_MAX_REWARDS) * REF_DAYS,
        "days_per_friend": REF_DAYS,
        "max_rewards": REF_MAX_REWARDS,
    }


# ── Sinov ──


def trial_available(user: User) -> bool:
    return user.trial_until is None and not billing.is_vip(user)


def start_trial(user: User) -> datetime:
    """Bir martalik TRIAL_DAYS kun VIP. Chaqiruvchi tekshiradi: trial_available."""
    user.trial_until = billing.grant(user, TRIAL_DAYS)
    return user.trial_until


def on_trial(user: User) -> bool:
    """Hozirgi VIP davri aynan sinov (uzaytirilmagan)."""
    return bool(user.trial_until and user.vip_until and user.vip_until == user.trial_until)
