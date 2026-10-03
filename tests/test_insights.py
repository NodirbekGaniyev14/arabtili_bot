"""K31 — Statistika sahifasi va VIP shaxsiy tahlil (services/insights.py)."""

from datetime import datetime, timedelta, timezone

import pytest

from db.models import AnswerLog, ListeningResult, Plan, Progress, TutorMistake, UserWord, XpLog
from services import insights as ins

NOW = datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.mark.parametrize(
    "said, fixed, cat",
    [
        ("الكتاب", "الكِتَابُ", "harakat"),
        ("كتاب جميل", "الكتاب الجميل", "al"),
        ("سيارة جميل", "سيارة جميلة", "jins"),
        ("انا", "أنا", "hamza"),
        ("سيف", "صيف", "harflar"),
        ("ذهبت المدرسة", "ذهبت إلى المدرسة", "predlog"),
        ("أنا أريد أذهب", "أنا أريد أن أذهب", "fel"),
        ("هو ذهب", "هي ذهبت", "fel"),
    ],
)
def test_classify_arabic_mistake_types(said, fixed, cat):
    assert ins.classify(said, fixed)[0] == cat


def test_classify_keeps_harakat_and_uses_note_fallback():
    # \w harakatni olib tashlamasligi kerak — aks holda so'z bo'linib «boshqa» bo'lardi
    assert ins.classify("ذَهَبَ", "ذَهَبَ") is None
    assert ins.classify("ذهب بيت", "رجع إلى البيت", "fe'l zamoni noto'g'ri")[0] == "fel"
    assert ins.classify("x", "kitob") is None, "arabcha bo'lmagan to'g'ri javob tasniflanmaydi"
    assert ins.classify("سيف", "صيف")[1] == "س–ص", "qaysi juft adashtirilgani ko'rsatiladi"


async def _learner(session, make_user, *, vip: bool):
    u = await make_user("Ali", vip_until=NOW + timedelta(days=10) if vip else None)
    session.add(Plan(user_id=u.id, level="A0", target_level="A1", target_date="2030-01-01", start_lesson="a0-01"))
    for i, lid in enumerate(("a0-01", "a0-02", "a0-03")):
        at = NOW - timedelta(days=3 - i)
        session.add(Progress(user_id=u.id, lesson_id=lid, correct=8, total=10, xp_earned=20, completed_at=at))
        session.add(XpLog(user_id=u.id, amount=20, source=f"lesson:{lid}", created_at=at))
    session.add(ListeningResult(user_id=u.id, topic="oila", score=50, count=10, created_at=NOW - timedelta(hours=12)))
    for said, fixed in [("الكتاب", "الكِتَابُ"), ("البيتَ", "البيتُ"), ("قلمٌ", "قلمٍ")]:
        session.add(TutorMistake(user_id=u.id, said_ar=said, fixed_ar=fixed, created_at=NOW - timedelta(days=1)))
    for given, exp in [("سيف", "صيف"), ("سيارة جميل", "سيارة جميلة")]:
        session.add(AnswerLog(user_id=u.id, ex_type="fill_blank", given=given, expected=exp,
                              created_at=NOW - timedelta(days=1)))
    session.add(UserWord(user_id=u.id, ar="بَيْت", uz="uy", due_date="2000-01-01", reps=2, interval_days=25))
    session.add(UserWord(user_id=u.id, ar="قَلَم", uz="qalam", due_date="2000-01-01", reps=0, lapses=2))
    await session.commit()
    return u


@pytest.mark.asyncio
async def test_vip_gets_all_five_insights_with_values(session, make_user):
    u = await _learner(session, make_user, vip=True)
    data = await ins.overview(session, u, "month")
    items = {i["id"]: i for i in data["insights"]["items"]}
    assert data["insights"]["unlocked"] == 5
    assert items["weak"]["value"].startswith("Tinglash · 50%"), "tinglash (50) o'qishdan (80) past"
    assert items["mistakes"]["top"][0]["id"] == "harakat" and items["mistakes"]["top"][0]["count"] == 3
    assert {t["id"] for t in items["mistakes"]["top"]} >= {"harakat"}
    assert items["plan"]["plan"][0]["action"] == "lesson"
    assert any(p["action"] == "listen" for p in items["plan"]["plan"]), "zaif ko'nikma rejaga kiradi"


@pytest.mark.asyncio
async def test_free_user_sees_only_level_and_no_locked_values(session, make_user):
    u = await _learner(session, make_user, vip=False)
    data = await ins.overview(session, u, "month")
    items = data["insights"]["items"]
    assert data["insights"]["unlocked"] == 1 and items[0]["id"] == "level" and items[0]["state"] == "open"
    for it in items[1:]:
        assert it["state"] == "vip"
        assert "value" not in it and "detail" not in it and "top" not in it and "plan" not in it, (
            "yopiq tahlil qiymati bepul foydalanuvchiga yuborilmaydi"
        )


