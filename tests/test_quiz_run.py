"""K33.2 — dars testi / nazorat / zaif so'zlar: javoblar serverda QULFLANADI, ball qulflangan javoblardan."""

import json

import httpx
import pytest
from sqlalchemy import select

from db.models import AnswerLog, Progress, QuizRun
from play_helpers import answer_run, play_lesson, run_items
from services import blind_quiz, quiz_run
from services.curriculum import load_curriculum, written_lesson_ids
from services.reading import passage_for

SECRET = {"answer", "explain_uz", "option_notes", "accept"}


@pytest.fixture
async def api(session, make_user):
    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

    state = {"user": await make_user("Talaba")}

    async def _session():
        yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    try:
        yield client, state, session
    finally:
        await client.aclose()
        app.dependency_overrides.clear()


async def _open(c, lesson_id="a0-01"):
    r = await c.get(f"/api/v2/lessons/{lesson_id}?v=2")
    assert r.status_code == 200, r.text
    return r.json()


# ── Mijozga javobsiz ──


async def test_lesson_requires_new_client(api):
    c, *_ = api
    r = await c.get("/api/v2/lessons/a0-01")
    assert r.status_code == 426 and "yangilangan" in r.json()["detail"]


async def test_lesson_questions_have_no_answers(api):
    c, _, session = api
    lesson = await _open(c)
    assert lesson["micro_test"] and lesson["run"]["id"]
    for q in lesson["micro_test"]:
        assert not SECRET & set(q), q
        assert q["input"] in blind_quiz.INPUT_KINDS
    stored = await run_items(session, lesson["run"]["id"])
    assert len(stored) == len(lesson["micro_test"]) and all("type" in i for i in stored)
    assert lesson["run"]["passage_offset"] == len(lesson["micro_test"])


async def test_passage_questions_are_in_the_same_run(api):
    c, _, session = api
    lid = next(
        l for l in sorted(written_lesson_ids())
        if load_curriculum()[l]["type"] == "lesson" and (passage_for(l) or {}).get("questions")
    )
    lesson = await _open(c, lid)
    n = lesson["run"]["passage_offset"]
    assert lesson["passage"]["questions"], lid
    assert not any(SECRET & set(q) for q in lesson["passage"]["questions"])
    assert len(await run_items(session, lesson["run"]["id"])) == n + len(lesson["passage"]["questions"])
    # o'qish savollariga ham javob qulflanadi; dars natijasi ikkalasidan
    await answer_run(c, session, lesson["run"]["id"])
    d = (await c.post(f"/api/v2/lessons/{lid}/complete", json={"run_id": lesson["run"]["id"]})).json()
    assert d["total"] == n + len(lesson["passage"]["questions"]) and d["correct"] == d["total"]


# ── Javobni qulflash ──


async def test_answer_reveals_the_correct_answer_after_locking(api):
    c, _, session = api
    lesson = await _open(c)
    run_id = lesson["run"]["id"]
    item = (await run_items(session, run_id))[0]
    r = await c.post(f"/api/v2/run/{run_id}/answer", json={"index": 0, "given": "zzz qqq"})
    assert r.status_code == 200
    res = r.json()
    assert res["ok"] is False and res["answer"] == item["answer"] and res["given"] == "zzz qqq"
    assert res["explain_uz"] == (item.get("explain_uz") or "")


async def test_locked_answer_cannot_be_changed(api):
    """Xato javobdan keyin to'g'risini yuborsa ham — avvalgisi qoladi (aks holda 'sinab ko'rib' bilib olinardi)."""
    c, _, session = api
    run_id = (await _open(c))["run"]["id"]
    item = (await run_items(session, run_id))[0]
    first = (await c.post(f"/api/v2/run/{run_id}/answer", json={"index": 0, "given": "zzz qqq"})).json()
    again = (await c.post(f"/api/v2/run/{run_id}/answer", json={"index": 0, "given": item["answer"]})).json()
    assert first["ok"] is False and again["ok"] is False and again["given"] == "zzz qqq"
    d = (await c.post("/api/v2/lessons/a0-01/complete", json={"run_id": run_id})).json()
    assert d["correct"] == 0


async def test_unanswered_questions_count_as_wrong(api):
    c, _, session = api
    run_id = (await _open(c))["run"]["id"]
    n = len(await run_items(session, run_id))
    await answer_run(c, session, run_id, n_correct=3)  # qolganlariga noto'g'ri
    d = (await c.post("/api/v2/lessons/a0-01/complete", json={"run_id": run_id})).json()
    assert (d["correct"], d["total"]) == (3, n)
    run_id = (await _open(c))["run"]["id"]
    r = await c.post(f"/api/v2/run/{run_id}/answer", json={"index": 0, "given": (await run_items(session, run_id))[0]["answer"]})
    assert r.json()["ok"]
    d = (await c.post("/api/v2/lessons/a0-01/complete", json={"run_id": run_id})).json()
    assert (d["correct"], d["total"]) == (1, n), "javob berilmaganlar — xato"


async def test_answer_validation_and_ownership(api, make_user):
    c, state, session = api
    run_id = (await _open(c))["run"]["id"]
    n = len(await run_items(session, run_id))
    assert (await c.post(f"/api/v2/run/{run_id}/answer", json={"index": n, "given": "a"})).status_code == 422
    assert (await c.post(f"/api/v2/run/{run_id}/answer", json={"index": -1, "given": "a"})).status_code == 422
    assert (await c.post(f"/api/v2/run/{run_id}/answer", json={"index": 0, "given": "x" * 301})).status_code == 422
    assert (await c.post("/api/v2/run/99999/answer", json={"index": 0, "given": "a"})).status_code == 404
    other = await make_user("Boshqa")
    state["user"] = other
    assert (await c.post(f"/api/v2/run/{run_id}/answer", json={"index": 0, "given": "a"})).status_code == 404
    assert (await c.post("/api/v2/lessons/a0-01/complete", json={"run_id": run_id})).status_code == 409


