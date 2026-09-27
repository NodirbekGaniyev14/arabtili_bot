"""K27 — «Xatolik bormi?» xabarida o'quvchi javobi va mashq turi.

Klient `given` yubormasa (eski versiya), server shu o'quvchining so'nggi 3 soatdagi
rad etilgan yozma javobini (#F70 jurnal) biriktiradi — admin nima yozilganini ko'radi.
"""

from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from db.models import AnswerLog, Feedback, utcnow
from services import feedback as fs


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.sent.append((chat_id, text))


@pytest.fixture
def client_for(session, monkeypatch):
    from config import settings
    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

    monkeypatch.setattr(settings, "admin_id", 999)
    bot = FakeBot()
    monkeypatch.setattr(app.state, "bot", bot, raising=False)

    async def _session():
        yield session

    def make(user):
        app.dependency_overrides[get_session] = _session
        app.dependency_overrides[get_current_user] = lambda: user
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")

    yield make, bot
    app.dependency_overrides.clear()


BODY = {
    "kind": "wrong_answer",
    "context": "a2-20",
    "label": "MIKRO-TEST · 4/7",
    "ex_type": "translate_ar_uz",
    "q": "أَنَا مَشْغُولٌ",
    "q_ar": "أَنَا مَشْغُولٌ",
    "answer": "men bandman",
}


def _log(user_id: int, given: str, hours_ago: float = 0.1, expected: str = "men bandman") -> AnswerLog:
    return AnswerLog(
        user_id=user_id, context="a2-20", ex_type="translate_ar_uz", q="أَنَا مَشْغُولٌ",
        expected=expected, given=given, created_at=utcnow() - timedelta(hours=hours_ago),
    )


async def _issue_text(session) -> str:
    return (await session.execute(select(Feedback.text).order_by(Feedback.id.desc()))).scalars().first()


async def test_issue_gets_rejected_answer_from_log(session, make_user, client_for):
    make, bot = client_for
    user = await make_user("Shirin")
    other = await make_user("Boshqa")
    session.add_all(
        [
            _log(user.id, "eski javob", hours_ago=5),  # 3 soatdan eski — olinmaydi
            _log(user.id, "мен бандман"),
            _log(other.id, "boshqa odamniki", hours_ago=0.01),  # boshqa o'quvchi — olinmaydi
        ]
    )
    await session.commit()
    async with make(user) as c:
        assert (await c.post("/api/report-issue", json=BODY)).json() == {"ok": True}
    text = await _issue_text(session)
    assert "O'quvchi javobi: мен бандман" in text
    assert "Mashq: ✍️ yozma tarjima (arabcha → o'zbekcha)" in text
    assert bot.sent and "мен бандман" in bot.sent[0][1]


async def test_issue_prefers_client_given_and_skips_unrelated_log(session, make_user, client_for):
    make, _bot = client_for
    user = await make_user("Ali")
    session.add(_log(user.id, "boshqa savol javobi", expected="kitob"))
    await session.commit()
    async with make(user) as c:
        await c.post("/api/report-issue", json=BODY)  # jurnalda bu savol yo'q
        await c.post("/api/report-issue", json={**BODY, "kind": "other", "given": "men mashg'ulman"})
    rows = (await session.execute(select(Feedback.text).order_by(Feedback.id))).scalars().all()
    assert "O'quvchi javobi" not in rows[0]
    assert "O'quvchi javobi: men mashg'ulman" in rows[1]


def test_issue_text_ex_type_labels():
    t = fs.issue_text("audio", label="Lug'at testi", ex_type="mcq", q="kitob", options=["kitob", "qalam"], answer="kitob")
    assert "Mashq: variantli" in t and "✓ kitob" in t
    assert "Mashq: yangi_tur" in fs.issue_text("other", ex_type="yangi_tur")
    assert "Mashq" not in fs.issue_text("other", q="x")
