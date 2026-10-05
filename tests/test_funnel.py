"""K32 — /funnel voronkasi: egasi yuborgan A0 hisobotidagi xatolar va dars ichi kuzatuvi (2026-10-05)."""

import re
from datetime import timedelta

import httpx
import pytest

from db.models import ExamAttempt, LessonVisit, Plan, Progress, User, utcnow
from services import funnel


async def _learner(session, name, start="a0-01", created=None):
    u = User(tg_id=abs(hash(name)) % 10**9, name=name, is_demo=0)
    if created:
        u.created_at = created
    session.add(u)
    await session.flush()
    session.add(Plan(user_id=u.id, level="A0", target_level="A2", target_date="2027-01-01", start_lesson=start))
    await session.flush()
    return u


def _passed(user, *ids, ok=1):
    return [Progress(user_id=user.id, lesson_id=lid, correct=5, total=6, passed=ok) for lid in ids]


def _lesson_line(text, lid):
    return next(line for line in text.splitlines() if line.startswith(f"<code>{lid}</code>"))


def _count(line):
    return int(re.search(r"[█░]+\s+(\d+)", line).group(1))


@pytest.mark.asyncio
async def test_level_report_counts_only_passed_lessons_level_exams_and_all_lessons(session):
    a = await _learner(session, "Ali")
    b = await _learner(session, "Vali")
    c = await _learner(session, "Gani")
    await _learner(session, "Hech")  # ro'yxatdan o'tgan, dars o'tmagan
    session.add_all(_passed(a, "a0-01", "a0-02", "a0-03"))
    # Vali: a0-03 ni a0-02 siz o'tgan (eski qulfsiz davr) — ketma-ketlik baribir buzilmaydi
    session.add_all(_passed(b, "a0-01", "a0-03"))
    # Gani: a0-01 testida YIQILGAN — o'tgan sanalmaydi
    session.add_all(_passed(c, "a0-01", ok=0))
    # Mini-imtihon imtihon emas (ilgari «topshirgan 184 > tugatgan 97»)
    session.add(ExamAttempt(user_id=a.id, level="A0", kind="mini", checkpoint=25, finished_at=utcnow(), passed=1))
    session.add(ExamAttempt(user_id=b.id, level="A0", kind="level", finished_at=utcnow(), passed=0))
    await session.commit()

    text = await funnel.level_report(session, "A0")
    assert "A0 dan boshlagan: <b>4</b>" in text
    assert "Kamida 1 dars o'tgan: <b>2</b>" in text, "yiqilgan urinish o'tgan emas"
    assert "topshirgan <b>1</b> · o'tgan <b>0</b>" in text, "faqat kind=level"
    assert [_count(_lesson_line(text, lid)) for lid in ("a0-01", "a0-02", "a0-03", "a0-04")] == [2, 2, 2, 0]
    # hamma 41 dars ko'rinadi (ilgari 26-darsda kesilardi)
    assert "<code>a0-41</code>" in text and len(text) < 4096
    counts = [_count(line) for line in text.splitlines() if line.startswith("<code>a0-")]
    assert len(counts) == 41 and counts == sorted(counts, reverse=True), "yetib borish faqat kamayadi"


@pytest.mark.asyncio
async def test_level_report_days_window_and_drop_marks(session):
    old = utcnow() - timedelta(days=40)
    for i in range(12):
        u = await _learner(session, f"Yangi{i}")
        session.add_all(_passed(u, "a0-01", *(["a0-02"] if i < 6 else [])))
    o = await _learner(session, "Eski", created=old)
    session.add_all(_passed(o, "a0-01", "a0-02"))
    await session.commit()

    week = await funnel.level_report(session, "A0", days=14)
    assert "oxirgi 14 kunda kelganlar" in week and "A0 dan boshlagan: <b>12</b>" in week
    line = _lesson_line(week, "a0-02")
    assert _count(line) == 6 and "−50%🔻" in line
    assert "Eng katta tushish: a0-02 (−50%)" in week
    assert "A0 dan boshlagan: <b>13</b>" in await funnel.level_report(session, "A0")


@pytest.mark.asyncio
async def test_unknown_target_and_args():
    assert funnel.parse_args([]) == ("A0", None)
    assert funnel.parse_args(["A1", "14"]) == ("A1", 14)
    assert funnel.parse_args(["a0-01", "99999"]) == ("a0-01", funnel.MAX_DAYS)
    assert funnel.parse_args(["0"]) == ("A0", 1)


