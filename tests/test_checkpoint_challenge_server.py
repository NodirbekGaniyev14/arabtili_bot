"""K33 — mini-imtihon va haftalik chellenj ballini SERVER hisoblaydi: javobsiz savollar, soxta ball, XP bir marta."""

import json

import httpx
import pytest
from sqlalchemy import select

from db.models import AnswerLog, ExamAttempt, Plan, Progress, XpLog
from services import checkpoint as cp
from services import exam as ex

SECRET = {"answer", "explain_uz", "option_notes", "accept"}


@pytest.fixture
async def api(session, make_user):
    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

    user = await make_user("Mini")
    session.add(Plan(user_id=user.id, level="A0", target_level="A1", target_date="2027-01-01"))
    for lid in cp.level_lessons("A0")[:14]:  # 25% ochiladi, savollar shu darslardan
        session.add(Progress(user_id=user.id, lesson_id=lid))
    await session.commit()

    async def _session():
        yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: user
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    try:
        yield client, user
    finally:
        await client.aclose()
        app.dependency_overrides.clear()


async def _attempt(session, attempt_id) -> ExamAttempt:
    return (await session.execute(select(ExamAttempt).where(ExamAttempt.id == attempt_id))).scalar_one()


async def _stored_items(session, attempt_id) -> list[dict]:
    return json.loads((await _attempt(session, attempt_id)).questions_json)["items"]


async def _xp(session, user, prefix) -> list[int]:
    rows = (await session.execute(select(XpLog).where(XpLog.user_id == user.id))).scalars().all()
    return [r.amount for r in rows if r.source.startswith(prefix)]


async def _start_cp(client, percent=25):
    r = await client.post(f"/api/checkpoint/start?percent={percent}&v=2", content="{}")
    assert r.status_code == 200, r.text
    return r.json()


async def _start_ch(client):
    r = await client.post("/api/challenge/start?v=2", content="{}")
    assert r.status_code == 200, r.text
    return r.json()


# ── Mini-imtihon ──


async def test_checkpoint_start_requires_new_client(api):
    client, _ = api
    r = await client.post("/api/checkpoint/start?percent=25", content="{}")
    assert r.status_code == 426 and "yangilangan" in r.json()["detail"]


async def test_checkpoint_start_hides_answers(api, session):
    client, _ = api
    data = await _start_cp(client)
    assert len(data["items"]) == cp.N_QUESTIONS
    for it in data["items"]:
        assert not SECRET & set(it), it
        assert it["input"] in ("options", "ar", "lat", "harakat", "order")
    stored = await _stored_items(session, data["attempt_id"])
    assert all("answer" in i for i in stored), "to'liq nusxa bazada qoladi"


async def test_checkpoint_correct_answers_pass_and_pay_xp_once(api, session):
    client, user = api
    for n, expected_xp in ((1, [15]), (2, [15])):  # 2-urinishda XP yo'q
        data = await _start_cp(client)
        stored = await _stored_items(session, data["attempt_id"])
        r = await client.post(
            "/api/checkpoint/submit",
            json={"attempt_id": data["attempt_id"], "answers": [i["answer"] for i in stored]},
        )
        assert r.status_code == 200, r.text
        res = r.json()
        assert res["score"] == 100 and res["passed"] is True and res["review"] == []
        assert await _xp(session, user, "checkpoint:") == expected_xp
        assert res["xp_earned"] == (15 if n == 1 else 0)
        assert res["xp_already_claimed"] is (n == 2)


async def test_checkpoint_forged_scores_are_ignored(api, session):
    """Eski usul: correct=total=12 — ammo javoblar yo'q. Natija 0, XP yo'q."""
    client, user = api
    data = await _start_cp(client)
    body = {"attempt_id": data["attempt_id"], "answers": [], "correct": 12, "total": 12, "wrong_words": []}
    res = (await client.post("/api/checkpoint/submit", json=body)).json()
    assert (res["correct"], res["total"], res["score"]) == (0, cp.N_QUESTIONS, 0)
    assert res["passed"] is False and await _xp(session, user, "checkpoint:") == []
    assert len(res["review"]) == cp.N_QUESTIONS and all("answer" in r for r in res["review"])


async def test_checkpoint_legacy_submit_is_426_and_keeps_attempt_open(api, session):
    client, _ = api
    data = await _start_cp(client)
    r = await client.post(
        "/api/checkpoint/submit",
        json={"attempt_id": data["attempt_id"], "correct": 12, "total": 12, "wrong_words": []},
    )
    assert r.status_code == 426
    assert (await _attempt(session, data["attempt_id"])).finished_at is None


