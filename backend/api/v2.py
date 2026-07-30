"""Curriculum v2 API — yangi dars playeri endpointlari (K2).

/api/v2/* — v1 (jonli kurs) endpointlariga tegmaydi.
"""

import json
import random

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import LessonRating, Plan, Progress, User, XpLog
from db.session import get_session
from services.achievements import check_and_award
from services.curriculum import (
    load_curriculum,
    load_lesson_v2,
    written_lesson_ids,
)
from services.lesson_test import PASS_SCORE, build_test
from services.reading import passage_for
from services.srs import reset_words, seed_from_srs_cards
from services.stats import completed_lesson_ids, lesson_attempt_count, user_stats
from services.telegram_auth import get_current_user

router = APIRouter(prefix="/api/v2")

CHECKPOINT_EVERY = 5
CHECKPOINT_QUESTIONS = 15
CHECKPOINT_PASS = 70  # foiz
FAIL_XP = 5  # yiqilgan urinish uchun ham ozgina XP (streak uzilmasin)


@router.get("/lessons/{lesson_id}")
async def lesson_v2(
    lesson_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    meta = load_curriculum().get(lesson_id)
    data = load_lesson_v2(lesson_id)
    if not meta or not data:
        raise HTTPException(status_code=404, detail="Dars topilmadi")

    # Mikro-test urinishga qarab yig'iladi — qayta topshirganda boshqa savollar
    attempts = await lesson_attempt_count(session, user.id, lesson_id)
    test = build_test(lesson_id, attempts)

    return {
        **data,
        "micro_test": test["items"],
        "test_attempt": test["attempt"],
        "pass_score": PASS_SCORE,
        "attempts_made": attempts,
        # A2+ darslarda bosqichma-bosqich o'qish matni (services/reading.py)
        "passage": passage_for(lesson_id),
        "meta": {
            "title_uz": meta["title_uz"],
            "level": meta["level"],
            "order": meta["order"],
            "module": meta["module"],
        },
    }


class CompleteV2Body(BaseModel):
    correct: int = Field(ge=0)
    total: int = Field(ge=1)
    wrong_words: list[str] = Field(default_factory=list)


def _checkpoint_lessons(lesson_id: str) -> list[str]:
    """Nazorat testi qamrab oladigan 5 dars (agar bu dars 5-lik chegarasi bo'lsa)."""
    meta = load_curriculum().get(lesson_id)
    if not meta or meta["type"] != "lesson" or meta["order"] % CHECKPOINT_EVERY != 0:
        return []
    prefix = lesson_id.split("-")[0]
    ids = [
        f"{prefix}-{i:02d}"
        for i in range(meta["order"] - CHECKPOINT_EVERY + 1, meta["order"] + 1)
    ]
    written = written_lesson_ids()
    return [i for i in ids if i in written]


@router.post("/lessons/{lesson_id}/complete")
async def complete_v2(
    lesson_id: str,
    body: CompleteV2Body,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    data = load_lesson_v2(lesson_id)
    if not data:
        raise HTTPException(status_code=404, detail="Dars topilmadi")

    correct = min(body.correct, body.total)
    perfect = correct == body.total
    score = round(100 * correct / body.total)
    passed = score >= PASS_SCORE  # spec §11 — 60% dan past bo'lsa dars o'tilmaydi

    done_before = await completed_lesson_ids(session, user.id)
    first_time = lesson_id not in done_before
    if not passed:
        # Dars tugatilmadi: keyingi dars ochilmaydi, XP faqat urinish uchun
        xp = FAIL_XP
    else:
        xp = (10 + 2 * correct + (5 if perfect else 0)) if first_time else (5 + correct)

    session.add(
        Progress(
            user_id=user.id, lesson_id=lesson_id,
            correct=correct, total=body.total, xp_earned=xp,
            passed=1 if passed else 0,
        )
    )
    session.add(XpLog(user_id=user.id, amount=xp, source=f"lesson:{lesson_id}"))
    await session.commit()

    # SRS: yangi kartalar + xato so'zlar reset (spec §11)
    added = await seed_from_srs_cards(session, user.id, data.get("srs_cards", []))
    await reset_words(session, user.id, body.wrong_words)

    plan = (
        await session.execute(
            select(Plan).where(Plan.user_id == user.id).order_by(Plan.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    plan_order = json.loads(plan.module_order_json) if plan else None
    stats = await user_stats(session, user.id, plan_order)
    new_badges = await check_and_award(session, user.id, stats["streak"])

    cp = _checkpoint_lessons(lesson_id)
    return {
        "xp_earned": xp,
        "perfect": perfect,
        "score": score,
        "passed": passed,
        "pass_score": PASS_SCORE,
        "first_time": first_time,
        "srs_added": added,
        "srs_reset": len(body.wrong_words),
        "stats": stats,
        "new_badges": new_badges,
        # Yiqilgan darsdan keyin nazorat testi taklif qilinmaydi
        "checkpoint_available": passed and len(cp) >= 2,
    }


class RateBody(BaseModel):
    rating: int = Field(ge=-1, le=1)  # +1 (👍) yoki -1 (👎)


@router.post("/lessons/{lesson_id}/rate")
async def rate_lesson(
    lesson_id: str,
    body: RateBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Dars oxiridagi 1-bosishli baho (👍/👎). Takror bosilsa yangilanadi."""
    if body.rating == 0:
        return {"ok": False}
    existing = (
        await session.execute(
            select(LessonRating).where(
                LessonRating.user_id == user.id,
                LessonRating.lesson_id == lesson_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.rating = body.rating
    else:
        session.add(
            LessonRating(user_id=user.id, lesson_id=lesson_id, rating=body.rating)
        )
    await session.commit()
    return {"ok": True}


@router.get("/checkpoint/{lesson_id}")
async def checkpoint_questions(
    lesson_id: str,
    user: User = Depends(get_current_user),
):
    ids = _checkpoint_lessons(lesson_id)
    if len(ids) < 2:
        raise HTTPException(status_code=404, detail="Nazorat testi mavjud emas")

    pool: list[dict] = []
    for lid in ids:
        data = load_lesson_v2(lid)
        if not data:
            continue
        for item in data.get("micro_test", []):
            pool.append(item)

    random.shuffle(pool)
    questions = pool[:CHECKPOINT_QUESTIONS]
    return {
        "lesson_ids": ids,
        "pass_percent": CHECKPOINT_PASS,
        "questions": questions,
    }


@router.post("/checkpoint/{lesson_id}/complete")
async def checkpoint_complete(
    lesson_id: str,
    body: CompleteV2Body,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not _checkpoint_lessons(lesson_id):
        raise HTTPException(status_code=404, detail="Nazorat testi mavjud emas")

    correct = min(body.correct, body.total)
    score = round(100 * correct / body.total)
    passed = score >= CHECKPOINT_PASS

    xp = 15 + correct if passed else 5
    session.add(
        XpLog(user_id=user.id, amount=xp, source=f"checkpoint:{lesson_id}")
    )
    await session.commit()
    await reset_words(session, user.id, body.wrong_words)

    return {
        "score": score,
        "passed": passed,
        "xp_earned": xp,
        "srs_reset": len(body.wrong_words),
    }


# ─────────────────── AI rol o'yini (Saudiya vaziyatlari) ───────────────────


@router.get("/roleplay/scenarios")
async def roleplay_scenarios(user: User = Depends(get_current_user)):
    from services import roleplay

    return {"scenarios": roleplay.scenario_list()}


class RoleplayBody(BaseModel):
    scenario_id: str
    history: list[dict] = Field(default_factory=list)


@router.post("/roleplay/reply")
async def roleplay_reply(
    body: RoleplayBody,
    user: User = Depends(get_current_user),
):
    from services import roleplay

    if not body.history:
        op = roleplay.opening(body.scenario_id)
        if op is None:
            raise HTTPException(status_code=404, detail="Vaziyat topilmadi")
        return op
    # Faqat oxirgi 12 xabar (kontekstni cheklaymiz)
    return await roleplay.reply(body.scenario_id, body.history[-12:])


# ─────────────────── AI yozish bahosi (zaxirali) ───────────────────


class WritingEvalBody(BaseModel):
    lesson_id: str
    text: str = Field(max_length=1000)


FALLBACK_FEEDBACK = (
    "AI baholash hozircha o'chiq. Yozganingiz saqlandi — asosiysi mashq "
    "qildingiz! Darsdagi namunalar bilan o'zingiz solishtirib ko'ring."
)


@router.post("/eval/writing")
async def eval_writing(
    body: WritingEvalBody,
    user: User = Depends(get_current_user),
):
    from config import settings

    lesson = load_lesson_v2(body.lesson_id) or {}
    task = (lesson.get("skills") or {}).get("writing", {}).get("task_uz", "")

    if not settings.anthropic_api_key or not body.text.strip():
        return {"ai": False, "feedback_uz": FALLBACK_FEEDBACK}

    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        resp = await client.messages.create(
            model="claude-opus-4-8",
            max_tokens=800,
            system=(
                "Sen arab tili o'qituvchisisan. O'zbek tilida so'zlashuvchi "
                "boshlang'ich o'quvchining yozma ishini bahola. Javobing qisqa "
                "(3-5 jumla), o'zbek tilida (lotin), samimiy va rag'batlantiruvchi. "
                "Xatolarni ko'rsat, to'g'ri variantini yoz. Baho qo'yma."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"Topshiriq: {task}\n\nO'quvchi yozgani:\n{body.text}",
                }
            ],
        )
        feedback = next(
            (b.text for b in resp.content if b.type == "text"), FALLBACK_FEEDBACK
        )
        return {"ai": True, "feedback_uz": feedback}
    except Exception:
        return {"ai": False, "feedback_uz": FALLBACK_FEEDBACK}
