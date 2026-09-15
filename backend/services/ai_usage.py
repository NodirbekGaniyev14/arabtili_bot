"""Anthropic sarfi hisobi (K17.3).

Har Claude chaqiruvi `ai_usage` jadvaliga yoziladi (xususiyat + tokenlar);
admin `/ustoz` buyrug'i shu yerdan kunlik/oylik $ sarfini hisoblaydi.
Narxlar — Haiku 4.5, 1 M token uchun USD; model o'zgarsa PRICE_PER_M yangilanadi.
"""

import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AiUsage

log = logging.getLogger(__name__)

# Haiku 4.5: kirish $1, chiqish $5, cache o'qish $0.10, cache yozish $1.25
PRICE_PER_M = {"in": 1.00, "out": 5.00, "cache_read": 0.10, "cache_write": 1.25}

FEATURES = {
    "tutor": "💬 Suhbat",
    "mock": "🎯 Mock imtihon",
    "roleplay": "🎭 Rol o'yini",
    "writing": "✍️ Yozma baho",
    "onboarding": "🧭 Reja tuzish",
}


def usage_of(resp) -> dict:
    """Anthropic javobidan token hisobi (`parse` va `create` ikkalasida ham `usage`)."""
    u = getattr(resp, "usage", None)
    return {
        "in": getattr(u, "input_tokens", 0) or 0,
        "out": getattr(u, "output_tokens", 0) or 0,
        "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
    }


def cost_usd(usage: dict) -> float:
    return sum((usage.get(k) or 0) * p for k, p in PRICE_PER_M.items()) / 1_000_000


def record(session: AsyncSession, feature: str, usage: dict, user_id: int | None = None) -> None:
    """Sarf qatorini sessiyaga qo'shadi — chaqiruvchi commit qiladi."""
    session.add(
        AiUsage(
            user_id=user_id,
            feature=feature[:12],
            tokens_in=usage.get("in") or 0,
            tokens_out=usage.get("out") or 0,
            cache_read=usage.get("cache_read") or 0,
            cache_write=usage.get("cache_write") or 0,
        )
    )


async def summary(session: AsyncSession, since: datetime | None = None) -> dict:
    """Xususiyat bo'yicha chaqiruvlar, tokenlar va $ (since — naive UTC).

    Qaytaradi: {"by": {feature: {"calls", "usage", "cost"}}, "calls", "usage", "cost"}.
    """
    q = select(
        AiUsage.feature,
        func.count(),
        func.coalesce(func.sum(AiUsage.tokens_in), 0),
        func.coalesce(func.sum(AiUsage.tokens_out), 0),
        func.coalesce(func.sum(AiUsage.cache_read), 0),
        func.coalesce(func.sum(AiUsage.cache_write), 0),
    ).group_by(AiUsage.feature)
    if since is not None:
        q = q.where(AiUsage.created_at >= since)
    rows = (await session.execute(q)).all()

    by: dict[str, dict] = {}
    total = {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0}
    calls = 0
    for feature, n, t_in, t_out, c_read, c_write in rows:
        u = {"in": t_in, "out": t_out, "cache_read": c_read, "cache_write": c_write}
        by[feature] = {"calls": n, "usage": u, "cost": cost_usd(u)}
        calls += n
        for k in total:
            total[k] += u[k]
    return {"by": by, "calls": calls, "usage": total, "cost": cost_usd(total)}