@pytest.mark.asyncio
async def test_unknown_level_or_lesson_shows_usage(session):
    assert "topilmadi" in await funnel.report(session, "C9") and "/funnel a0-01" in await funnel.report(session, "C9")
    assert "topilmadi" in await funnel.report(session, "a0-99")


def test_lesson_phases_match_player_order():
    """LessonPlayerV2 bilan bir xil: kirish, qoida, 5 harf kartasi, 4 ko'nikma, test, natija."""
    assert funnel.lesson_phases("a0-01") == [
        "hook", "grammar", "vocab", "vocab", "vocab", "vocab", "vocab",
        "reading", "listening", "speaking", "writing", "test", "result",
    ]
    assert set(funnel.lesson_phases("a2-15")) <= set(funnel.PHASE_NAMES)


@pytest.mark.asyncio
async def test_record_open_and_phase_keep_the_furthest(session):
    u = await _learner(session, "Ali")
    await funnel.record_open(session, u.id, "a0-01")
    await funnel.record_phase(session, u.id, "a0-01", 9, "speaking")
    await funnel.record_phase(session, u.id, "a0-01", 3, "vocab")  # qayta urinish — kamaymaydi
    await funnel.record_open(session, u.id, "a0-01")
    v = (await session.execute(LessonVisit.__table__.select())).one()
    assert (v.opens, v.max_idx, v.max_phase) == (2, 9, "speaking")
    # GET'siz ham faza yoziladi (ochilish yozilmay qolgan bo'lsa)
    await funnel.record_phase(session, u.id, "a0-02", 2, "vocab")
    assert len((await session.execute(LessonVisit.__table__.select())).all()) == 2


@pytest.mark.asyncio
async def test_lesson_report_shows_where_learners_stop(session):
    assert "Hali ma'lumot yo'q" in await funnel.lesson_report(session, "a0-01")
    # 10 kishi ochdi: 3 — kirishda, 4 — gapirishda (9), 1 — testda (11), 2 — natijagacha (12), 1 o'tdi
    ends = [0, 0, 0, 9, 9, 9, 9, 11, 12, 12]
    users = []
    for i, idx in enumerate(ends):
        u = await _learner(session, f"U{i}")
        users.append(u)
        await funnel.record_open(session, u.id, "a0-01")
        if idx:
            await funnel.record_phase(session, u.id, "a0-01", idx, funnel.lesson_phases("a0-01")[idx])
    session.add_all(_passed(users[-1], "a0-01") + _passed(users[-2], "a0-01", ok=0))
    await session.commit()

    text = await funnel.lesson_report(session, "a0-01")
    assert "Ochgan: <b>10</b>" in text and "o'tgan (≥60%): <b>1</b> (10%)" in text
    table = text.split("<pre>")[1].split("</pre>")[0]
    rows = {line.split()[0]: line for line in table.splitlines()}
    assert "to'xtagan 3" in rows["kirish"] and "to'xtagan 4" in rows["gapirish"] and "to'xtagan 1" in rows["mikro-test"]
    assert _count(rows["natija"]) == 2 and "to'xtagan" not in rows["natija"]
    assert "Ko'p to'xtagan joy: gapirish — 4 (40%), kirish — 3 (30%)" in text


@pytest.fixture
def client(session):
    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

    async def _session():
        yield session

    state = {"user": None}
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    try:
        yield c, state
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_lesson_api_records_open_and_phase(client, session):
    c, state = client
    state["user"] = await _learner(session, "Api")
    await session.commit()
    assert (await c.get("/api/v2/lessons/a0-01")).status_code == 200
    assert (await c.post("/api/v2/lessons/a0-01/phase", json={"idx": 4, "phase": "vocab"})).json() == {"ok": True}
    assert (await c.post("/api/v2/lessons/a0-01/phase", json={"idx": 4, "phase": "<script>"})).status_code == 400
    assert (await c.post("/api/v2/lessons/zz-99/phase", json={"idx": 1, "phase": "hook"})).status_code == 404
    assert (await c.post("/api/v2/lessons/a0-01/phase", json={"idx": 999, "phase": "hook"})).status_code == 422
    v = (await session.execute(LessonVisit.__table__.select())).one()
    assert (v.opens, v.max_idx, v.max_phase) == (1, 4, "vocab")
