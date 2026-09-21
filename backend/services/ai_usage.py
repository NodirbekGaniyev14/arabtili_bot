"""Anthropic sarfi hisobi (K17.3).

Har Claude chaqiruvi `ai_usage` jadvaliga yoziladi (xususiyat + tokenlar);
admin `/ustoz` buyrug'i shu yerdan kunlik/oylik $ sarfini hisoblaydi.
Narxlar — 1 M token uchun USD, model prefiksi bo'yicha (PRICES); noma'lum model
Haiku narxida hisoblanadi. K23.4: VIP suhbat/mock boshqa modelda bo'lishi mumkin
(`ai_usage.model` ustuni) — /ustoz model bo'yicha ham ko'rsatadi.
"""

import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AiUsage

log = logging.getLogger(__name__)

# Haiku 4.5: kirish $1, chiqish $5, cache o'qish $0.10, cache yozish $1.25
PRICE_PER_M = {"in": 1.00, "out": 5.00, "cache_read": 0.10, "cache_write": 1.25}
# Model prefiksi → narx (cache o'qish 0.1×, yozish 1.25× kirish narxidan)
PRICES = {
    "claude-haiku-4-5": PRICE_PER_M,
    "claude-sonnet-5": {"in": 2.00, "out": 10.00, "cache_read": 0.20, "cache_write": 2.50},
    "claude-sonnet-4": {"in": 3.00, "out": 15.00, "cache_read": 0.30, "cache_write": 3.75},
    "claude-opus-5": {"in": 5.00, "out": 25.00, "cache_read": 0.50, "cache_write": 6.25},
}


def prices_for(model: str) -> dict:
    for prefix, p in PRICES.items():
        if (model or "").startswith(prefix):
            return p
    return PRICE_PER_M


def short_model(model: str) -> str:
    """claude-sonnet-5 → Sonnet 5, claude-haiku-4-5-20251001 → Haiku 4.5 (hisobot uchun)."""
    parts = [p for p in (model or "").split("-") if p and not (len(p) == 8 and p.isdigit())]
    if len(parts) >= 2 and parts[0] == "claude":
        return parts[1].capitalize() + " " + ".".join(parts[2:])
    return model or "?"

FEATURES = {
    "tutor": "💬 Suhbat",
    "mock": "🎯 Mock imtihon",
    "roleplay": "🎭 Rol o'yini",
    "writing": "✍️ Yozma baho",
    "onboarding": "🧭 Reja tuzish",
    "daily": "🎙 Kunlik savol",
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


def cost_usd(usage: dict, model: str = "") -> float:
    prices = prices_for(model or usage.get("model") or "")
    return sum((usage.get(k) or 0) * p for k, p in prices.items()) / 1_000_000


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
            model=(usage.get("model") or "")[:40],
        )
    )


async def summary(session: AsyncSession, since: datetime | None = None) -> dict:
    """Xususiyat bo'yicha chaqiruvlar, tokenlar va $ (since — naive UTC).

    Qaytaridi: {"by": {feature: {"calls", "usage", "cost"}}, "by_model": {model: {"calls", "cost"}},
    "calls", "usage", "cost"} — narx har qator o'z modeli bo'yicha.
    """
    q = select(
        AiUsage.feature,
        AiUsage.model,
        func.count(),
        func.coalesce(func.sum(AiUsage.tokens_in), 0),
        func.coalesce(func.sum(AiUsage.tokens_out), 0),
        func.coalesce(func.sum(AiUsage.cache_read), 0),
        func.coalesce(func.sum(AiUsage.cache_write), 0),
    ).group_by(AiUsage.feature, AiUsage.model)
    if since is not None:
        q = q.where(AiUsage.created_at >= since)
    rows = (await session.execute(q)).all()

    by: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    total = {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0}
    calls = 0
    cost = 0.0
    for feature, model, n, t_in, t_out, c_read, c_write in rows:
        u = {"in": t_in, "out": t_out, "cache_read": c_read, "cache_write": c_write}
        c = cost_usd(u, model or "")
        f = by.setdefault(feature, {"calls": 0, "usage": {k: 0 for k in total}, "cost": 0.0})
        f["calls"] += n
        f["cost"] += c
        m = by_model.setdefault(model or "", {"calls": 0, "cost": 0.0})
        m["calls"] += n
        m["cost"] += c
        calls += n
        cost += c
        for k in total:
            total[k] += u[k]
            f["usage"][k] += u[k]
    return {"by": by, "by_model": by_model, "calls": calls, "usage": total, "cost": cost}
