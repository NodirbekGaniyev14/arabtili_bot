"""Curriculum v2 API — yangi dars playeri endpointlari (K2).

/api/v2/* — v1 (jonli kurs) endpointlariga tegmaydi.
"""

import json
import random
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    DailySpeaking,
    DrillResult,
    ListeningResult,
    TutorRating,
    LessonRating,
    MockResult,
    Plan,
    Progress,
    TraceResult,
    TutorMistake,
    TutorTurn,
    User,
    WritingResult,
    XpLog,
    utcnow,
)
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
    request: Request,
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

    # Taklif mukofoti: taklif qilingan o'quvchi birinchi darsni o'tdi (K18.1)
    referral_bonus = None
    if passed and user.invited_by is not None and not user.ref_rewarded:
        from services import referral

        referral_bonus = await referral.on_lesson_passed(
            session, user, getattr(request.app.state, "bot", None)
        )

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
        "referral_bonus": referral_bonus,
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
    session: AsyncSession = Depends(get_session),
):
    from services import ai_usage, roleplay

    if not body.history:
        op = roleplay.opening(body.scenario_id)
        if op is None:
            raise HTTPException(status_code=404, detail="Vaziyat topilmadi")
        return op
    # Faqat oxirgi 12 xabar (kontekstni cheklaymiz)
    out = await roleplay.reply(body.scenario_id, body.history[-12:])
    usage = out.pop("usage", None)
    if usage:
        ai_usage.record(session, "roleplay", usage, user.id)
        await session.commit()
    return out


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
    session: AsyncSession = Depends(get_session),
):
    from config import settings
    from services import ai_usage

    lesson = load_lesson_v2(body.lesson_id) or {}
    task = (lesson.get("skills") or {}).get("writing", {}).get("task_uz", "")

    if not settings.anthropic_api_key or not body.text.strip():
        return {"ai": False, "feedback_uz": FALLBACK_FEEDBACK}

    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        resp = await client.messages.create(
            # Qisqa baho uchun Haiku yetarli — Opus'dan ~15x arzon
            model=settings.tutor_model,
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
        ai_usage.record(session, "writing", ai_usage.usage_of(resp), user.id)
        await session.commit()
        return {"ai": True, "feedback_uz": feedback}
    except Exception:
        return {"ai": False, "feedback_uz": FALLBACK_FEEDBACK}


# ─────────────────── AI ustoz — jonli suhbat (K17) ───────────────────
# services/tutor.py (Haiku 4.5, structured output), services/stt.py (Groq
# Whisper), services/tts.py (edge-tts cache). Kunlik limit — token xarajati
# nazorati: har chaqiruv (ochilish ham) bitta "turn" sifatida sanaladi.

_SESSION_KEY_RE = r"^[A-Za-z0-9_-]{8,36}$"
_AUDIO_KEY_RE = re.compile(r"^[0-9a-f]{24}$")


async def _user_level(session: AsyncSession, user_id: int) -> str:
    plan = (
        await session.execute(
            select(Plan.level).where(Plan.user_id == user_id).order_by(Plan.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    return (plan or "A0").upper()


async def _tutor_turns_today(session: AsyncSession, user_id: int) -> int:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = start.replace(tzinfo=None)  # DB'da naive UTC (models.utcnow)
    n = (
        await session.execute(
            select(func.count(TutorTurn.id)).where(
                TutorTurn.user_id == user_id, TutorTurn.created_at >= start
            )
        )
    ).scalar_one()
    return int(n or 0)


async def _tutor_access(session: AsyncSession, user: User) -> dict:
    """VIP → to'liq limit; bepul → TUTOR_FREE_TURNS (tatib ko'rish)."""
    from config import settings
    from services import billing

    vip = billing.is_vip(user)
    limit = settings.tutor_daily_turns if vip else settings.tutor_free_turns
    used = await _tutor_turns_today(session, user.id)
    return {
        "vip": vip,
        "vip_days_left": billing.vip_days_left(user),
        "daily_limit": limit,
        "turns_left": max(limit - used, 0),
        "used": used,
    }


@router.get("/tutor/topics")
async def tutor_topics(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from config import settings
    from services import billing, referral, stt, tutor

    level = await _user_level(session, user.id)
    access = await _tutor_access(session, user)
    # So'nggi mock natijalari — o'quvchi o'sishini ko'rsin
    recent = (
        await session.execute(
            select(MockResult.mock_id, MockResult.score, MockResult.created_at)
            .where(MockResult.user_id == user.id)
            .order_by(MockResult.id.desc())
            .limit(10)
        )
    ).all()
    return {
        "level": level,
        "topics": tutor.topic_list(level),
        "mocks": tutor.mock_list(level),
        "mock_results": [
            {"mock_id": r[0], "score": r[1], "date": r[2].strftime("%d.%m")} for r in recent
        ],
        **{k: v for k, v in access.items() if k != "used"},
        "free_turns": settings.tutor_free_turns,
        "vip_turns": settings.tutor_daily_turns,
        "trial_available": referral.trial_available(user),
        "trial_days": referral.TRIAL_DAYS,
        "price": billing.price_summary(),
        "ai": bool(settings.anthropic_api_key),
        "voice": stt.available(),
    }


class TutorTurnBody(BaseModel):
    session_key: str = Field(pattern=_SESSION_KEY_RE)
    topic_id: str = Field(default="erkin", max_length=24)
    # [{role:'user'|'assistant', content}] — assistant = faqat `ar` matni
    history: list[dict] = Field(default_factory=list, max_length=60)
    voice: bool = False  # oxirgi javob mikrofondan keldi
    mode: str = Field(default="chat", pattern=r"^(chat|mock)$")
    mock_id: str = Field(default="", max_length=24)


@router.post("/tutor/turn")
async def tutor_turn(
    body: TutorTurnBody,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from config import settings
    from services import ai_usage, alerts, tts, tutor

    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="AI ustoz hozircha o'chiq")

    access = await _tutor_access(session, user)
    if access["turns_left"] <= 0:
        if not access["vip"]:
            # 402 — klient paywall'ni ochadi
            raise HTTPException(
                status_code=402, detail="Bepul javoblar tugadi — VIP bilan davom eting"
            )
        raise HTTPException(
            status_code=429, detail="Bugungi suhbat limiti tugadi — ertaga davom eting"
        )

    level = await _user_level(session, user.id)
    known = await tutor.known_words(session, user.id)
    for m in body.history:
        if len(str(m.get("content", ""))) > 600:
            raise HTTPException(status_code=422, detail="Xabar juda uzun")

    learner_answered = bool(body.history) and body.history[-1].get("role") == "user"
    crit = {"vocab": -1, "grammar": -1, "content": -1, "pron": -1}
    try:
        if body.mode == "mock":
            reply, usage = await tutor.reply_mock(
                name=user.name,
                level=level,
                mock_id=body.mock_id,
                history=body.history,
                known=known,
            )
            if learner_answered:
                # Talaffuz (aniqlik) — oxirgi /tutor/transcribe ishonch bali (server xotirasi)
                pron = _take_voice_conf(user.id, body.session_key) if body.voice else -1
                reply.score = tutor.mock_overall(reply.vocab, reply.grammar, reply.content, pron)
                crit = {
                    "vocab": reply.vocab, "grammar": reply.grammar,
                    "content": reply.content, "pron": pron,
                }
            ok = reply.score >= 50 if learner_answered else True
            score = reply.score if learner_answered else -1
        else:
            reply, usage = await tutor.reply(
                name=user.name,
                level=level,
                topic_id=body.topic_id,
                history=body.history,
                known=known,
            )
            ok = reply.correction_ok if learner_answered else True
            score = -1
    except tutor.TutorUnavailable as e:
        # Turn hisobga olinmaydi — o'quvchi limiti kuymaydi. Kredit/kalit
        # muammosi — admin Telegram'da darhol biladi (kuniga bir marta)
        if e.kind in ("credit", "auth"):
            alerts.fire(getattr(request.app.state, "bot", None), e.kind)
        raise HTTPException(status_code=503, detail=e.message_uz)

    ai_usage.record(session, "mock" if body.mode == "mock" else "tutor", usage, user.id)
    if learner_answered:
        await _note_mistake(session, user.id, body, reply, score)
    # O'quvchi javob bergan turn (ochilish emas) — limit va statistika uchun
    session.add(
        TutorTurn(
            user_id=user.id,
            session_key=body.session_key,
            topic=(body.mock_id if body.mode == "mock" else body.topic_id)[:24],
            level=level,
            ok=1 if ok else 0,
            voice=1 if (learner_answered and body.voice) else 0,
            mode=body.mode,
            score=score,
            **crit,
        )
    )
    await session.commit()

    # Matn darhol ketadi, mp3 fonda tayyorlanadi (edge-tts 1-3 s) — klient
    # audio'ni kechroq, tayyor bo'lganda yuklaydi (audio.ts: playUrl retry)
    audio_key = tts.schedule(reply.ar, level)
    return {
        "reply": {**reply.model_dump(), "pron": crit["pron"]},
        "audio_url": f"/api/v2/tutor/audio/{audio_key}.mp3" if audio_key else "",
        "turns_left": max(access["turns_left"] - 1, 0),
        "vip": access["vip"],
        "usage": usage,
    }


MISTAKE_KEEP = 300  # har o'quvchi uchun daftarda saqlanadigan eng ko'p yozuv
MOCK_MISTAKE_BELOW = 70  # mock javobi shundan past bo'lsa daftarga tushadi


async def _note_mistake(session: AsyncSession, user_id: int, body, reply, score: int) -> None:
    """Xatolar daftari: ustoz tuzatgan jumla (chat) yoki past mock javobi.
    O'quvchi keyin ko'rib, eshitib, qayta aytib mashq qiladi (/tutor/log)."""
    said = str(body.history[-1].get("content", "")).removeprefix("🎤").strip()[:400]
    if not said:
        return
    if body.mode == "mock":
        if not (0 <= score < MOCK_MISTAKE_BELOW) or not getattr(reply, "ideal_ar", ""):
            return
        row = TutorMistake(
            user_id=user_id, kind="mock", topic=body.mock_id[:24], said_ar=said,
            fixed_ar=reply.ideal_ar[:400], note_uz=(reply.feedback_uz or "")[:400],
        )
    else:
        if reply.correction_ok or not reply.fixed_ar:
            return
        row = TutorMistake(
            user_id=user_id, kind="chat", topic=body.topic_id[:24], said_ar=said,
            fixed_ar=reply.fixed_ar[:400], note_uz=(reply.note_uz or "")[:400],
        )
    session.add(row)
    # Daftar cheksiz o'smasin — eng eskilari o'chadi
    ids = (
        await session.execute(
            select(TutorMistake.id)
            .where(TutorMistake.user_id == user_id)
            .order_by(TutorMistake.id.desc())
            .offset(MISTAKE_KEEP)  # yangi qator autoflush bilan hisobda
        )
    ).scalars().all()
    for mid in ids:
        old = await session.get(TutorMistake, mid)
        if old is not None:
            await session.delete(old)


@router.get("/tutor/audio/{key}.mp3")
async def tutor_audio(key: str):
    """Ustoz javobining mp3'si. Kalit — matn xeshi, sirli ma'lumot yo'q,
    shuning uchun <audio src> to'g'ridan-to'g'ri (initData'siz) yuklay oladi."""
    from services import tts

    if not _AUDIO_KEY_RE.match(key):
        raise HTTPException(status_code=404)
    path = tts.path_for(key)
    if not path.exists():
        # Fonda hali tayyorlanayotgan bo'lsa — biroz kutamiz (klient retry ham qiladi)
        await tts.wait_for(key, timeout=6)
    if not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(
        path, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=604800"}
    )


async def _read_audio(file: UploadFile) -> bytes:
    from services.stt import MAX_AUDIO_BYTES

    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Audio bo'sh")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio juda uzun (maks. 20 soniya)")
    return data


# Mock talaffuz mezoni: /tutor/transcribe ishonch balini sessiya bo'yicha saqlaymiz,
# keyingi /tutor/turn (voice=true) uni oladi — klient soxta ball yubora olmaydi
_voice_conf: dict[tuple[int, str], tuple[int, float]] = {}
VOICE_CONF_TTL = 600.0


def _put_voice_conf(user_id: int, session_key: str, conf: int) -> None:
    import time

    now = time.time()
    if len(_voice_conf) > 5000:
        for k in [k for k, v in _voice_conf.items() if now - v[1] > VOICE_CONF_TTL]:
            _voice_conf.pop(k, None)
    _voice_conf[(user_id, session_key)] = (conf, now)


def _take_voice_conf(user_id: int, session_key: str) -> int:
    import time

    v = _voice_conf.pop((user_id, session_key), None)
    if v is None or time.time() - v[1] > VOICE_CONF_TTL:
        return -1
    return v[0]


STT_DAILY_CAP = 200  # har o'quvchi kuniga shuncha ovoz yozuvi — Groq bepul limiti himoyasi
_stt_used: dict[int, tuple[str, int]] = {}


def _stt_quota(user_id: int) -> None:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    d, n = _stt_used.get(user_id, (day, 0))
    if d != day:
        n = 0
    if n >= STT_DAILY_CAP:
        raise HTTPException(status_code=429, detail="Bugungi ovoz limiti tugadi — ertaga davom eting")
    _stt_used[user_id] = (day, n + 1)


async def _badges(session: AsyncSession, user_id: int) -> list[dict]:
    """Speaking/yozuv yakunida yangi nishonlar (xato bo'lsa — bo'sh, oqim buzilmasin)."""
    try:
        stats = await user_stats(session, user_id)
        return await check_and_award(session, user_id, stats["streak"])
    except Exception as e:  # pragma: no cover — nishon oqimni to'xtatmasin
        import logging

        logging.getLogger(__name__).warning("badge tekshiruvi xatosi: %r", e)
        return []


def _stt_failed(request: Request) -> None:
    """STT xizmat xatosi (kalit/tarmoq) — o'quvchiga 503, adminga ogohlantirish.
    Oddiy «tushunilmadi» (bo'sh matn, 200) va yaroqsiz audio (400) bu yerga kirmaydi."""
    from services import alerts, stt

    err = stt.last_error
    if not err or err == "http:400":
        return
    bot = getattr(request.app.state, "bot", None)
    if err == "auth":
        alerts.fire(bot, "stt_auth")
    elif err == "rate":
        alerts.fire(bot, "stt_rate")
        raise HTTPException(
            status_code=503, detail="Ovoz xizmati band — 10 soniyadan keyin yana bosing."
        )
    else:
        alerts.fire(bot, "stt_down", err)
    raise HTTPException(
        status_code=503, detail="Ovoz xizmati vaqtincha ishlamayapti — admin xabardor."
    )


@router.post("/tutor/transcribe")
async def tutor_transcribe(
    request: Request,
    file: UploadFile = File(...),
    prompt: str = Form(""),
    session_key: str = Form("", max_length=36),
    topic_id: str = Form("", max_length=24),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Mikrofon yozuvi → arabcha matn. `prompt` — oxirgi ustoz savoli (kontekst),
    `topic_id` — mavzu/mock: uning lug'ati Whisper prompt'iga qo'shiladi (o'quvchi
    aytishi mumkin bo'lgan so'zlar tanish bo'ladi). `session_key` berilsa aniqlik
    bali keyingi mock javobi uchun saqlanadi."""
    from services import stt, tutor

    if not stt.available():
        raise HTTPException(status_code=503, detail="Ovoz xizmati sozlanmagan")
    data = await _read_audio(file)
    _stt_quota(user.id)
    words: list[str] = []
    meta = tutor.TOPIC_BY_ID.get(topic_id) or tutor.MOCK_BY_ID.get(topic_id)
    if meta and meta.get("themes"):
        level = await _user_level(session, user.id)
        words = [w["ar"] for w in tutor.topic_words(level, meta["themes"], set())[:40]]
    text, conf = await stt.transcribe_ex(
        data, file.filename or "speech.webm", file.content_type or "audio/webm",
        stt.build_prompt(prompt[:300], words),
    )
    if not text:
        _stt_failed(request)
    if session_key and text:
        _put_voice_conf(user.id, session_key, conf)
    return {"text": text, "confidence": conf}


@router.post("/tutor/pronounce")
async def tutor_pronounce(
    request: Request,
    file: UploadFile = File(...),
    target: str = Form("", max_length=400),
    drill_key: str = Form("", max_length=32),
    idx: int = Form(-1),
    user: User = Depends(get_current_user),
):
    """Takrorlash mashqi: o'quvchi jumlani aytadi → o'xshashlik bali.
    Whisper'ga maqsad matn BERILMAYDI — aks holda «eshitgandek» yozib qo'yadi.
    Talaffuz mashqida (drill_key+idx) maqsadni server o'zi biladi."""
    from services import drill, stt, tutor

    if not stt.available():
        raise HTTPException(status_code=503, detail="Ovoz xizmati sozlanmagan")
    if drill_key:
        target = drill.target(drill_key, user.id, idx)
        if not target:
            raise HTTPException(status_code=404, detail="Mashq topilmadi — qaytadan boshlang")
    if not target.strip():
        raise HTTPException(status_code=422, detail="Maqsad jumla yo'q")
    data = await _read_audio(file)
    _stt_quota(user.id)
    heard = await stt.transcribe(
        data, file.filename or "speech.webm", file.content_type or "audio/webm"
    )
    if not heard:
        _stt_failed(request)
    result = tutor.pronunciation_score(target, heard)
    if drill_key:
        drill.record(drill_key, user.id, idx, result["score"])
    return {"transcript": heard, **result}


# ─────────── Talaffuz mashqi (K17.5) — LLM'siz, bepul ───────────


@router.get("/tutor/drill")
async def tutor_drill(
    topic_id: str = "erkin",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Mavzu bo'yicha 10 ta jumla (audio fonda tayyorlanadi). VIP shart emas."""
    from services import drill, stt, tts

    level = await _user_level(session, user.id)
    key, items = drill.create(user.id, level, topic_id[:24])
    out = []
    for i, it in enumerate(items):
        audio_key = tts.schedule(it["ar"], level)
        out.append(
            {
                "idx": i,
                **it,
                "audio_url": f"/api/v2/tutor/audio/{audio_key}.mp3" if audio_key else "",
            }
        )
    return {
        "key": key,
        "level": level,
        "topic_id": topic_id if topic_id in drill.TOPIC_BY_ID else "erkin",
        "items": out,
        "voice": stt.available(),
    }


class DrillFinishBody(BaseModel):
    key: str = Field(min_length=8, max_length=32)


@router.post("/tutor/drill/finish")
async def tutor_drill_finish(
    body: DrillFinishBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Mashq yakuni: o'rtacha ball, XP (kamida 5 jumla; bir mavzu kuniga bir marta)."""
    from services import drill

    s = drill.summary(body.key, user.id)
    if s is None:
        raise HTTPException(status_code=404, detail="Mashq topilmadi")
    xp = drill.xp_for(s["score"], s["count"])
    if xp > 0:
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )
        earned = (
            await session.execute(
                select(DrillResult.id)
                .where(
                    DrillResult.user_id == user.id,
                    DrillResult.topic == s["topic"],
                    DrillResult.xp > 0,
                    DrillResult.created_at >= today,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if earned is not None:
            xp = 0
    if s["count"] > 0:
        session.add(
            DrillResult(
                user_id=user.id, topic=s["topic"], level=s["level"],
                score=s["score"], count=s["count"], xp=xp,
            )
        )
        if xp > 0:
            session.add(XpLog(user_id=user.id, amount=xp, source=f"drill:{body.key}"))
        await session.commit()
    drill.finish(body.key, user.id)
    return {
        "topic_id": s["topic"],
        "score": s["score"],
        "count": s["count"],
        "total": len(s["items"]),
        "xp": xp,
        "scores": s["scores"],
        "items": [{"ar": it["ar"], "uz": it["uz"]} for it in s["items"]],
        "new_badges": await _badges(session, user.id),
    }


# ─────────── Tinglab tushunish (K18.3) — LLM'siz, bepul ───────────


@router.get("/tutor/listen")
async def tutor_listen(
    topic_id: str = "erkin",
    kind: str = "choice",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """10 ta jumla: faqat audio (+ tanlash rejimida 4 variant). Matn javobdan keyin."""
    from services import listening, tts

    level = await _user_level(session, user.id)
    key, d = listening.create(user.id, level, topic_id[:24], kind)
    items = listening.public_items(d)
    for i, it in enumerate(d["items"]):
        audio_key = tts.schedule(it["ar"], level)
        items[i]["audio_url"] = f"/api/v2/tutor/audio/{audio_key}.mp3" if audio_key else ""
    return {"key": key, "kind": d["kind"], "level": level, "topic_id": d["topic"], "items": items}


class ListenAnswerBody(BaseModel):
    key: str = Field(min_length=8, max_length=32)
    idx: int = Field(ge=0, le=50)
    choice: int | None = Field(default=None, ge=0, le=10)
    text: str = Field(default="", max_length=400)


@router.post("/tutor/listen/answer")
async def tutor_listen_answer(
    body: ListenAnswerBody,
    user: User = Depends(get_current_user),
):
    from services import listening

    r = listening.answer(body.key, user.id, body.idx, body.choice, body.text)
    if r is None:
        raise HTTPException(status_code=404, detail="Mashq topilmadi — qaytadan boshlang")
    return r


@router.post("/tutor/listen/finish")
async def tutor_listen_finish(
    body: DrillFinishBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Yakun: o'rtacha, XP (kamida 5 jumla; mavzu+rejim uchun kuniga bir marta)."""
    from services import listening

    s = listening.summary(body.key, user.id)
    if s is None:
        raise HTTPException(status_code=404, detail="Mashq topilmadi")
    xp = listening.xp_for(s["score"], s["count"])
    if xp > 0:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        earned = (
            await session.execute(
                select(ListeningResult.id)
                .where(
                    ListeningResult.user_id == user.id,
                    ListeningResult.topic == s["topic"],
                    ListeningResult.kind == s["kind"],
                    ListeningResult.xp > 0,
                    ListeningResult.created_at >= today,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if earned is not None:
            xp = 0
    if s["count"] > 0:
        session.add(
            ListeningResult(
                user_id=user.id, topic=s["topic"], kind=s["kind"], level=s["level"],
                score=s["score"], count=s["count"], xp=xp,
            )
        )
        if xp > 0:
            session.add(XpLog(user_id=user.id, amount=xp, source=f"listen:{body.key}"))
        await session.commit()
    listening.finish(body.key, user.id)
    return {
        "topic_id": s["topic"],
        "kind": s["kind"],
        "score": s["score"],
        "count": s["count"],
        "total": len(s["items"]),
        "xp": xp,
        "scores": s["scores"],
        "items": s["items"],
        "new_badges": await _badges(session, user.id),
    }


@router.get("/tutor/log")
async def tutor_log(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Speaking daftari: xatolar (tuzatishlar), mock va talaffuz natijalari tarixi."""
    from services import tutor

    rows = (
        await session.execute(
            select(TutorMistake)
            .where(TutorMistake.user_id == user.id)
            .order_by(TutorMistake.id.desc())
            .limit(100)
        )
    ).scalars().all()
    mistakes = [
        {
            "id": m.id,
            "kind": m.kind,
            "topic": m.topic,
            "title": (
                (tutor.MOCK_BY_ID.get(m.topic) or tutor.TOPIC_BY_ID.get(m.topic) or {}).get("title_uz", "")
            ),
            "said_ar": m.said_ar,
            "fixed_ar": m.fixed_ar,
            "note_uz": m.note_uz,
            "date": m.created_at.strftime("%d.%m"),
        }
        for m in rows
    ]

    mock_rows = (
        await session.execute(
            select(MockResult.mock_id, MockResult.score, MockResult.created_at)
            .where(MockResult.user_id == user.id)
            .order_by(MockResult.id.asc())
        )
    ).all()
    mocks: dict[str, dict] = {}
    for mock_id, score, created in mock_rows:
        m = tutor.MOCK_BY_ID.get(mock_id) or {}
        d = mocks.setdefault(
            mock_id,
            {
                "mock_id": mock_id, "title": m.get("title_uz", mock_id), "emoji": m.get("emoji", "🎯"),
                "best": 0, "last": 0, "attempts": 0, "history": [], "date": "",
            },
        )
        d["attempts"] += 1
        d["best"] = max(d["best"], score)
        d["last"] = score
        d["date"] = created.strftime("%d.%m")
        d["history"] = (d["history"] + [score])[-6:]

    drill_rows = (
        await session.execute(
            select(DrillResult.topic, DrillResult.score, DrillResult.created_at)
            .where(DrillResult.user_id == user.id)
            .order_by(DrillResult.id.asc())
        )
    ).all()
    drills: dict[str, dict] = {}
    for topic_id, score, created in drill_rows:
        t = tutor.TOPIC_BY_ID.get(topic_id) or {}
        d = drills.setdefault(
            topic_id,
            {
                "topic_id": topic_id, "title": t.get("title_uz", topic_id), "emoji": t.get("emoji", "🎤"),
                "best": 0, "last": 0, "attempts": 0, "history": [], "date": "",
            },
        )
        d["attempts"] += 1
        d["best"] = max(d["best"], score)
        d["last"] = score
        d["date"] = created.strftime("%d.%m")
        d["history"] = (d["history"] + [score])[-6:]

    listen_rows = (
        await session.execute(
            select(ListeningResult.topic, ListeningResult.kind, ListeningResult.score, ListeningResult.created_at)
            .where(ListeningResult.user_id == user.id)
            .order_by(ListeningResult.id.asc())
        )
    ).all()
    listens: dict[str, dict] = {}
    for topic_id, kind, score, created in listen_rows:
        t = tutor.TOPIC_BY_ID.get(topic_id) or {}
        k = f"{topic_id}:{kind}"
        d = listens.setdefault(
            k,
            {
                "topic_id": topic_id, "kind": kind,
                "title": f"{t.get('title_uz', topic_id)} · {'diktant' if kind == 'dictation' else 'tanlash'}",
                "emoji": "🎧", "best": 0, "last": 0, "attempts": 0, "history": [], "date": "",
            },
        )
        d["attempts"] += 1
        d["best"] = max(d["best"], score)
        d["last"] = score
        d["date"] = created.strftime("%d.%m")
        d["history"] = (d["history"] + [score])[-6:]

    return {
        "mistakes": mistakes,
        "mocks": sorted(mocks.values(), key=lambda d: -d["best"]),
        "drills": sorted(drills.values(), key=lambda d: -d["best"]),
        "listens": sorted(listens.values(), key=lambda d: -d["best"]),
    }


# ─────────── Yozuv (xattotlik) mashqi (K19.2) — 2 kunda bir matn, surat → AI ───────────


@router.get("/tutor/writing")
async def tutor_writing(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Joriy davr matni (audio fonda), bajarilgan bo'lsa natija, urinishlar, tarix."""
    from config import settings
    from services import tts, writing

    level = await _user_level(session, user.id)
    period = writing.period_key()
    row = await writing.period_row(session, user.id, period)
    text = writing.current_text(level, row)
    audio_key = tts.schedule(text["ar"].replace("\n", ". "), level)
    return {
        "period": period,
        "ends": writing.period_ends(),
        "level": level,
        "text": {**text, "audio_url": f"/api/v2/tutor/audio/{audio_key}.mp3" if audio_key else ""},
        "done": writing.row_dict(row) if row and row.attempts > 0 else None,
        "attempts_left": max(writing.MAX_ATTEMPTS - (row.attempts if row else 0), 0),
        "max_attempts": writing.MAX_ATTEMPTS,
        "history": await writing.history(session, user.id),
        "ai": bool(settings.anthropic_api_key),
    }


@router.post("/tutor/writing/check")
async def tutor_writing_check(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Qo'lyozma surati → Haiku vision → aniqlik, xato so'zlar, maslahatlar. Davrda 3 urinish,
    XP birinchi muvaffaqiyatli tekshiruvda bir marta (eng yaxshi ball saqlanadi)."""
    from services import ai_usage, alerts, tutor, writing

    mime = (file.content_type or "").split(";")[0].strip().lower()
    if mime not in writing.IMAGE_TYPES:
        raise HTTPException(status_code=422, detail="Faqat surat (JPG/PNG) yuklang")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Surat bo'sh")
    if len(data) > writing.MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Surat juda katta (maks. 8 MB)")

    level = await _user_level(session, user.id)
    period = writing.period_key()
    row = await writing.period_row(session, user.id, period)
    text = writing.current_text(level, row)
    if row and row.attempts >= writing.MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail=f"Bu matn uchun {writing.MAX_ATTEMPTS} urinish tugadi — keyingi matn {writing.period_ends()} dan keyin",
        )
    try:
        image, img_mime = writing.prepare_image(data)
    except ValueError:
        raise HTTPException(status_code=422, detail="Surat o'qilmadi — boshqa rasm yuklang")

    try:
        reply, usage = await writing.check(level, text, image, img_mime)
    except tutor.TutorUnavailable as e:
        if e.kind in ("credit", "auth"):
            alerts.fire(getattr(request.app.state, "bot", None), e.kind)
        raise HTTPException(status_code=503, detail=e.message_uz)

    now = utcnow()
    fb = json.dumps(writing.feedback_dict(reply), ensure_ascii=False)
    if row is None:
        row = WritingResult(
            user_id=user.id, period=period, text_id=text["id"], level=level,
            score=0, neatness=0, attempts=0, xp=0, feedback="", created_at=now,
        )
        session.add(row)
    row.attempts += 1
    row.updated_at = now
    improved = reply.accuracy >= row.score
    if improved:
        row.score = reply.accuracy
        row.neatness = reply.neatness
        row.feedback = fb
    xp = 0
    if row.xp == 0 and reply.is_handwriting and reply.accuracy > 0:
        xp = writing.xp_for(reply.accuracy)
        row.xp = xp
        session.add(XpLog(user_id=user.id, amount=xp, source=f"writing:{period}"))
    ai_usage.record(session, "writing", usage, user.id)
    await session.commit()
    return {
        **writing.row_dict(row),
        "result": {"accuracy": reply.accuracy, "neatness": reply.neatness, **writing.feedback_dict(reply)},
        "improved": improved,
        "xp_awarded": xp,
        "usage": usage,
        "new_badges": await _badges(session, user.id),
    }


# ─────────── Kunlik speaking savoli (K17.7) — hamma uchun bepul ───────────


def _daily_row_dict(row) -> dict:
    return {
        "score": row.score,
        "xp": row.xp,
        "voice": bool(row.voice),
        "answer": row.answer,
        "feedback_uz": row.feedback,
        "ideal_ar": row.ideal,
        "fixed_ar": row.fixed,
    }


@router.get("/tutor/daily")
async def tutor_daily(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Bugungi savol (audio fonda), bajarilgan bo'lsa natija, streak."""
    from config import settings
    from services import daily, stt, tts

    level = await _user_level(session, user.id)
    q = daily.question_for(level)
    row = await daily.today_row(session, user.id)
    st = await daily.status(session, user.id)
    audio_key = tts.schedule(q["ar"], level)
    return {
        "day": daily._today().isoformat(),
        "level": level,
        "question": {**q, "audio_url": f"/api/v2/tutor/audio/{audio_key}.mp3" if audio_key else ""},
        "done": _daily_row_dict(row) if row else None,
        "streak": st["streak"],
        "best": st["best"],
        "total": st["total"],
        "ai": bool(settings.anthropic_api_key),
        "voice": stt.available(),
    }


class DailyAnswerBody(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    voice: bool = False


@router.post("/tutor/daily/answer")
async def tutor_daily_answer(
    body: DailyAnswerBody,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Javobni baholaydi (Haiku, qisqa prompt), XP beradi, streak'ni yangilaydi. Kuniga bitta."""
    from services import ai_usage, alerts, daily, tutor

    if await daily.today_row(session, user.id) is not None:
        raise HTTPException(status_code=409, detail="Bugungi savolga javob berilgan — ertaga yangi savol")
    level = await _user_level(session, user.id)
    q = daily.question_for(level)
    try:
        reply, usage = await daily.grade(level, q, body.text)
    except tutor.TutorUnavailable as e:
        if e.kind in ("credit", "auth"):
            alerts.fire(getattr(request.app.state, "bot", None), e.kind)
        raise HTTPException(status_code=503, detail=e.message_uz)

    day = daily._today().isoformat()
    xp = daily.xp_for(reply.score, body.voice)
    row = DailySpeaking(
        user_id=user.id, day=day, question_id=q["id"], level=level, score=reply.score,
        voice=1 if body.voice else 0, xp=xp, answer=body.text.removeprefix("🎤").strip()[:400],
        feedback=reply.feedback_uz[:400], ideal=reply.ideal_ar[:400], fixed=reply.fixed_ar[:400],
    )
    session.add(row)
    session.add(XpLog(user_id=user.id, amount=xp, source=f"daily:{day}"))
    ai_usage.record(session, "daily", usage, user.id)
    await session.commit()
    st = await daily.status(session, user.id)
    return {
        "result": _daily_row_dict(row), "streak": st["streak"], "best": st["best"], "xp": xp,
        "new_badges": await _badges(session, user.id),
    }


# ─────────── Sifat halqasi (K18.2): 👍/👎 ───────────


class RateBody(BaseModel):
    session_key: str = Field(min_length=4, max_length=36, pattern=r"^[A-Za-z0-9_-]+$")
    mode: str = Field(default="chat", pattern=r"^(chat|mock|daily|drill|listen)$")
    topic: str = Field(default="", max_length=24)
    good: bool
    comment: str = Field(default="", max_length=400)


@router.post("/tutor/rate")
async def tutor_rate(
    body: RateBody,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Sessiya bahosi (bir sessiya — bitta, qayta yuborilsa yangilanadi).
    👎 bo'lsa adminga mavzu/daraja/izoh bilan xabar — matn saqlanmaydi, bu yagona signal."""
    level = await _user_level(session, user.id)
    row = (
        await session.execute(
            select(TutorRating).where(
                TutorRating.user_id == user.id, TutorRating.session_key == body.session_key
            )
        )
    ).scalar_one_or_none()
    first = row is None
    if row is None:
        row = TutorRating(user_id=user.id, session_key=body.session_key)
        session.add(row)
    row.mode, row.topic, row.level = body.mode, body.topic[:24], level
    row.good, row.comment = (1 if body.good else 0), body.comment.strip()[:400]
    await session.commit()

    bot = getattr(request.app.state, "bot", None)
    from config import settings

    if not body.good and bot is not None and settings.admin_id and (first or row.comment):
        turns = (
            await session.execute(
                select(func.count()).select_from(TutorTurn).where(
                    TutorTurn.user_id == user.id, TutorTurn.session_key == body.session_key
                )
            )
        ).scalar_one()
        from services import feedback as feedback_svc

        uname = f"@{user.username}" if user.username else "—"
        text = (
            f"👎 <b>AI ustoz bahosi</b> · {body.mode} · {feedback_svc.esc(body.topic or '—')} · {level}\n"
            f"{feedback_svc.esc(user.name or '—')} ({feedback_svc.esc(uname)}), ID <code>{user.tg_id}</code>"
            f" · {turns} javob\n"
            + (f"\n<blockquote>{feedback_svc.esc(row.comment)}</blockquote>" if row.comment else "\n<i>izohsiz</i>")
        )
        try:
            await bot.send_message(settings.admin_id, text, parse_mode="HTML")
        except Exception:
            pass
    return {"ok": True}


class SayBody(BaseModel):
    text: str = Field(min_length=1, max_length=400)


@router.post("/tutor/say")
async def tutor_say(
    body: SayBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Ixtiyoriy arabcha matn uchun mp3 (xatolar daftari: to'g'ri jumlani eshitish).
    Matn xeshi bilan keshlanadi — bir xil jumla bir marta sintez qilinadi."""
    from services import tts

    level = await _user_level(session, user.id)
    key = tts.schedule(body.text.strip(), level)
    return {"audio_url": f"/api/v2/tutor/audio/{key}.mp3" if key else ""}


@router.delete("/tutor/mistakes/{mistake_id}")
async def tutor_mistake_delete(
    mistake_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """«O'rgandim» — daftardan o'chirish."""
    row = await session.get(TutorMistake, mistake_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Topilmadi")
    await session.delete(row)
    await session.commit()
    return {"ok": True}


class TutorFinishBody(BaseModel):
    session_key: str = Field(pattern=_SESSION_KEY_RE)


MOCK_XP_FACTOR = 0.5  # 100 ball = 50 XP; bir mock uchun kuniga bir marta


MOCK_CERT_MIN = 70  # shu balldan boshlab sertifikat rasmi (shaxsiy rekord bo'lsa)


def _avg_criteria(rows) -> dict:
    """Mock turnlari bo'yicha mezon o'rtachalari (-1 = o'lchanmagan)."""
    out = {}
    for i, k in enumerate(("vocab", "grammar", "content", "pron"), start=5):
        vals = [r[i] for r in rows if r[i] is not None and r[i] >= 0]
        out[k] = round(sum(vals) / len(vals)) if vals else -1
    return out


async def _mock_certificate(request: Request, session: AsyncSession, user: User, mock_id: str,
                            level: str, avg: int, crit: dict) -> dict | None:
    """Shaxsiy rekord (≥ MOCK_CERT_MIN) — sertifikat rasmi + botga ulashish tugmasi."""
    from services import tutor
    from services.certificate import issue_mock_certificate

    mock = tutor.MOCK_BY_ID.get(mock_id) or {}
    try:
        cert = await issue_mock_certificate(
            session, user.id, user.name, mock_id, mock.get("title_uz", mock_id), level, avg, crit
        )
    except Exception as e:  # shrift/disk muammosi natijani buzmasin
        print(f"Mock sertifikati yaratilmadi: {e!r}")
        return None
    data = {
        "cert_id": cert.cert_id,
        "png_url": f"/api/certificates/{cert.cert_id}.png",
        "verify_code": cert.cert_id.split("-")[-1],
    }
    bot = getattr(request.app.state, "bot", None)
    if bot:
        try:
            from urllib.parse import quote

            from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

            share_text = quote(
                f"Arabiy'da «{mock.get('title_uz', mock_id)}» speaking mock imtihonidan {avg}/100 oldim! 🎤"
            )
            share_url = quote("https://t.me/JamalArabiy_bot")
            kb = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="👥 Do'stlarga ulashish",
                        url=f"https://t.me/share/url?url={share_url}&text={share_text}",
                    )
                ]]
            )
            await bot.send_photo(
                user.tg_id,
                FSInputFile(cert.png_path),
                caption=f"🎤 Speaking mock «{mock.get('title_uz', mock_id)}» — {avg}/100. Shaxsiy rekord!",
                reply_markup=kb,
            )
        except Exception:
            pass
    return data


@router.post("/tutor/finish")
async def tutor_finish(
    body: TutorFinishBody,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Suhbat/mock yakuni: XP (bir marta) va qisqa hisobot.

    Mock: o'rtacha ball → MockResult, XP = ball × MOCK_XP_FACTOR (bir mock
    uchun kuniga bir marta — farmga yo'l qo'ymaslik uchun)."""
    from services import tutor

    rows = (
        await session.execute(
            select(
                TutorTurn.ok, TutorTurn.voice, TutorTurn.mode, TutorTurn.score, TutorTurn.topic,
                TutorTurn.vocab, TutorTurn.grammar, TutorTurn.content, TutorTurn.pron,
            )
            .where(TutorTurn.user_id == user.id, TutorTurn.session_key == body.session_key)
            .order_by(TutorTurn.id.asc())
        )
    ).all()
    # Ochilish turn'i (o'quvchi javobsiz) ham qatorga yoziladi — uni hisobdan
    # chiqarish uchun: javoblar = qatorlar - 1
    turns = max(len(rows) - 1, 0)
    ok = sum(1 for r in rows if r[0]) - (1 if rows else 0)
    ok = max(min(ok, turns), 0)
    voice = sum(1 for r in rows if r[1])
    is_mock = bool(rows) and rows[0][2] == "mock"

    source = f"tutor:{body.session_key}"
    already = (
        await session.execute(
            select(XpLog.id).where(XpLog.user_id == user.id, XpLog.source == source).limit(1)
        )
    ).scalar_one_or_none()
    xp = 0
    result: dict = {"turns": turns, "ok_turns": ok, "voice_turns": voice}

    if is_mock:
        scores = [r[3] for r in rows if r[3] >= 0]
        avg = round(sum(scores) / len(scores)) if scores else 0
        mock_id = rows[0][4]
        level = await _user_level(session, user.id)
        crit = _avg_criteria([r for r in rows if r[3] >= 0])
        result.update({
            "mock": True, "score": avg, "scores": scores, "mock_id": mock_id,
            "criteria": crit, "certificate": None,
        })
        if scores and already is None:
            complete = len(scores) >= tutor.MOCK_QUESTIONS
            # Shaxsiy rekordmi — sertifikat shundagina (spam bo'lmasin)
            prev_best = (
                await session.execute(
                    select(func.coalesce(func.max(MockResult.score), -1)).where(
                        MockResult.user_id == user.id, MockResult.mock_id == mock_id
                    )
                )
            ).scalar_one()
            today = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0, tzinfo=None
            )
            earned_today = (
                await session.execute(
                    select(MockResult.id)
                    .where(
                        MockResult.user_id == user.id,
                        MockResult.mock_id == mock_id,
                        MockResult.xp > 0,
                        MockResult.created_at >= today,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            # Faqat to'liq (barcha savollar) mock XP beradi
            if earned_today is None and len(scores) >= tutor.MOCK_QUESTIONS:
                xp = round(avg * MOCK_XP_FACTOR)
            session.add(
                MockResult(
                    user_id=user.id,
                    mock_id=mock_id,
                    level=level,
                    score=avg,
                    xp=xp,
                    session_key=body.session_key,
                    **crit,
                )
            )
            if xp > 0:
                session.add(XpLog(user_id=user.id, amount=xp, source=source))
            await session.commit()
            if complete and avg >= MOCK_CERT_MIN and avg > prev_best:
                result["certificate"] = await _mock_certificate(
                    request, session, user, mock_id, level, avg, crit
                )
    elif turns >= 3 and already is None:
        xp = min(30, 2 * turns + ok + 2 * voice)
        session.add(XpLog(user_id=user.id, amount=xp, source=source))
        await session.commit()

    result["xp"] = xp
    result["new_badges"] = await _badges(session, user.id)
    return result


class TutorSaveWordBody(BaseModel):
    ar: str = Field(min_length=1, max_length=128)
    uz: str = Field(default="", max_length=256)


@router.post("/tutor/save_word")
async def tutor_save_word(
    body: TutorSaveWordBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Suhbatda chiqqan yangi so'zni SRS kartotekasiga qo'shish."""
    added = await seed_from_srs_cards(
        session, user.id, [{"front": body.ar.strip(), "back": body.uz.strip(), "type": "word"}]
    )
    await session.commit()
    return {"added": added}


# ── Harf chizish mashqi (K21.6) ──


@router.get("/trace")
async def trace_info(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Harflar ro'yxati + eng yaxshi ballar; bugun XP olinganmi."""
    from services import trace

    return {
        "letters": trace.letters(),
        "best": await trace.best(session, user.id),
        "pass": trace.PASS,
        "min_letters": trace.MIN_LETTERS,
        "xp_today": await trace.xp_taken_today(session, user.id, utcnow()),
    }


class TraceFinishBody(BaseModel):
    scores: dict[str, int] = Field(default_factory=dict)


@router.post("/trace/finish")
async def trace_finish(
    body: TraceFinishBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Sessiya yakuni: natija saqlanadi, XP (≥ MIN_LETTERS harf, kuniga bir marta)."""
    from services import trace

    scores = trace.clean_scores(body.scores)
    if not scores:
        raise HTTPException(status_code=422, detail="Hech qanday harf chizilmadi")
    avg = round(sum(scores.values()) / len(scores))
    xp = trace.xp_for(avg, len(scores))
    if xp and await trace.xp_taken_today(session, user.id, utcnow()):
        xp = 0
    session.add(TraceResult(user_id=user.id, scores=json.dumps(scores, ensure_ascii=False), avg=avg, count=len(scores), xp=xp))
    if xp:
        session.add(XpLog(user_id=user.id, amount=xp, source="trace"))
    await session.commit()
    return {"avg": avg, "count": len(scores), "xp": xp, "best": await trace.best(session, user.id),
            "new_badges": await _badges(session, user.id)}
