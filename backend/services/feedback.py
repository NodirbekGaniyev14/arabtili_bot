"""Fikr-mulohaza: saqlash, adminga yetkazish, anonim javob berish.

Admin javobi faqat fikr egasining shaxsiy chatiga boradi — boshqa hech kim
ko'rmaydi. Javob "Arabiy jamoasi" nomidan ketadi, admin kimligi oshkor
qilinmaydi.
"""

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import Feedback, User

MAX_REPLY = 3000
_ID_TAG = re.compile(r"#F(\d+)")


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def feedback_id_from_text(text: str) -> int | None:
    """Adminga yuborilgan xabardagi `#F123` yorlig'idan fikr raqamini oladi."""
    m = _ID_TAG.search(text or "")
    return int(m.group(1)) if m else None


def admin_notice(fb: Feedback, user: User) -> str:
    """Adminga boradigan xabar — javob berish uchun `#F<id>` yorlig'i bilan."""
    uname = f"@{user.username}" if user.username else "—"
    ctx = f" · {esc(fb.context)}" if fb.context else ""
    return (
        f"💬 <b>Yangi fikr</b> #F{fb.id}\n"
        f"{esc(user.name or '—')}, {esc(uname)}, ID <code>{user.tg_id}</code>{ctx}\n\n"
        f"{esc(fb.text)}\n\n"
        f"<i>Javob berish: shu xabarga reply qiling yoki "
        f"/javob {fb.id} matn</i>"
    )


def reply_notice(fb: Feedback, reply: str) -> str:
    """Foydalanuvchiga boradigan anonim javob."""
    return (
        "💬 <b>Fikringizga javob</b>\n\n"
        f"<blockquote>{esc(fb.text[:300])}</blockquote>\n"
        f"{esc(reply)}\n\n"
        "<i>— Arabiy jamoasi</i>"
    )


async def save(
    session: AsyncSession,
    user_id: int,
    text: str,
    source: str,
    context: str = "",
) -> Feedback:
    fb = Feedback(
        user_id=user_id, text=text[:2000], source=source, context=context[:64]
    )
    session.add(fb)
    await session.commit()
    await session.refresh(fb)
    return fb


async def notify_admin(bot, fb: Feedback, user: User) -> None:
    if not (bot and settings.admin_id):
        return
    try:
        await bot.send_message(
            settings.admin_id, admin_notice(fb, user), parse_mode="HTML"
        )
    except Exception:
        pass


async def load_with_user(
    session: AsyncSession, feedback_id: int
) -> tuple[Feedback, User] | None:
    row = (
        await session.execute(
            select(Feedback, User)
            .join(User, User.id == Feedback.user_id)
            .where(Feedback.id == feedback_id)
        )
    ).first()
    return (row[0], row[1]) if row else None


async def mark_replied(session: AsyncSession, fb: Feedback, text: str) -> None:
    fb.reply_text = text[:MAX_REPLY]
    fb.replied_at = datetime.now(timezone.utc).replace(tzinfo=None)
    session.add(fb)
    await session.commit()
