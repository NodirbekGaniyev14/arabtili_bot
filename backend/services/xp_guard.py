"""XP himoyasi (K28 pentest) — natijani mijoz o'zi hisoblaydigan eski endpointlar uchun chegaralar.

Topilgan zaiflik (2026-09-28): /lessons/{id}/complete, /checkpoint/{id}/complete, /practice/weak/complete,
/vocab/quiz/submit `correct`/`total` ni chegarasiz qabul qilardi — bitta so'rov
`{"correct": 1000000, "total": 1000000}` million XP berardi, takrorlash cheksiz edi. Haftalik reyting top-3
VIP kunlari bilan taqdirlanadi (haqiqiy pul qiymati) — soxta XP halol o'quvchilardan sovrinni tortib olardi.

Yechim (halol o'quvchi sezmaydi):
  - `clamp` — natija savollar soniga qisiladi (server biladi: mikro-test ≤ 10 + o'qish savollari va h.k.);
  - `capped` — manba bo'yicha kunlik XP chegarasi (Toshkent kuni) — skript bilan «dehqonchilik» cheklanadi.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import XpLog
from services.stats import TASHKENT_OFFSET


def clamp(correct: int, total: int, cap: int) -> tuple[int, int]:
    """(correct, total): 1 ≤ total ≤ cap, 0 ≤ correct ≤ total."""
    total = max(1, min(int(total), max(1, cap)))
    return max(0, min(int(correct), total)), total


def day_start_utc(now: datetime | None = None) -> datetime:
    """Toshkent kunining boshi — naive UTC (XpLog.created_at shunday saqlanadi)."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    local = now + TASHKENT_OFFSET
    return datetime(local.year, local.month, local.day) - TASHKENT_OFFSET


async def xp_today(session: AsyncSession, user_id: int, prefix: str) -> int:
    """Bugun `prefix` bilan boshlanuvchi manbadan olingan XP."""
    total = (
        await session.execute(
            select(func.coalesce(func.sum(XpLog.amount), 0)).where(
                XpLog.user_id == user_id,
                XpLog.source.like(prefix.replace("%", r"\%").replace("_", r"\_") + "%", escape="\\"),
                XpLog.created_at >= day_start_utc(),
            )
        )
    ).scalar_one()
    return int(total or 0)


async def capped(session: AsyncSession, user_id: int, prefix: str, xp: int, daily_cap: int) -> int:
    """XP kunlik chegaradan oshmasin (qolgani beriladi, tugagan bo'lsa 0)."""
    if xp <= 0:
        return 0
    left = max(0, daily_cap - await xp_today(session, user_id, prefix))
    return min(xp, left)
