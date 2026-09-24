"""K24 — Lug'at 2.0: mavzular, fleshkarta filtri, sessiya (10 so'z + test), baholash, SRS va XP."""

from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from db.models import UserWord, XpLog
from services import vocab
from services import vocab_session as vs
from services.stats import _today

# ── ma'lumot ──


def test_split_uz():
    assert vs.split_uz("kitob (o'zbekcha 'kitob' shundan)") == ("kitob", "o'zbekcha 'kitob' shundan")
    assert vs.split_uz("ketdi, bordi · u/erkak") == ("ketdi, bordi", "")
    assert vs.split_uz("tozaladi (II bob · u/erkak)") == ("tozaladi (II bob)", "")
    assert vs.split_uz("") == ("", "")


def test_card_filter_and_key():
    ok = lambda **kw: vocab.card_ok({"ar": "كَتَبَ", "uz": "yozdi", "pos": "fe'l", **kw})  # noqa: E731
    assert ok()
    assert not ok(uz="men yozdim")
    assert not ok(uz="sen yozasan / u (ayol) yozadi")
    assert not ok(uz="boraman (kelasi zamon)")
    assert not ok(uz="u ikki erkak yozdi (ikkilik)")
    assert not vocab.card_ok({"ar": "كِتَابِي", "uz": "mening kitobim", "pos": "ot"})
    assert not vocab.card_ok({"ar": "ب", "uz": "bo — kosacha", "pos": "harf"})
    assert not vocab.card_ok({"ar": "بُيُوت", "uz": "uylar (بَيْت ko'pligi)", "pos": "ot"})
    assert not vocab.card_ok({"ar": "يَدَانِ", "uz": "ikki qo'l", "pos": "ot"})
    assert vocab.card_ok({"ar": "اثْنَانِ", "uz": "ikki (2)", "pos": "son"}), "son — ikkilik ot emas"
    assert vocab.card_ok({"ar": "هِيَ", "uz": "u (ayol)", "pos": "olmosh"}), "olmosh — ayol shakli so'zning o'zi"
    assert vocab.card_key("الْبَيْت") == vocab.card_key("بَيْت") == "بيت"
    assert vocab.card_key("أَلَم") == "الم", "hamzali alif — artikl emas"
    assert vocab.card_key("الْآنَ") == "الان", "qisqa so'z — artikl olib tashlanmaydi"


@pytest.mark.parametrize("level", vocab.LEVELS)
def test_every_card_has_topic(level):
    """Darsga yangi so'z qo'shilsa — content/vocab/lesson_themes.json ga mavzu yozilishi kerak."""
    pool = vocab.card_pool(level)
    assert len(pool) >= 100
    missing = [w["ar"] for w in pool if not w["topic"]]
    assert not missing, f"{level}: mavzusiz so'zlar (lesson_themes.json): {missing[:10]}"
    assert len({w["key"] for w in pool}) == len(pool), "takror so'z"


def test_topics_and_levels():
    data = vs.levels(set())
    assert [x["level"] for x in data["levels"]] == list(vocab.LEVELS)
    assert data["total"] > 5000 and data["learned"] == 0
    a1 = vs.topics("A1", set())
    assert a1["title_uz"] == "Elementar" and len(a1["topics"]) == len(vocab.TOPICS)
    assert all(t["total"] >= vocab.MIN_TOPIC_WORDS for t in a1["topics"])
    assert sum(t["total"] for t in a1["topics"]) == a1["total"]
    # A0 da kichik mavzular ko'rinmaydi, lekin so'zlari «Aralash»da bor
    a0 = vs.topics("A0", set())
    assert len(a0["topics"]) < len(vocab.TOPICS)
    assert len(vocab.topic_pool("A0", vocab.ALL_TOPIC)) == a0["total"]


def test_build_new_session():
    d = vs.build("A1", "ovqat", {}, seed=3)
    assert d["mode"] == "new" and len(d["words"]) == vs.SESSION_WORDS and d["batch"] == 5
    assert d["words"][0]["ar"] == "خُبْز", "A1 — dars so'zlari oldin (eng oddiy)"
    assert len(d["exam"]) == len(d["words"])
    assert {q["key"] for q in d["exam"]} == {w["key"] for w in d["words"]}
    kinds = [q["type"] for q in d["exam"]]
    assert {"ar_uz", "uz_ar"} <= set(kinds)
    for q in d["exam"]:
        assert len(q["options"]) == vs.OPTIONS and len(set(q["options"])) == vs.OPTIONS
        assert q["answer"] in q["options"]
        if q["type"] == "audio_uz":
            assert q["audio"]
    # Bilgan so'zlar chiqmaydi, keyingi 10 ta keladi
    known = {w["key"]: {} for w in d["words"]}
    d2 = vs.build("A1", "ovqat", known, seed=3)
    assert not {w["key"] for w in d2["words"]} & set(known)
    assert d2["learned"] == 10 and d2["remaining"] == d["remaining"] - len(d2["words"])


def test_build_review_when_topic_done():
    pool = vocab.topic_pool("A0", "ovqat")
    known = {w["key"]: {"lapses": 0, "ease": 2.5, "due": "2026-01-01"} for w in pool}
    weak = pool[3]["key"]
    known[weak] = {"lapses": 4, "ease": 1.3, "due": "2026-01-01"}
    d = vs.build("A0", "ovqat", known, seed=1)
    assert d["mode"] == "review" and d["remaining"] == 0
    assert weak in {w["key"] for w in d["words"]}, "eng zaif so'z takrorga tushadi"


