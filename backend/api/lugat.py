"""Lug'at 2.0 (K24) — daraja → mavzu → fleshkarta sessiyasi → test → natija/XP.

Eski /api/vocab/* (qidiruv, kunlik to'plam, daraja imtihoni) api/routes.py da qoladi.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User, UserWord, XpLog
from db.session import get_session
from services import vocab
from services import vocab_session as vs
from services.srs import apply_grade
from services.stats import TASHKENT_OFFSET, _today
from services.telegram_auth import get_current_user

router = APIRouter(prefix="/api/vocab")


async def _cards(session: AsyncSession, user_id: int) -> dict[str, UserWord]:
    """Foydalanuvchi kartotekasi: {card_key: UserWord} (darsdan kelgan «الْبَيْت» = lug'atdagi «بَيْت»)."""
    rows = (await session.execute(select(UserWord).where(UserWord.user_id == user_id))).scalars().all()
    out: dict[str, UserWord] = {}
    for w in rows:
        out.setdefault(vocab.card_key(w.ar), w)
    return out


def _level(level: str) -> str:
    level = (level or "").upper()[:4]
    if level not in vocab.LEVELS:
        raise HTTPException(status_code=422, detail="Noma'lum daraja")
    return level


def _topic(topic: str) -> str:
    topic = (topic or "").strip()[:24]
    if topic != vocab.ALL_TOPIC and topic not in vocab.TOPIC_BY_SLUG:
        raise HTTPException(status_code=422, detail="Noma'lum mavzu")
    return topic


@router.get("/levels")
async def vocab_levels(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Darajalar kartasi: so'z soni, o'rganilgani, mavzular soni."""
    cards = await _cards(session, user.id)
    return vs.levels(set(cards))


@router.get("/topics")
async def vocab_topics(
    level: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    cards = await _cards(session, user.id)
    return vs.topics(_level(level), set(cards))


@router.get("/session")
async def vocab_session(
    level: str,
    topic: str = vocab.ALL_TOPIC,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """10 so'zlik sessiya: so'zlar (fleshkarta) + test savollari (javobi bilan — darhol ko'rsatish uchun;
    natija baribir serverda qayta tekshiriladi)."""
    level, topic = _level(level), _topic(topic)
    cards = await _cards(session, user.id)
    known = {k: {"lapses": w.lapses or 0, "ease": w.ease or 2.5, "due": w.due_date or ""} for k, w in cards.items()}
    data = vs.build(level, topic, known)
    if not data["words"]:
        raise HTTPException(status_code=404, detail="Bu mavzuda so'z yo'q")
    return data


class AnswerIn(BaseModel):
    key: str = Field(max_length=128)
    type: str = Field(max_length=12)
    chosen: str = Field(default="", max_length=300)


class FinishBody(BaseModel):
    level: str
    topic: str = vocab.ALL_TOPIC
    mode: str = Field(default="new", pattern=r"^(new|review|retry)$")
    answers: list[AnswerIn] = Field(default_factory=list, max_length=12)
    # Fleshkartada «Bilmadim» bosilgan so'zlar — testda to'g'ri bo'lsa ham SRS'da «qiyin»
    unknown: list[str] = Field(default_factory=list, max_length=20)


async def _vocab_xp_today(session: AsyncSession, user_id: int) -> int:
    start = datetime.combine(_today(), datetime.min.time()) - TASHKENT_OFFSET
    total = (
        await session.execute(
            select(func.coalesce(func.sum(XpLog.amount), 0)).where(
                XpLog.user_id == user_id,
                XpLog.created_at >= start,
                XpLog.source.like(f"{vs.XP_SOURCE}:%"),
            )
        )
    ).scalar_one()
    return int(total or 0)


@router.post("/session/finish")
async def vocab_session_finish(
    body: FinishBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Testni baholaydi, so'zlarni SRS kartotekasiga qo'shadi/yangilaydi, XP beradi (kunlik chegara bilan)."""
    from api.v2 import _badges

    level, topic = _level(body.level), _topic(body.topic)
    graded = vs.grade(level, [a.model_dump() for a in body.answers])
    if not graded:
        raise HTTPException(status_code=422, detail="Javoblar topilmadi")
    unknown = set(body.unknown)
    cards = await _cards(session, user.id)
    today = _today().isoformat()
    added = 0
    for g in graded:
        w = g["word"]
        card = cards.get(w["key"])
        grade = "again" if not g["correct"] else ("hard" if w["key"] in unknown else "good")
        if card is None:
            main, _hint = vs.split_uz(w.get("uz", ""))
            card = UserWord(
                user_id=user.id,
                ar=w["ar"],
                translit=w.get("translit", ""),
                uz=main[:256],
                audio=w.get("audio", "") or "",
                kind="word",
                card_type="word",
                deck="msa",
                due_date=today,
            )
            session.add(card)
            cards[w["key"]] = card
            added += 1
        apply_grade(card, grade)

    correct = sum(1 for g in graded if g["correct"])
    total = len(graded)
    percent = round(correct / total * 100)
    mode = "review" if body.mode != "new" else "new"
    xp = vs.xp_for(correct, total, mode)
    left = max(0, vs.DAILY_XP_CAP - await _vocab_xp_today(session, user.id))
    capped = xp > left
    xp = min(xp, left)
    if xp:
        session.add(XpLog(user_id=user.id, amount=xp, source=f"{vs.XP_SOURCE}:{level}:{topic}"[:64]))
    await session.commit()

    pool = vocab.topic_pool(level, topic)
    learned = sum(1 for w in pool if w["key"] in cards)
    return {
        "correct": correct,
        "total": total,
        "percent": percent,
        "passed": percent >= vs.PASS,
        "xp": xp,
        "xp_capped": capped,
        "added": added,
        "wrong": [
            {**vs.public(g["word"]), "type": g["type"], "chosen": g["chosen"]}
            for g in graded
            if not g["correct"]
        ],
        "topic_total": len(pool),
        "topic_learned": learned,
        "remaining": len(pool) - learned,
        "new_badges": await _badges(session, user.id),
    }