async def test_checkpoint_review_lists_wrong_answers_and_logs_typed(api, session, monkeypatch):
    client, user = api
    # Tasodifiy tanlovga bog'lanmaymiz: bitta variantli, bitta yozma savol
    fixed = {
        "level": "A0", "percent": 25, "lessons_covered": 10, "pass_score": 80,
        "items": [
            {"type": "mcq", "q_uz": "q1", "options": ["a", "b"], "answer": "a", "explain_uz": "izoh"},
            {"type": "translate_ar_uz", "q_uz": "", "q_ar": "قَلَم", "answer": "qalam"},
        ],
    }
    monkeypatch.setattr(cp, "build_mini", lambda *a, **k: json.loads(json.dumps(fixed)))
    data = await _start_cp(client)
    res = (await client.post(
        "/api/checkpoint/submit", json={"attempt_id": data["attempt_id"], "answers": ["a", "zzz qqq"]}
    )).json()
    assert (res["correct"], res["total"], res["score"]) == (1, 2, 50)
    assert [r["index"] for r in res["review"]] == [1]
    assert res["review"][0]["answer"] == "qalam" and res["review"][0]["given"] == "zzz qqq"
    logged = (await session.execute(select(AnswerLog).where(AnswerLog.user_id == user.id))).scalars().all()
    assert [(r.context, r.ex_type, r.given) for r in logged] == [("cp25", "translate_ar_uz", "zzz qqq")]


async def test_checkpoint_cannot_be_submitted_twice(api):
    client, _ = api
    data = await _start_cp(client)
    body = {"attempt_id": data["attempt_id"], "answers": []}
    assert (await client.post("/api/checkpoint/submit", json=body)).status_code == 200
    assert (await client.post("/api/checkpoint/submit", json=body)).status_code == 409


async def test_checkpoint_other_users_attempt_is_404(api, session, make_user):
    client, _ = api
    data = await _start_cp(client)
    from main import app
    from services.telegram_auth import get_current_user

    other = await make_user("Boshqa")
    app.dependency_overrides[get_current_user] = lambda: other
    r = await client.post("/api/checkpoint/submit", json={"attempt_id": data["attempt_id"], "answers": []})
    assert r.status_code == 404


async def test_checkpoint_oversized_answer_rejected(api):
    client, _ = api
    data = await _start_cp(client)
    r = await client.post("/api/checkpoint/submit", json={"attempt_id": data["attempt_id"], "answers": ["x" * 500]})
    assert r.status_code == 422


# ── Haftalik chellenj ──


async def test_challenge_start_requires_new_client(api):
    client, _ = api
    assert (await client.post("/api/challenge/start", content="{}")).status_code == 426


async def test_challenge_start_hides_answers(api, session):
    client, _ = api
    data = await _start_ch(client)
    assert data["items"] and data["xp_reward"]
    assert all(not SECRET & set(it) for it in data["items"])


async def test_challenge_correct_answers_pay_xp_once_per_week(api, session):
    client, user = api
    for n in (1, 2):
        data = await _start_ch(client)
        stored = await _stored_items(session, data["attempt_id"])
        res = (await client.post(
            "/api/challenge/submit",
            json={"attempt_id": data["attempt_id"], "answers": [i["answer"] for i in stored]},
        )).json()
        assert res["score"] == 100 and res["passed"] is True and res["review"] == []
        assert res["xp_earned"] == (40 if n == 1 else 0)
        assert res["xp_already_claimed"] is (n == 2)
    assert await _xp(session, user, "challenge:") == [40]


async def test_challenge_forged_scores_are_ignored(api, session):
    client, user = api
    data = await _start_ch(client)
    res = (await client.post(
        "/api/challenge/submit",
        json={"attempt_id": data["attempt_id"], "answers": [], "correct": 10, "total": 10},
    )).json()
    assert res["correct"] == 0 and res["passed"] is False and res["xp_earned"] == 0
    assert await _xp(session, user, "challenge:") == []


async def test_challenge_legacy_submit_is_426_and_keeps_attempt_open(api, session):
    client, _ = api
    data = await _start_ch(client)
    r = await client.post(
        "/api/challenge/submit",
        json={"attempt_id": data["attempt_id"], "correct": 10, "total": 10, "wrong_words": []},
    )
    assert r.status_code == 426
    assert (await _attempt(session, data["attempt_id"])).finished_at is None
    _ = ex  # imtihon moduli bilan bir xil chegara (STALE_CLIENT)