def test_grade():
    d = vs.build("A1", "fellar", {}, seed=5)
    answers = [{"key": q["key"], "type": q["type"], "chosen": q["answer"]} for q in d["exam"]]
    answers[0]["chosen"] = next(o for o in d["exam"][0]["options"] if o != d["exam"][0]["answer"])
    answers.append(dict(answers[1]))  # takror — hisoblanmaydi
    answers.append({"key": "yoq", "type": "ar_uz", "chosen": "x"})
    answers.append({"key": answers[2]["key"], "type": "hack", "chosen": "x"})
    g = vs.grade("A1", answers)
    assert len(g) == 10 and sum(x["correct"] for x in g) == 9 and not g[0]["correct"]
    assert vs.xp_for(9, 10, "new") == 9 + vs.XP_BONUS
    assert vs.xp_for(7, 10, "new") == 7
    assert vs.xp_for(10, 10, "review") == 5 + vs.REVIEW_BONUS


# ── API ──


@pytest.fixture
def client(session, monkeypatch):
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
async def test_api_flow(client, session, make_user):
    c, state = client
    u = await make_user()
    state["user"] = u
    # Darsdan kelgan karta «ال» bilan — lug'atdagi «خُبْز» emas, lekin boshqa so'z bilan tekshiramiz:
    session.add(UserWord(user_id=u.id, ar="الْخُبْز", uz="non", due_date=_today().isoformat()))
    await session.flush()

    lv = (await c.get("/api/vocab/levels")).json()
    assert lv["learned"] >= 1 and lv["levels"][1]["level"] == "A1"
    tp = (await c.get("/api/vocab/topics", params={"level": "A1"})).json()
    ovqat = next(t for t in tp["topics"] if t["slug"] == "ovqat")
    assert ovqat["learned"] == 1, "الْخُبْز = خُبْز (artiklsiz kalit)"
    assert (await c.get("/api/vocab/topics", params={"level": "Z9"})).status_code == 422
    assert (await c.get("/api/vocab/session", params={"level": "A1", "topic": "yoq"})).status_code == 422

    s = (await c.get("/api/vocab/session", params={"level": "A1", "topic": "ovqat"})).json()
    assert s["mode"] == "new" and "خُبْز" not in [w["ar"] for w in s["words"]], "bilgan so'z qayta chiqmaydi"
    answers = [{"key": q["key"], "type": q["type"], "chosen": q["answer"]} for q in s["exam"]]
    wrong_q = s["exam"][0]
    answers[0]["chosen"] = next(o for o in wrong_q["options"] if o != wrong_q["answer"])
    unknown_key = s["exam"][1]["key"]
    r = await c.post(
        "/api/vocab/session/finish",
        json={"level": "A1", "topic": "ovqat", "mode": "new", "answers": answers, "unknown": [unknown_key]},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["correct"] == 9 and d["total"] == 10 and d["percent"] == 90 and d["passed"]
    assert d["xp"] == 9 + vs.XP_BONUS and d["added"] == 10
    assert len(d["wrong"]) == 1 and d["wrong"][0]["key"] == wrong_q["key"] and d["wrong"][0]["chosen"] == answers[0]["chosen"]
    assert d["topic_learned"] == 11 and d["remaining"] == d["topic_total"] - 11

    cards = {w.ar: w for w in (await session.execute(select(UserWord).where(UserWord.user_id == u.id))).scalars()}
    by_key = {vocab.card_key(a): w for a, w in cards.items()}
    today = _today()
    assert by_key[wrong_q["key"]].due_date == today.isoformat() and by_key[wrong_q["key"]].lapses == 1
    assert by_key[unknown_key].due_date == (today + timedelta(days=1)).isoformat()
    assert by_key[unknown_key].ease < 2.5, "fleshkartada «bilmadim» — qiyin"
    ok_key = s["exam"][2]["key"]
    assert by_key[ok_key].due_date == (today + timedelta(days=1)).isoformat() and by_key[ok_key].ease == 2.5
    xp = (await session.execute(select(XpLog).where(XpLog.user_id == u.id))).scalar_one()
    assert xp.amount == 14 and xp.source == "vocab:A1:ovqat"

    # Keyingi sessiya — yangi 10 so'z
    s2 = (await c.get("/api/vocab/session", params={"level": "A1", "topic": "ovqat"})).json()
    assert not {w["key"] for w in s2["words"]} & {w["key"] for w in s["words"]}


@pytest.mark.asyncio
async def test_api_daily_xp_cap_and_bad_answers(client, session, make_user):
    c, state = client
    state["user"] = await make_user()
    session.add(XpLog(user_id=state["user"].id, amount=vs.DAILY_XP_CAP - 4, source="vocab:A1:all"))
    await session.flush()
    s = (await c.get("/api/vocab/session", params={"level": "A1", "topic": "all"})).json()
    answers = [{"key": q["key"], "type": q["type"], "chosen": q["answer"]} for q in s["exam"]]
    d = (await c.post("/api/vocab/session/finish", json={"level": "A1", "topic": "all", "answers": answers})).json()
    assert d["percent"] == 100 and d["xp"] == 4 and d["xp_capped"] is True
    r = await c.post("/api/vocab/session/finish", json={"level": "A1", "topic": "all", "answers": [{"key": "x", "type": "ar_uz"}]})
    assert r.status_code == 422