async def test_finished_run_accepts_no_more_answers(api):
    c, _, session = api
    run_id = (await _open(c))["run"]["id"]
    await answer_run(c, session, run_id)
    assert (await c.post("/api/v2/lessons/a0-01/complete", json={"run_id": run_id})).status_code == 200
    assert (await c.post(f"/api/v2/run/{run_id}/answer", json={"index": 0, "given": "a"})).status_code == 404
    assert (await c.post("/api/v2/lessons/a0-01/complete", json={"run_id": run_id})).status_code == 409


async def test_run_of_another_lesson_cannot_complete_this_one(api):
    c, _, session = api
    run_id = (await _open(c, "a0-01"))["run"]["id"]
    await answer_run(c, session, run_id)
    assert (await c.post("/api/v2/lessons/a0-02/complete", json={"run_id": run_id})).status_code == 409


async def test_progress_is_recorded_from_server_score(api):
    c, state, session = api
    d = await play_lesson(c, session, "a0-01", n_correct=1)
    assert d["passed"] is False
    row = (await session.execute(select(Progress).where(Progress.user_id == state["user"].id))).scalars().one()
    assert (row.correct, row.total, row.passed) == (1, d["total"], 0)


# ── Yangi urinish / chegaralar ──


async def test_untouched_run_is_reused_on_refresh(api):
    c, *_ = api
    a = (await _open(c))["run"]["id"]
    b = (await _open(c))["run"]["id"]
    assert a == b


async def test_abandoned_attempt_advances_the_question_window(api):
    """Javob berilib tugatilmagan urinish keyingi urinishni 'oldinga suradi' — ochilgan javoblar ish bermasin."""
    c, _, session = api
    first = await _open(c)
    await c.post(f"/api/v2/run/{first['run']['id']}/answer", json={"index": 0, "given": "zzz"})
    second = await _open(c)
    assert second["run"]["id"] != first["run"]["id"]
    assert second["test_attempt"] == first["test_attempt"] + 1


async def test_hourly_run_limit(api, monkeypatch):
    c, *_ = api
    monkeypatch.setattr(quiz_run, "MAX_RUNS_PER_HOUR", 3)
    ids = [l for l in sorted(written_lesson_ids()) if load_curriculum()[l]["type"] == "lesson"][:4]
    for lid in ids[:3]:
        assert (await c.get(f"/api/v2/lessons/{lid}?v=2")).status_code == 200
    r = await c.get(f"/api/v2/lessons/{ids[3]}?v=2")
    assert r.status_code == 429 and "Juda ko'p urinish" in r.json()["detail"]


async def test_legacy_complete_is_426_and_keeps_run_open(api):
    c, _, session = api
    run_id = (await _open(c))["run"]["id"]
    r = await c.post("/api/v2/lessons/a0-01/complete", json={"correct": 7, "total": 7})
    assert r.status_code == 426
    run = (await session.execute(select(QuizRun).where(QuizRun.id == run_id))).scalar_one()
    assert run.finished_at is None


# ── Servis: turlar, izoh, jurnal ──


async def test_service_logs_rejected_typed_answers_and_notes(session, make_user):
    user = await make_user()
    items = [
        {"type": "translate_ar_uz", "q_uz": "", "q_ar": "قَلَم", "answer": "qalam"},
        {"type": "mcq", "q_uz": "q", "options": ["a", "b"], "answer": "a", "option_notes": {"b": "b — boshqa so'z"}},
        {"type": "mcq", "q_uz": "q2", "options": ["a", "b"], "answer": "b"},
        {"type": "shadowing", "q_uz": "takrorlang", "q_ar": "سَلام", "answer": ""},
    ]
    run = await quiz_run.create_run(session, user.id, "lesson", "a0-12", items)
    r0 = await quiz_run.lock_answer(session, run, 0, "daftar")
    r1 = await quiz_run.lock_answer(session, run, 1, "b")
    r2 = await quiz_run.lock_answer(session, run, 2, "b")
    r3 = await quiz_run.lock_answer(session, run, 3, "done")
    assert [r["ok"] for r in (r0, r1, r2, r3)] == [False, False, True, True]
    assert r1["note"] == "b — boshqa so'z" and r2["note"] == ""
    logged = (await session.execute(select(AnswerLog))).scalars().all()
    assert [(l.context, l.ex_type, l.given, l.expected) for l in logged] == [("a0-12", "translate_ar_uz", "daftar", "qalam")]
    res = quiz_run.summarize(run)
    assert (res["correct"], res["total"]) == (2, 4)
    assert res["wrong_words"] == ["قَلَم"], "SRS'ga faqat javob berilgan xato so'z"


async def test_service_unanswered_not_sent_to_srs(session, make_user):
    user = await make_user()
    items = [{"type": "translate_ar_uz", "q_ar": "قَلَم", "answer": "qalam"}, {"type": "translate_ar_uz", "q_ar": "بَيْت", "answer": "uy"}]
    run = await quiz_run.create_run(session, user.id, "weak", "", items)
    await quiz_run.lock_answer(session, run, 0, "zzz")
    res = quiz_run.summarize(run)
    assert res == {"correct": 0, "total": 2, "wrong_words": ["قَلَم"]}


def test_items_roundtrip_is_json():
    items = [{"type": "mcq", "options": ["a", "b"], "answer": "a"}]
    assert json.loads(json.dumps({"items": items, "extra": {}}))["items"] == items
