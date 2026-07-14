"""Root Lab xizmati — o'zaklar ro'yxati, tafsilot va progress."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import RootProgress
from services.curriculum import load_patterns, load_roots


def roots_summary() -> list[dict]:
    """Ro'yxat uchun yengil ma'lumot (daraxtsiz)."""
    out = []
    for r in load_roots():
        out.append(
            {
                "root": r["root"],
                "meaning_uz": r["meaning_uz"],
                "uz_cognates": r.get("uz_cognates", []),
                "count": len(r.get("derived", [])),
            }
        )
    return out


def root_detail(root: str) -> dict | None:
    for r in load_roots():
        if r["root"] == root:
            return r
    return None


def pattern_detail(pattern_ar: str) -> dict | None:
    for p in load_patterns():
        if p["ar"] == pattern_ar:
            return p
    return None


async def record_seen(session: AsyncSession, user_id: int, root: str) -> None:
    """Foydalanuvchi o'zakni Root Lab'da ochganini yozadi."""
    row = (
        await session.execute(
            select(RootProgress).where(
                RootProgress.user_id == user_id, RootProgress.root == root
            )
        )
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if row is None:
        session.add(
            RootProgress(user_id=user_id, root=root, seen_count=1, last_seen=now)
        )
    else:
        row.seen_count += 1
        row.last_seen = now
        session.add(row)
    await session.commit()


async def seen_roots(session: AsyncSession, user_id: int) -> set[str]:
    rows = await session.execute(
        select(RootProgress.root).where(RootProgress.user_id == user_id)
    )
    return set(rows.scalars())