@pytest.mark.asyncio
async def test_vip_without_data_sees_requirement_progress(session, make_user):
    u = await make_user("Yangi", vip_until=NOW + timedelta(days=3))
    session.add(Plan(user_id=u.id, level="A0", target_level="A1", target_date="", start_lesson="a0-01"))
    await session.commit()
    data = await ins.overview(session, u, "week")
    items = {i["id"]: i for i in data["insights"]["items"]}
    assert items["forecast"]["state"] == "data" and items["forecast"]["want"] == ins.MIN_LESSONS_FORECAST
    assert items["mistakes"]["state"] == "data" and items["mistakes"]["have"] == 0
    assert data["insights"]["unlocked"] == 1


@pytest.mark.asyncio
async def test_skills_vocab_streak_and_history(session, make_user):
    u = await _learner(session, make_user, vip=False)
    data = await ins.overview(session, u, "week")
    assert data["skills"]["reading"] == {"score": 80, "count": 3, "last": 80, "delta": None}
    assert data["skills"]["listening"]["score"] == 50 and data["skills"]["speaking"]["score"] is None
    v = data["vocab"]
    assert v["total"] == 2 and v["due"] == 2 and v["retention"] == 50
    assert v["stages"] == {"new": 0, "learning": 1, "mature": 1}
    assert v["hardest"][0]["ar"] == "قَلَم"
    assert data["streak"]["days"] >= 1 and len(data["streak"]["week"]) == 7
    assert data["history"][0]["skill"] == "listening", "tarix — eng yangisi birinchi"
    assert data["goal"]["target"] == "A1" and 0 < data["goal"]["percent"] < 100


@pytest.mark.asyncio
async def test_period_filters_skills_but_not_insights(session, make_user):
    u = await _learner(session, make_user, vip=True)
    session.add(ListeningResult(user_id=u.id, topic="oila", score=90, count=10, created_at=NOW - timedelta(days=60)))
    await session.commit()
    week = await ins.overview(session, u, "week")
    three = await ins.overview(session, u, "3m")
    assert week["skills"]["listening"]["count"] == 1 and three["skills"]["listening"]["count"] == 2
    assert week["insights"] == three["insights"], "tahlillar davr tanloviga bog'liq emas (90 kun)"
    assert (await ins.overview(session, u, "bogus"))["period"] == "month"


def test_forecast_on_track_and_late():
    from datetime import date

    goal = {"remaining": 20, "target": "A1"}
    today = date(2026, 10, 3)
    ok = ins.forecast(goal, 5.0, "2026-12-31", today)
    assert ok["weeks"] == 4 and ok["on_track"] is True
    late = ins.forecast(goal, 1.0, "2026-10-31", today)
    assert late["on_track"] is False and late["need_pace"] == 5.0
    stalled = ins.forecast(goal, 0.0, "", today)
    assert stalled["weeks"] is None and stalled["on_track"] is None


def test_classify_skips_noise_and_detects_wrong_word():
    assert ins.classify("ب", "ضَرُورِيّ") is None, "bitta harf — «bilmayman», tahlilga kirmaydi"
    assert ins.classify("mening ismim Nodir", "اِسْمِي نُودِير") is None, "o'zbekcha javob arabcha xato turi emas"
    assert ins.classify("كتاب", "ضَرُورِيّ")[0] == "meaning"


def test_unclassified_type_never_outranks_real_types():
    vip = dict(vip=True, pos={"level": "A1", "percent": 10, "done": 1, "total": 10, "next": None},
               skills90={s: {"score": None} for s in ins.SKILLS}, fc={"done": True}, goal={"target": "A1", "remaining": 0},
               lessons_done=5, vocab={"due": 0})
    top = [{"id": "boshqa", "title": "Gap tuzilishi", "tip": "", "count": 9},
           {"id": "harakat", "title": "Harakatlar", "tip": "", "count": 2}]
    # mistake_stats saralaydi; build_insights birinchisini qiymat qiladi
    ranked = sorted(top, key=lambda t: (t["id"] == "boshqa", -t["count"]))
    out = ins.build_insights(mistakes={"total": 11, "top": ranked}, **vip)
    assert next(i for i in out["items"] if i["id"] == "mistakes")["value"].startswith("Harakatlar")


def test_very_slow_pace_is_not_shown_as_hundreds_of_weeks():
    from datetime import date

    fc = ins.forecast({"remaining": 129, "target": "A2"}, 0.2, "2026-12-20", date(2026, 10, 3))
    out = ins.build_insights(
        vip=True, pos={"level": "A0", "percent": 10, "done": 4, "total": 41, "next": None},
        skills90={s: {"score": None} for s in ins.SKILLS}, mistakes={"total": 0, "top": []}, fc=fc,
        goal={"target": "A2", "remaining": 129}, lessons_done=4, vocab={"due": 0},
    )
    f = next(i for i in out["items"] if i["id"] == "forecast")
    assert "2 yildan ko'p" in f["value"] and "haftasiga 5 dars" in f["detail"].lower()
