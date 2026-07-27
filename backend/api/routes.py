import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    ClientError,
    Placement,
    Plan,
    Progress,
    User,
    UserWord,
    XpLog,
)
from services import roots as roots_svc
from db.session import get_session
from services.ai import generate_plan
from services.course import course_all_levels, start_lesson_for
from services.achievements import check_and_award, list_achievements
from services.ai import XP_BY_MINUTES
from services.league import leaderboard
from services import feedback as feedback_svc
from services import placement as placement_svc
from services import profile as profile_svc
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
        # Daraja qaysi versiyadagi placement testi bilan aniqlangan.
        # Joriy versiyadan past bo'lsa — ilova bir martalik qayta test so'raydi.
        "placement_version": plan.placement_version or 0,
        "placement_current": placement_svc.PLACEMENT_VERSION,
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
    level = plan.level if plan else "A0"
    done = await completed_lesson_ids(session, user.id)
    return course_all_levels(done, current_level=level)


SESSION_LIMIT = 20  # bitta takror sessiyasidagi maksimal kartalar


@router.get("/review")
async def review_cards(
    deck: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await seed_user_words(session, user.id)
    today = _today().isoformat()

    all_due = (
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

    # Deck bo'yicha soni (MSA / Hijoziy almashtirgich uchun)
    msa_due = sum(1 for w in all_due if w.deck != "hejazi")
    hejazi_due = sum(1 for w in all_due if w.deck == "hejazi")

    # Tanlangan deck bo'yicha filtrlash (bo'lmasa — hammasi)
    rows = all_due
    if deck in ("msa", "hejazi"):
        rows = [w for w in all_due if (w.deck == "hejazi") == (deck == "hejazi")]

    cards = [
        {
            "id": w.id,
            "ar": w.ar,
            "translit": w.translit,
            "uz": w.uz,
            "audio": w.audio,
            "kind": w.kind,
            "deck": w.deck,
        }
        for w in rows[:SESSION_LIMIT]
    ]
    return {
        "cards": cards,
        "total_due": len(rows),
        "msa_due": msa_due,
        "hejazi_due": hejazi_due,
    }


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
    period: str = "week",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if period not in ("week", "month", "all"):
        period = "week"
    return await leaderboard(session, user.id, period)


# ──────────────── Daraja aniqlash testi (placement, AI'siz) ────────────────


@router.get("/placement/next")
async def placement_next(
    passed: str = "",
    user: User = Depends(get_current_user),
):
    """Keyingi bosqich savollari.

    `passed` — shu paytgacha bo'lgan natijalar, masalan "A0:1,A1:0".
    Bo'sh bo'lsa test boshidan (A0) beriladi.
    """
    results: dict[str, bool] = {}
    for part in filter(None, passed.split(",")):
        tier, _, ok = part.partition(":")
        if tier in placement_svc.TIERS:
            results[tier] = ok == "1"

    tier = placement_svc.next_tier(results)
    if tier is None:
        level = placement_svc.decide_level(results)
        return {
            "done": True,
            "level": level,
            "reason": placement_svc.level_reason(level, results),
        }
    return {
        "done": False,
        "tier": tier,
        "tier_title": placement_svc.tier_title(tier),
        "tier_index": placement_svc.TIERS.index(tier) + 1,
        "tier_count": len(placement_svc.TIERS),
        "pass_ratio": placement_svc.pass_ratio(),
        "items": placement_svc.tier_questions(tier),
    }


class PlacementFinish(BaseModel):
    """Test tugagach yakuniy natija — daraja saqlanadi."""

    results: dict[str, bool] = Field(default_factory=dict)


@router.post("/placement/finish")
async def placement_finish(
    body: PlacementFinish,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    results = {
        t: bool(v) for t, v in body.results.items() if t in placement_svc.TIERS
    }
    level = placement_svc.decide_level(results)
    reason = placement_svc.level_reason(level, results)
    start = start_lesson_for(level)

    plan = (
        await session.execute(
            select(Plan).where(Plan.user_id == user.id).order_by(Plan.id.desc()).limit(1)
        )
    ).scalar_one_or_none()

    if plan:
        plan.level = level
        plan.level_reason = reason
        plan.start_lesson = start
        plan.placement_version = placement_svc.PLACEMENT_VERSION
        session.add(plan)
        await session.commit()

    session.add(
        Placement(
            user_id=user.id,
            answers_json=json.dumps({"source": "placement_v2"}, ensure_ascii=False),
            test_json=json.dumps(results, ensure_ascii=False),
        )
    )
    await session.commit()

    return {
        "level": level,
        "reason": reason,
        "start_lesson": start,
        "saved": plan is not None,
    }


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

    # Imtihon statistikasi (Hanyu uslubidagi STATISTIKA bo'limi uchun)
    from sqlalchemy import func

    from db.models import ExamAttempt

    exam_rows = (
        await session.execute(
            select(ExamAttempt).where(
                ExamAttempt.user_id == user.id,
                ExamAttempt.finished_at.isnot(None),
            )
        )
    ).scalars().all()
    exams_passed = sum(1 for a in exam_rows if a.passed)
    best_exam = max((a.total_score for a in exam_rows), default=0)

    cards_total = (
        await session.execute(
            select(func.count()).select_from(UserWord).where(UserWord.user_id == user.id)
        )
    ).scalar_one()
    # "Joriy xatolar" — kamida bir marta adashilgan va hozir takrori kelganlar
    mistakes_now = (
        await session.execute(
            select(func.count()).select_from(UserWord).where(
                UserWord.user_id == user.id,
                UserWord.lapses > 0,
                UserWord.due_date <= _today().isoformat(),
            )
        )
    ).scalar_one()

    # Onboarding'dagi maqsad (sabab) — oxirgi placementdan
    goal = ""
    pl = (
        await session.execute(
            select(Placement).where(Placement.user_id == user.id).order_by(Placement.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if pl:
        goal = json.loads(pl.answers_json or "{}").get("goal", "")

    return {
        "name": user.name,
        "username": user.username,
        "level": plan.level if plan else "A0",
        "target_level": plan.target_level if plan else "",
        "target_date": plan.target_date if plan else "",
        "daily_minutes": plan.daily_minutes if plan else 20,
        "daily_xp_goal": plan.daily_xp_goal if plan else 30,
        "goal": goal,
        "exams_passed": exams_passed,
        "best_exam": best_exam,
        "cards_total": cards_total,
        "mistakes_now": mistakes_now,
        "stats": stats,
        **extras,
        "achievements": achievements,
    }


@router.post("/settings/reset-plan")
async def reset_plan(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Rejani tozalash — foydalanuvchi onboardingdan qayta o'tadi.
    XP/streak/progress/SRS saqlanadi."""
    from sqlalchemy import delete

    await session.execute(delete(Plan).where(Plan.user_id == user.id))
    await session.execute(delete(Placement).where(Placement.user_id == user.id))
    await session.commit()
    return {"ok": True}


@router.get("/practice/weak")
async def practice_weak(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Zaif so'zlar testi — eng ko'p adashilgan/kechikkan kartalardan mcq."""
    import random as _random

    rows = (
        await session.execute(
            select(UserWord)
            .where(UserWord.user_id == user.id, UserWord.card_type.in_(["word", "phrase"]))
            .order_by(UserWord.lapses.desc(), UserWord.due_date)
            .limit(30)
        )
    ).scalars().all()

    if len(rows) < 4:
        return {"items": [], "reason": "kam_soz"}

    picked = rows[:10]
    all_uz = [w.uz.split("·")[0].strip() for w in rows if w.uz]
    items = []
    for w in picked:
        correct = w.uz.split("·")[0].strip()
        distractors = [u for u in all_uz if u and u != correct]
        _random.shuffle(distractors)
        items.append(
            {
                "type": "mcq",
                "q_uz": "Bu so'zning ma'nosi?",
                "q_ar": w.ar,
                "audio": w.audio or "",
                "options": [correct, *distractors[:3]],
                "answer": correct,
                "explain_uz": "",
                "root": "",
                "pattern": "",
                "words": [],
            }
        )
    _random.shuffle(items)
    return {"items": items}


class WeakCompleteBody(BaseModel):
    correct: int = Field(ge=0)
    total: int = Field(ge=1)
    wrong_words: list[str] = Field(default_factory=list)


@router.post("/practice/weak/complete")
async def practice_weak_complete(
    body: WeakCompleteBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from services.srs import reset_words

    xp = max(1, body.correct)
    session.add(XpLog(user_id=user.id, amount=xp, source="practice:weak"))
    await session.commit()
    await reset_words(session, user.id, body.wrong_words)
    return {"xp_earned": xp}


class FeedbackBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    context: str = Field(default="", max_length=64)


@router.post("/feedback")
async def submit_feedback(
    body: FeedbackBody,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Ilova ichidan yuborilgan fikr — saqlanadi va adminga yetkaziladi."""
    fb = await feedback_svc.save(
        session, user.id, body.text.strip(), source="app", context=body.context
    )
    await feedback_svc.notify_admin(
        getattr(request.app.state, "bot", None), fb, user
    )
    return {"ok": True}


class ClientErrorBody(BaseModel):
    message: str = Field(max_length=2000)
    context: str = Field(default="", max_length=128)


@router.post("/client-error")
async def report_client_error(
    body: ClientErrorBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Player/ilovadagi JS xatosini backend logiga yozadi."""
    msg = (body.message or "").strip()
    if not msg:
        return {"ok": False}
    session.add(
        ClientError(user_id=user.id, message=msg[:2000], context=body.context[:128])
    )
    await session.commit()
    print(f"⚠️ CLIENT-ERROR [{body.context}] user={user.tg_id}: {msg[:200]}")
    return {"ok": True}


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


class NameBody(BaseModel):
    name: str = Field(max_length=100)


@router.post("/settings/name")
async def update_name(
    body: NameBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Foydalanuvchi o'z ismini o'zgartiradi (sertifikat va reytingda ko'rinadi)."""
    name, error = profile_svc.validate_name(body.name)
    if error:
        raise HTTPException(status_code=400, detail=error)

    user.name = name
    session.add(user)
    await session.commit()
    return {"name": user.name}


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
    # HIMOYA: rejasi bor foydalanuvchi onboardingga qaytmasligi kerak.
    # (Ilgari server bir lahza javob bermasa ilova onboardingni ko'rsatardi —
    # shunda yangi reja yozilib, daraja va boshlash nuqtasi nolga tushardi.)
    # Haqiqiy qayta-onboarding /settings/reset-plan orqali bo'ladi — u avval
    # rejani o'chiradi, shuning uchun bu yerga kelganda reja bo'lmaydi.
    existing = await latest_plan(session, user.id)
    if existing is not None:
        return {"ai_used": False, "plan": plan_to_dict(existing), "kept": True}

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
        start_lesson=start_lesson_for(generated.level),
    )
    session.add(plan)
    await session.commit()

    return {"ai_used": ai_used, "plan": plan_to_dict(plan)}


# ─────────────────── Ma'lumotnoma: grammatika va lug'at ───────────────────


@router.get("/reference/stats")
async def reference_stats_route(user: User = Depends(get_current_user)):
    from services.reference import reference_stats

    return reference_stats()


@router.get("/reference/grammar")
async def reference_grammar(
    q: str = "",
    level: str = "",
    user: User = Depends(get_current_user),
):
    """Butun kurs bo'ylab grammatika qoidalari (qidiruv + daraja filtri)."""
    from services.reference import search_grammar

    return search_grammar(q[:100], level[:4].upper())


@router.get("/reference/vocab")
async def reference_vocab(
    q: str = "",
    level: str = "",
    offset: int = 0,
    user: User = Depends(get_current_user),
):
    """Butun kurs lug'ati — arabcha, transliteratsiya, o'zbekcha yoki o'zak bo'yicha."""
    from services.reference import search_vocab

    return search_vocab(q[:100], level[:4].upper(), limit=60, offset=max(0, offset))
