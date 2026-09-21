"""Xato deb topilgan yozma javoblar jurnali (#F70, K23).

Klient yozma mashqda (fill_blank / translate_* / dictation / harakat) javob rad etilganda
`POST /api/v2/answer-log` yuboradi. Admin `/javoblar` — 30 kunda eng ko'p rad etilgan
savollar: kutilgan javob va o'quvchilar yozganlari. Shu ro'yxatdan «to'g'ri edi, lekin
xato deyildi» holatlari ko'rinadi (yumshoq tekshiruvga qoida yoki kontentga variant qo'shiladi).
"""

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AnswerLog, utcnow

MAX_ROWS = 20_000
PRUNE_EVERY = 500  # har 500-qatorda eski qatorlar tozalanadi
TYPES = {"fill_blank", "translate_uz_ar", "translate_ar_uz", "dictation", "harakat"}


def _cut(s: str, n: int = 200) -> str:
    return (s or "").strip()[:n]


async def record(session: AsyncSession, user_id: int, context: str, ex_type: str, q: str, expected: str, given: str) -> bool:
    """Qatorni qo'shadi (commit chaqiruvchida). Klaviatura turi bo'lmasa yoki javob bo'sh — yozilmaydi."""
    if ex_type not in TYPES or not _cut(given) or not _cut(expected):
        return False
    row = AnswerLog(
        user_id=user_id, context=_cut(context, 24), ex_type=_cut(ex_type, 16),
        q=_cut(q), expected=_cut(expected), given=_cut(given),
    )
    session.add(row)
    await session.flush()
    if row.id % PRUNE_EVERY == 0:
        await prune(session)
    return True


async def prune(session: AsyncSession) -> int:
    """MAX_ROWS dan ortiq eski qatorlar o'chiriladi."""
    total = (await session.execute(select(func.count()).select_from(AnswerLog))).scalar_one()
    extra = total - MAX_ROWS
    if extra <= 0:
        return 0
    cutoff = (
        await session.execute(select(AnswerLog.id).order_by(AnswerLog.id).offset(extra - 1).limit(1))
    ).scalar_one()
    from sqlalchemy import delete

    await session.execute(delete(AnswerLog).where(AnswerLog.id <= cutoff))
    return extra


async def report(session: AsyncSession, days: int = 30, top: int = 15, since: datetime | None = None) -> dict:
    """Eng ko'p rad etilgan savollar: [{context, ex_type, q, expected, n, users, given: [(matn, soni)]}]."""
    since = since or (utcnow() - timedelta(days=days))
    rows = (
        await session.execute(
            select(AnswerLog.context, AnswerLog.ex_type, AnswerLog.q, AnswerLog.expected, AnswerLog.given, AnswerLog.user_id)
            .where(AnswerLog.created_at >= since)
        )
    ).all()
    groups: dict[tuple, dict] = {}
    for context, ex_type, q, expected, given, uid in rows:
        g = groups.setdefault((context, ex_type, q, expected), {"n": 0, "users": set(), "given": defaultdict(int)})
        g["n"] += 1
        g["users"].add(uid)
        g["given"][given] += 1
    items = []
    for (context, ex_type, q, expected), g in groups.items():
        items.append(
            {
                "context": context, "ex_type": ex_type, "q": q, "expected": expected,
                "n": g["n"], "users": len(g["users"]),
                "given": sorted(g["given"].items(), key=lambda kv: -kv[1])[:3],
            }
        )
    items.sort(key=lambda it: (-it["users"], -it["n"]))
    return {"total": len(rows), "days": days, "items": items[:top]}


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def report_text(rep: dict) -> str:
    if not rep["total"]:
        return f"📝 <b>Rad etilgan javoblar</b> — {rep['days']} kunda yozuv yo'q (deploy'dan keyin yig'iladi)."
    lines = [f"📝 <b>Rad etilgan yozma javoblar</b> — {rep['days']} kun, jami {rep['total']} ta\n"]
    for i, it in enumerate(rep["items"], 1):
        given = " · ".join(f"«{_esc(t)}»×{n}" if n > 1 else f"«{_esc(t)}»" for t, n in it["given"])
        lines.append(
            f"{i}. <b>{_esc(it['context'])}</b> · {it['ex_type']} · {it['users']} kishi / {it['n']} marta\n"
            f"   ❓ {_esc(it['q'][:90])}\n"
            f"   ✅ {_esc(it['expected'])}\n"
            f"   ✍️ {given}"
        )
    lines.append("\nKo'p kishi bir xil «xato» yozgan bo'lsa — javob variantini kontentga qo'shish yoki tekshiruvni yumshatish kerak.")
    return "\n".join(lines)
