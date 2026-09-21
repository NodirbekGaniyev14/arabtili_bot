"""So'rovnoma (K22.0) — barcha o'quvchidan bot haqida fikr.

Admin `/sorov [matn]` → barcha haqiqiy foydalanuvchilarga xabar + tugmalar
(«✍️ Fikr yozish», «👍 Hammasi yaxshi»). Qabul qiluvchilarda `users.survey_pending=1`:
keyingi matn yoki ovozli xabari fikr sifatida saqlanadi (`feedback.source="survey"`),
adminga darhol boradi (#F… — reply bilan javob berish mumkin), +XP bir marta.
Ovozli xabar STT orqali matnga (o'zbekcha). `/fikrlar [n]` — javoblar ro'yxati.
"""

import html
import logging

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Feedback, User, XpLog
from services import feedback as feedback_svc

log = logging.getLogger(__name__)

SOURCE = "survey"
XP = 10
OK_TEXT = "👍 Hammasi yaxshi (tugma)"

DEFAULT_TEXT = (
    "👋 Assalomu alaykum!\n\n"
    "Arabiy bot va ilovasi haqida <b>fikringizni</b> bilmoqchiman:\n"
    "• Nima yoqdi, nima yoqmadi?\n"
    "• Qayerda xato yoki tushunarsiz joy uchradi?\n"
    "• Nimani qo'shish yoki yaxshilash kerak?\n\n"
    "Shu chatga <b>bitta xabar</b> yozsangiz kifoya — ovozli xabar ham bo'ladi. "
    "Har birini o'zim o'qiyman va javob beraman. Rahmat! 🙏\n"
    "<i>— Arabiy jamoasi</i>"
)
PROMPT_TEXT = "✍️ Fikringizni shu yerga bitta xabar qilib yozing — matn yoki ovozli. Xato, taklif, nima yoqmagani — hammasi kerak."
THANKS = "Rahmat! 🙏 Fikringiz yetib bordi — o'qib, javob yozaman."


def text(custom: str = "") -> str:
    return html.escape(custom.strip()) if custom.strip() else DEFAULT_TEXT


def kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✍️ Fikr yozish", callback_data="sv:write"),
            InlineKeyboardButton(text="👍 Hammasi yaxshi", callback_data="sv:ok"),
        ]]
    )


async def record(session: AsyncSession, bot, user: User, body: str, kind: str = "text") -> tuple[Feedback, int]:
    """Fikrni saqlaydi, adminga yuboradi, birinchi javobga XP. (fikr, berilgan XP)."""
    prefix = "🎤 " if kind == "voice" else ""
    fb = await feedback_svc.save(session, user.id, prefix + body.strip(), source=SOURCE, context="sorov")
    user.survey_pending = 0
    earned = 0
    has_xp = (
        await session.execute(select(XpLog.id).where(XpLog.user_id == user.id, XpLog.source == SOURCE).limit(1))
    ).scalar_one_or_none()
    if has_xp is None and body.strip() != OK_TEXT:
        session.add(XpLog(user_id=user.id, amount=XP, source=SOURCE))
        earned = XP
    await session.commit()
    await feedback_svc.notify_admin(bot, fb, user)
    return fb, earned


async def responses(session: AsyncSession, limit: int = 30) -> list[tuple[Feedback, User]]:
    rows = (
        await session.execute(
            select(Feedback, User)
            .join(User, User.id == Feedback.user_id)
            .where(Feedback.source == SOURCE)
            .order_by(Feedback.id.desc())
            .limit(limit)
        )
    ).all()
    return [(r[0], r[1]) for r in rows]


def responses_text(rows: list[tuple[Feedback, User]], total: int) -> str:
    if not rows:
        return "📋 So'rov javoblari hali yo'q."
    lines = [f"📋 <b>So'rov javoblari</b> — jami {total}, oxirgi {len(rows)}:\n"]
    for fb, u in rows:
        when = fb.created_at.strftime("%d.%m") if fb.created_at else ""
        body = html.escape(fb.text[:300])
        lines.append(f"• <b>{html.escape(u.name or 'Foydalanuvchi')}</b> ({when}) #F{fb.id}: {body}")
    return "\n".join(lines)
