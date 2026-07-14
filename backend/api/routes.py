import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Placement, Plan, Progress, User, UserWord, XpLog
from services import roots as roots_svc
from db.session import get_session
from services.ai import generate_plan
from services.content import (
    PLANNED_TITLES,
    flattened_lessons,
    lesson_index,
    load_modules,
    ordered_module_ids,
)
from services.achievements import check_and_award, list_achievements
from services.ai import XP_BY_MINUTES
from services.league import leaderboard
from services.srs import GRADES, apply_grade, seed_user_words
from services.stats import (
    _today,
    completed_lesson_ids,
    profile_extras,
    user_stats,
)
from services.telegram_auth import get_current_user

router = APIRouter(prefix="/api")


def plan_to_dict(plan: Plan) -> dict:
    return {
        "level": plan.level,
        "level_reason": plan.level_reason,
        "target_level": plan.target_level,
        "target_date": plan.target_date,
        "daily_xp_goal": plan.daily_xp_goal,
        "daily_minutes": plan.daily_minutes,
        "focus_areas": json.loads(plan.focus_areas_json),
        "module_order": json.loads(plan.module_order_json),
        "weekly_schedule": json.loads(plan.weekly_schedule_json),
        "motivation": plan.motivation,
    }


async def latest_plan(session: AsyncSession, user_id: int) -> Plan | None:
    result = await session.execute(
        select(Plan).where(Plan.user_id == user_id).order_by(Plan.id.desc()).limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/health")
async def health():
    return {"status": "ok", "app": "Arabiy"}


@router.get("/me")
async def me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    plan = await latest_plan(session, user.id)
    plan_order = json.loads(plan.module_order_json) if plan else None
    await seed_user_words(session, user.id)
    stats = await user_stats(session, user.id, plan_order)
    return {
        "name": user.name,
        "has_plan": plan is not None,
        "plan": plan_to_dict(plan) if plan else None,
        "stats": stats,
    }


@router.get("/modules")
async def modules_list(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    plan = await latest_plan(session, user.id)
    plan_order = json.loads(plan.module_order_json) if plan else None
    done = await completed_lesson_ids(session, user.id)
    flat = flattened_lessons(plan_order)

    all_modules = load_modules()
    result = []
    for mid in ordered_module_ids(plan_order):
        mod = all_modules[mid]
        lessons = []
        for lesson in mod["lessons"]:
            lid = lesson["id"]
            flat_idx = flat.index(lid)
            unlocked = flat_idx == 0 or flat[flat_idx - 1] in done
            lessons.append(
                {
                    "id": lid,
                    "title": lesson["title"],
                    "done": lid in done,
                    "unlocked": unlocked or lid in done,
                }
            )
        result.append(
            {
                "id": mid,
                "title": mod["title"],
                "arabic_title": mod.get("arabic_title", ""),
                "available": True,
                "done_count": sum(1 for l in lessons if l["done"]),
                "lessons": lessons,
            }
        )

    # Rejada bor, lekin hali yozilmagan modullar — "tez orada"
    coming = [
        {"id": m, "title": PLANNED_TITLES.get(m, m), "available": False}
        for m in (plan_order or [])
        if m not in all_modules and m in PLANNED_TITLES
    ]

    return {"modules": result, "coming_soon": coming}


@router.get("/lessons/{lesson_id}")
async def lesson_detail(
    lesson_id: str,
    user: User = Depends(get_current_user),
):
    info = lesson_index().get(lesson_id)
    if not info:
        raise HTTPException(status_code=404, detail="Dars topilmadi")
    return {
        **info["lesson"],
        "module_title": info["module_title"],
        "pos": info["pos"],
        "count": info["count"],
    }


class CompleteBody(BaseModel):
    correct: int = Field(ge=0)
    total: int = Field(ge=1)


@router.post("/lessons/{lesson_id}/complete")
async def lesson_complete(
    lesson_id: str,
    body: CompleteBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if lesson_id not in lesson_index():
        raise HTTPException(status_code=404, detail="Dars topilmadi")

    correct = min(body.correct, body.total)
    perfect = correct == body.total

    done_before = await completed_lesson_ids(session, user.id)
    first_time = lesson_id not in done_before

    if first_time:
        xp = 10 + 2 * correct + (5 if perfect else 0)
    else:
        # Takror mashq — kamaytirilgan XP
        xp = 5 + correct

    session.add(
        Progress(
            user_id=user.id,
            lesson_id=lesson_id,
            correct=correct,
            total=body.total,
            xp_earned=xp,
        )
    )
    session.add(XpLog(user_id=user.id, amount=xp, source=f"lesson:{lesson_id}"))
    await session.commit()

    # Yangi o'rganilgan elementlarni SRS kartotekasiga qo'shamiz
    await seed_user_words(session, user.id)

    plan = await latest_plan(session, user.id)
    plan_order = json.loads(plan.module_order_json) if plan else None
    stats = await user_stats(session, user.id, plan_order)

    new_badges = await check_and_award(session, user.id, stats["streak"])

    return {
        "xp_earned": xp,
        "perfect": perfect,
        "first_time": first_time,
        "stats": stats,
        "new_badges": new_badges,
    }


SESSION_LIMIT = 20  # bitta takror sessiyasidagi maksimal kartalar


@router.get("/review")
async def review_cards(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await seed_user_words(session, user.id)
    today = _today().isoformat()

    rows = (
        (
            await session.execute(
                select(UserWord)
                .where(UserWord.user_id == user.id, UserWord.due_date <= today)
                .order_by(UserWord.due_date, UserWord.id)
            )
        )
        .scalars()
        .all()
    )

    cards = [
        {
            "id": w.id,
            "ar": w.ar,
            "translit": w.translit,
            "uz": w.uz,
            "audio": w.audio,
            "kind": w.kind,
        }
        for w in rows[:SESSION_LIMIT]
    ]
    return {"cards": cards, "total_due": len(rows)}


class ReviewAnswerBody(BaseModel):
    word_id: int
    grade: str


@router.post("/review/answer")
async def review_answer(
    body: ReviewAnswerBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if body.grade not in GRADES:
        raise HTTPException(status_code=422, detail="Noto'g'ri baho")

    word = (
        await session.execute(
            select(UserWord).where(
                UserWord.id == body.word_id, UserWord.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if word is None:
        raise HTTPException(status_code=404, detail="Karta topilmadi")

    apply_grade(word, body.grade)

    xp = 0
    if body.grade != "again":
        xp = 1
        session.add(XpLog(user_id=user.id, amount=xp, source="review"))

    session.add(word)
    await session.commit()

    stats = await user_stats(session, user.id, None)
    new_badges = await check_and_award(session, user.id, stats["streak"])

    return {
        "xp": xp,
        "interval_days": word.interval_days,
        "due_date": word.due_date,
        "new_badges": new_badges,
    }


@router.get("/leaderboard")
async def leaderboard_route(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await leaderboard(session, user.id)


@router.get("/achievements")
async def achievements_route(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await list_achievements(session, user.id)


# ─────────────────────── Root Lab (o'zak-vazn) ───────────────────────


@router.get("/roots")
async def roots_list(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    seen = await roots_svc.seen_roots(session, user.id)
    items = roots_svc.roots_summary()
    for it in items:
        it["seen"] = it["root"] in seen
    return {"roots": items, "seen_count": len(seen), "total": len(items)}


@router.get("/roots/{root:path}")
async def root_detail(
    root: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    detail = roots_svc.root_detail(root)
    if detail is None:
        raise HTTPException(status_code=404, detail="O'zak topilmadi")
    await roots_svc.record_seen(session, user.id, root)
    return detail


class AddRootCardsBody(BaseModel):
    root: str


@router.post("/roots/add-to-srs")
async def add_root_to_srs(
    body: AddRootCardsBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """O'zak + uning so'zlarini SRS kartotekasiga qo'shadi (Root Lab'dan)."""
    detail = roots_svc.root_detail(body.root)
    if detail is None:
        raise HTTPException(status_code=404, detail="O'zak topilmadi")

    from services.stats import _today

    existing = set(
        (
            await session.execute(
                select(UserWord.ar).where(UserWord.user_id == user.id)
            )
        ).scalars()
    )
    today = _today().isoformat()
    added = 0

    # O'zak kartasi
    cognates = ", ".join(detail.get("uz_cognates", [])[:5])
    root_back = f"{detail['meaning_uz']} → {cognates}"
    if detail["root"] not in existing:
        session.add(
            UserWord(
                user_id=user.id, ar=detail["root"], uz=root_back,
                audio=detail.get("audio", ""), kind="root",
                card_type="root", deck="msa", due_date=today,
            )
        )
        existing.add(detail["root"])
        added += 1

    # Yasalgan so'zlar
    for d in detail.get("derived", []):
        if d["ar"] in existing:
            continue
        session.add(
            UserWord(
                user_id=user.id, ar=d["ar"], translit=d.get("uz_cognate", ""),
                uz=d["uz"], audio=d.get("audio", ""), kind="word",
                card_type="word", deck="msa", due_date=today,
            )
        )
        existing.add(d["ar"])
        added += 1

    await session.commit()
    return {"added": added}


@router.get("/profile")
async def profile_route(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    plan = await latest_plan(session, user.id)
    plan_order = json.loads(plan.module_order_json) if plan else None
    stats = await user_stats(session, user.id, plan_order)
    extras = await profile_extras(session, user.id)
    achievements = await list_achievements(session, user.id)

    return {
        "name": user.name,
        "username": user.username,
        "level": plan.level if plan else "A0",
        "target_level": plan.target_level if plan else "",
        "target_date": plan.target_date if plan else "",
        "daily_minutes": plan.daily_minutes if plan else 20,
        "daily_xp_goal": plan.daily_xp_goal if plan else 30,
        "stats": stats,
        **extras,
        "achievements": achievements,
    }


class GoalBody(BaseModel):
    daily_minutes: int = Field(ge=1, le=240)


@router.post("/settings/goal")
async def update_goal(
    body: GoalBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    plan = await latest_plan(session, user.id)
    if plan is None:
        raise HTTPException(status_code=400, detail="Reja topilmadi")

    plan.daily_minutes = body.daily_minutes
    plan.daily_xp_goal = XP_BY_MINUTES.get(body.daily_minutes, 30)
    session.add(plan)
    await session.commit()

    return {
        "daily_minutes": plan.daily_minutes,
        "daily_xp_goal": plan.daily_xp_goal,
    }


class OnboardingBody(BaseModel):
    name: str = Field(max_length=64)
    goal: str
    self_level: str
    target: str
    duration: str
    focus: list[str]
    daily_minutes: int
    test: dict = Field(default_factory=dict)


@router.post("/onboarding")
async def onboarding(
    body: OnboardingBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    answers = body.model_dump(exclude={"test"})

    # Foydalanuvchi kiritgan ismni saqlaymiz
    if body.name.strip():
        user.name = body.name.strip()
        session.add(user)

    session.add(
        Placement(
            user_id=user.id,
            answers_json=json.dumps(answers, ensure_ascii=False),
            test_json=json.dumps(body.test, ensure_ascii=False),
        )
    )

    generated, ai_used = await generate_plan(answers, body.test)

    plan = Plan(
        user_id=user.id,
        level=generated.level,
        level_reason=generated.level_reason,
        target_level=generated.target_level,
        target_date=generated.target_date,
        daily_xp_goal=generated.daily_xp_goal,
        daily_minutes=generated.daily_minutes,
        focus_areas_json=json.dumps(generated.focus_areas, ensure_ascii=False),
        module_order_json=json.dumps(generated.module_order, ensure_ascii=False),
        weekly_schedule_json=json.dumps(
            [d.model_dump() for d in generated.weekly_schedule], ensure_ascii=False
        ),
        motivation=generated.motivation,
    )
    session.add(plan)
    await session.commit()

    return {"ai_used": ai_used, "plan": plan_to_dict(plan)}
