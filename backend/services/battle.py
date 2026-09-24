"""Oktagon (K25) — 1v1 lug'at jangi.

Qoidalar: daraja bo'yicha navbat (A0…B2); ikkala o'yinchiga bir xil 10 savol, har biriga 10 soniya,
raundlar sinxron (ikkalasi javob bersa yoki vaqt tugasa — keyingisi). Ball: to'g'ri javob
10 + tezlik bonusi (0–10), oxirgi savol ×2; teng bo'lsa umumiy vaqti kam bo'lgan yutadi.
BOT_WAIT soniyada odam topilmasa — bot (ochiq belgilangan 🤖): aniqligi o'yinchi baliga moslanadi.

Transport — WebSocket (api/battle.py). Bu modul faqat mantiq: Hub (ulanishlar, navbat, janglar),
Match (raundlar), bot. Holat xotirada — bitta uvicorn jarayoni; jang oxirida `battles` jadvaliga
yoziladi, Oktagon ball va XP beriladi. Restart paytidagi janglar yo'qoladi (ball o'zgarmaydi).

Xavfsizlik: to'g'ri javob klientga raund TUGAGACH yuboriladi; javob vaqti serverda o'lchanadi.
"""

import asyncio
import logging
import math
import random
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from sqlalchemy import func, or_, select

from db.models import Battle, User, XpLog
from services import vocab
from services import vocab_session as vs
from services.stats import TASHKENT_OFFSET, _today

log = logging.getLogger(__name__)

QUESTIONS = 10
QUESTION_SECONDS = 10.0
GRACE = 0.5  # tarmoq kechikishi — javob shu qadar kechiksa ham qabul
ROUND_PAUSE = 1.8  # raund natijasi ko'rinib turadi
START_DELAY = 3.5  # «VS» ekrani
BOT_WAIT = 10.0  # odam kutish, keyin bot
FREE_DAILY = 20  # VIP'siz kunlik janglar (VIP — cheksiz)
XP = {"win": 8, "draw": 5, "loss": 3}
XP_DAILY_CAP = 60  # janglardan kuniga ko'pi bilan (haftalik reytingda VIP sovrinlari bor)
XP_SOURCE = "battle"
POINTS = {"win": 20, "draw": 5, "loss": -10}
BOT_POINTS = {"win": 10, "draw": 2, "loss": -5}  # bot bilan jang — yarmi
LEAGUES = [
    {"id": "bronze", "title": "Bronza", "icon": "🥉", "min": 0},
    {"id": "silver", "title": "Kumush", "icon": "🥈", "min": 150},
    {"id": "gold", "title": "Oltin", "icon": "🥇", "min": 400},
    {"id": "diamond", "title": "Olmos", "icon": "💎", "min": 800},
]
BOT_NAMES = ["Zayd", "Layla", "Umar", "Maryam", "Yusuf", "Fotima", "Bilol", "Oysha", "Solih", "Hind"]
KINDS = ("ar_uz", "uz_ar")  # tezkor jangda faqat matn (audio shovqinli joyda noqulay)


def _session_factory():
    from db.session import SessionLocal

    return SessionLocal


SESSION_FACTORY = None  # testlar almashtiradi; None — db.session.SessionLocal


def sessions():
    return (SESSION_FACTORY or _session_factory())()


# ───────────────────────── sof mantiq ─────────────────────────


def league(points: int) -> dict:
    cur = LEAGUES[0]
    for lg in LEAGUES:
        if points >= lg["min"]:
            cur = lg
    idx = LEAGUES.index(cur)
    nxt = LEAGUES[idx + 1] if idx + 1 < len(LEAGUES) else None
    return {
        "id": cur["id"],
        "title": cur["title"],
        "icon": cur["icon"],
        "next_title": nxt["title"] if nxt else "",
        "next_at": nxt["min"] if nxt else 0,
    }


def points_for(correct: bool, elapsed: float, double: bool) -> int:
    """To'g'ri javob: 10 + qolgan vaqt ulushi × 10 (tez = ko'p). Oxirgi savol ×2."""
    if not correct:
        return 0
    remaining = max(0.0, QUESTION_SECONDS - max(0.0, elapsed))
    pts = 10 + round(10 * remaining / QUESTION_SECONDS)
    return pts * 2 if double else pts


def outcome_of(p1_score: int, p2_score: int, p1_ms: int, p2_ms: int) -> int:
    """G'olib: 1 | 2 | 0 (durang). Ball teng — umumiy vaqti kam yutadi."""
    if p1_score != p2_score:
        return 1 if p1_score > p2_score else 2
    if p1_ms != p2_ms and (p1_score or p2_score):
        return 1 if p1_ms < p2_ms else 2
    return 0


def build_questions(level: str, rnd: random.Random, n: int = QUESTIONS) -> list[dict]:
    """Darajaning lug'atidan n savol (chalg'ituvchilar — o'sha mavzudan, yetmasa darajadan)."""
    pool = list(vocab.card_pool(level))
    words = rnd.sample(pool, min(n, len(pool)))
    out = []
    for i, w in enumerate(words):
        topic_pool = vocab.topic_pool(level, w["topic"]) if w.get("topic") else pool
        out.append(vs.question(w, KINDS[i % len(KINDS)], topic_pool, level, rnd))
    return out


def bot_accuracy(points: int) -> float:
    """Yangi o'yinchiga ~60% to'g'ri, kuchliga (800+ ball) ~85% — yutish imkoni ~50–60%."""
    return max(0.6, min(0.85, 0.6 + points / 3200))


def bot_move(q: dict, accuracy: float, rnd: random.Random) -> tuple[float, str | None]:
    """(kechikish soniyada, tanlov). Tanlov None — bot ulgurmadi. To'g'ri javob tezroq."""
    right = rnd.random() < accuracy
    scale = QUESTION_SECONDS / 10
    delay = (rnd.uniform(2.0, 6.5) if right else rnd.uniform(3.5, 9.3)) * scale
    if right:
        return delay, q["answer"]
    wrong = [o for o in q["options"] if o != q["answer"]]
    return delay, (rnd.choice(wrong) if wrong else None)


# ───────────────────────── o'yinchi va jang ─────────────────────────


class Conn(Protocol):
    async def send(self, msg: dict) -> None: ...


@dataclass
class Player:
    user_id: int | None  # None — bot
    name: str
    points: int
    conn: Conn | None = None
    bot: bool = False
    accuracy: float = 0.0
    score: int = 0
    correct: int = 0
    time_ms: int = 0
    answers: dict[int, dict] = field(default_factory=dict)

    def public(self) -> dict:
        return {"name": self.name, "points": self.points, "league": league(self.points), "bot": self.bot}


class Match:
    def __init__(self, hub: "Hub", level: str, p1: Player, p2: Player, rnd: random.Random | None = None):
        self.hub = hub
        self.id = secrets.token_hex(5)
        self.level = level
        self.players = [p1, p2]
        self.rnd = rnd or random.Random()
        self.questions = build_questions(level, self.rnd)
        self.i = -1
        self.sent_at = 0.0
        self.round_done = asyncio.Event()
        self.phase = "start"  # start | question | round | end
        self.finished = False
        self.forfeit_by: Player | None = None
        self.task: asyncio.Task | None = None

    # ── yordamchilar ──
    def other(self, p: Player) -> Player:
        return self.players[1] if p is self.players[0] else self.players[0]

    def player_of(self, user_id: int) -> Player | None:
        return next((p for p in self.players if p.user_id == user_id), None)

    async def send(self, p: Player, msg: dict) -> None:
        if p.bot or p.conn is None:
            return
        try:
            await p.conn.send(msg)
        except Exception:  # ulanish uzilgan — jang davom etadi, javobsiz savollar 0 ball
            p.conn = None

    def _question_msg(self, i: int) -> dict:
        q = self.questions[i]
        left = QUESTION_SECONDS
        if self.phase == "question" and i == self.i:
            left = max(0.0, QUESTION_SECONDS - (time.monotonic() - self.sent_at))
        return {
            "t": "q",
            "i": i,
            "n": len(self.questions),
            "type": q["type"],
            "prompt": q["prompt"],
            "options": q["options"],
            "seconds": round(left, 2),
            "double": i == len(self.questions) - 1,
        }

    def _matched_msg(self, p: Player, resume: bool = False) -> dict:
        o = self.other(p)
        return {
            "t": "matched",
            "match": self.id,
            "level": self.level,
            "you": p.public(),
            "opp": o.public(),
            "n": len(self.questions),
            "seconds": QUESTION_SECONDS,
            "start_in": 0 if resume else START_DELAY,
            "resume": resume,
            "score": {"you": p.score, "opp": o.score},
        }

    async def reattach(self, p: Player, conn: Conn) -> None:
        """Telegram fonga o'tib qaytdi — joriy holat qayta yuboriladi."""
        p.conn = conn
        await self.send(p, self._matched_msg(p, resume=True))
        if self.phase == "question" and self.i >= 0 and self.i not in p.answers:
            await self.send(p, self._question_msg(self.i))

    # ── oqim ──
    async def run(self) -> None:
        try:
            for p in self.players:
                await self.send(p, self._matched_msg(p))
            await asyncio.sleep(START_DELAY)
            for i in range(len(self.questions)):
                if self.forfeit_by is not None:
                    break
                await self._round(i)
            await self._finish()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # pragma: no cover — kutilmagan xato o'yinchini osilib qoldirmasin
            log.exception("Oktagon jangi xatosi: %r", e)
            for p in self.players:
                await self.send(p, {"t": "error", "msg": "Jangda xato yuz berdi — ball o'zgarmadi"})
        finally:
            self.finished = True
            self.hub.match_done(self)

    async def _round(self, i: int) -> None:
        self.i = i
        self.round_done.clear()
        self.phase = "question"
        self.sent_at = time.monotonic()
        msg = self._question_msg(i)
        for p in self.players:
            await self.send(p, msg)
        bots = [asyncio.create_task(self._bot_play(p, i)) for p in self.players if p.bot]
        try:
            await asyncio.wait_for(self.round_done.wait(), timeout=QUESTION_SECONDS + GRACE)
        except asyncio.TimeoutError:
            pass
        for t in bots:
            t.cancel()
        self.phase = "round"
        q = self.questions[i]
        for p in self.players:
            if i not in p.answers:  # ulgurmadi
                p.answers[i] = {"choice": None, "ok": False, "pts": 0}
                p.time_ms += int(QUESTION_SECONDS * 1000)
        for p in self.players:
            o = self.other(p)
            await self.send(
                p,
                {
                    "t": "round",
                    "i": i,
                    "answer": q["answer"],
                    "you": p.answers[i],
                    "opp": {"ok": o.answers[i]["ok"], "pts": o.answers[i]["pts"], "answered": o.answers[i]["choice"] is not None},
                    "score": {"you": p.score, "opp": o.score},
                },
            )
        if i < len(self.questions) - 1 and self.forfeit_by is None:
            await asyncio.sleep(ROUND_PAUSE)

    async def _bot_play(self, p: Player, i: int) -> None:
        delay, choice = bot_move(self.questions[i], p.accuracy, self.rnd)
        if choice is None or delay >= QUESTION_SECONDS:
            return
        await asyncio.sleep(delay)
        self.answer(p, i, choice)

    def answer(self, p: Player, i: int, choice: str) -> bool:
        """Javob qabul qilinadi (joriy savol, bir marta, vaqt ichida). Ball serverda hisoblanadi."""
        if self.finished or self.phase != "question" or i != self.i or i in p.answers:
            return False
        elapsed = time.monotonic() - self.sent_at
        if elapsed > QUESTION_SECONDS + GRACE:
            return False
        q = self.questions[i]
        ok = choice == q["answer"]
        pts = points_for(ok, min(elapsed, QUESTION_SECONDS), i == len(self.questions) - 1)
        p.answers[i] = {"choice": choice, "ok": ok, "pts": pts}
        p.score += pts
        p.correct += int(ok)
        p.time_ms += int(min(elapsed, QUESTION_SECONDS) * 1000)
        other = self.other(p)
        asyncio.get_running_loop().create_task(self.send(other, {"t": "opp_answered", "i": i}))
        if all(i in x.answers for x in self.players):
            self.round_done.set()
        return True

    def forfeit(self, p: Player) -> None:
        if self.finished or self.forfeit_by is not None:
            return
        self.forfeit_by = p
        self.round_done.set()

    async def _finish(self) -> None:
        self.phase = "end"
        self.finished = True
        p1, p2 = self.players
        if self.forfeit_by is not None:
            winner = 2 if self.forfeit_by is p1 else 1
            status = "forfeit"
        else:
            winner = outcome_of(p1.score, p2.score, p1.time_ms, p2.time_ms)
            status = "done"
        rewards: dict[int, dict] = {}
        try:
            async with sessions() as session:
                rewards = await persist(session, self, winner, status)
        except Exception as e:  # pragma: no cover
            log.exception("Oktagon natijasi saqlanmadi: %r", e)
        for idx, p in enumerate(self.players, start=1):
            if p.bot:
                continue
            o = self.other(p)
            res = "draw" if winner == 0 else ("win" if winner == idx else "lose")
            await self.send(
                p,
                {
                    "t": "end",
                    "result": res,
                    "reason": status,
                    "score": {"you": p.score, "opp": o.score},
                    "correct": {"you": p.correct, "opp": o.correct},
                    "n": len(self.questions),
                    **rewards.get(p.user_id or 0, {}),
                },
            )


async def _battle_xp_today(session, user_id: int) -> int:
    start = datetime.combine(_today(), datetime.min.time()) - TASHKENT_OFFSET
    total = (
        await session.execute(
            select(func.coalesce(func.sum(XpLog.amount), 0)).where(
                XpLog.user_id == user_id, XpLog.created_at >= start, XpLog.source.like(f"{XP_SOURCE}:%")
            )
        )
    ).scalar_one()
    return int(total or 0)


async def persist(session, m: Match, winner: int, status: str) -> dict[int, dict]:
    """Jang yozuvi + har odam o'yinchiga ball/XP. Qaytaradi: {user_id: {delta, points, league, xp, new_badges}}."""
    p1, p2 = m.players
    bot_game = p1.bot or p2.bot
    row = Battle(
        level=m.level,
        p1_id=p1.user_id,
        p2_id=p2.user_id,
        bot_name=(p2.name if p2.bot else ""),
        p1_score=p1.score,
        p2_score=p2.score,
        p1_correct=p1.correct,
        p2_correct=p2.correct,
        p1_time_ms=p1.time_ms,
        p2_time_ms=p2.time_ms,
        winner=winner,
        status=status,
    )
    out: dict[int, dict] = {}
    table = BOT_POINTS if bot_game else POINTS
    for idx, p in enumerate(m.players, start=1):
        if p.bot or p.user_id is None:
            continue
        res = "draw" if winner == 0 else ("win" if winner == idx else "loss")
        user = await session.get(User, p.user_id)
        if user is None:
            continue
        before = user.battle_points or 0
        after = max(0, before + table[res])
        user.battle_points = after
        user.battle_games = (user.battle_games or 0) + 1
        if res == "win":
            user.battle_wins = (user.battle_wins or 0) + 1
        delta = after - before
        if idx == 1:
            row.p1_delta = delta
        else:
            row.p2_delta = delta
        xp = XP[res] if not bot_game else math.ceil(XP[res] / 2)
        xp = min(xp, max(0, XP_DAILY_CAP - await _battle_xp_today(session, p.user_id)))
        if xp:
            session.add(XpLog(user_id=p.user_id, amount=xp, source=f"{XP_SOURCE}:{m.level}"))
        out[p.user_id] = {"delta": delta, "points": after, "league": league(after), "xp": xp}
    session.add(row)
    await session.commit()
    try:
        from api.v2 import _badges

        for uid in out:
            out[uid]["new_badges"] = await _badges(session, uid)
    except Exception:  # pragma: no cover
        pass
    return out


# ───────────────────────── hub: ulanishlar, navbat ─────────────────────────


@dataclass
class Waiter:
    user_id: int
    name: str
    points: int
    level: str
    conn: Conn
    since: float = field(default_factory=time.monotonic)
    timer: asyncio.Task | None = None


class Hub:
    def __init__(self):
        self.conns: dict[int, Conn] = {}
        self.queue: dict[str, list[Waiter]] = {}
        self.waiting: dict[int, Waiter] = {}
        self.matches: dict[int, Match] = {}  # user_id → faol jang

    def online(self) -> int:
        return len(self.conns)

    def in_queue(self, level: str) -> int:
        return len(self.queue.get(level, []))

    async def connect(self, user_id: int, conn: Conn) -> bool:
        """Ulanish ro'yxatga olinadi; faol jang bo'lsa — davom ettiriladi. True — jang tiklandi."""
        self.conns[user_id] = conn
        m = self.matches.get(user_id)
        if m and not m.finished:
            p = m.player_of(user_id)
            if p:
                await m.reattach(p, conn)
                return True
        return False

    def disconnect(self, user_id: int, conn: Conn) -> None:
        if self.conns.get(user_id) is conn:
            del self.conns[user_id]
            self.cancel(user_id)
            m = self.matches.get(user_id)
            p = m.player_of(user_id) if m else None
            if p and p.conn is conn:
                p.conn = None  # jang davom etadi; qaytsa — reattach

    def cancel(self, user_id: int) -> bool:
        w = self.waiting.pop(user_id, None)
        if not w:
            return False
        q = self.queue.get(w.level, [])
        if w in q:
            q.remove(w)
        if w.timer and not w.timer.done():
            w.timer.cancel()
        return True

    async def join(self, user_id: int, name: str, points: int, level: str, conn: Conn) -> str:
        """Navbatga qo'yadi yoki darhol raqib bilan jang boshlaydi. Qaytaradi: queued | matched | busy."""
        if user_id in self.matches:
            return "busy"
        self.cancel(user_id)
        queue = self.queue.setdefault(level, [])
        opp = next((w for w in queue if w.user_id != user_id and self.conns.get(w.user_id) is w.conn), None)
        if opp:
            self.cancel(opp.user_id)
            self._start(level, Player(opp.user_id, opp.name, opp.points, opp.conn), Player(user_id, name, points, conn))
            return "matched"
        w = Waiter(user_id, name, points, level, conn)
        queue.append(w)
        self.waiting[user_id] = w
        w.timer = asyncio.get_running_loop().create_task(self._bot_after(w))
        return "queued"

    async def _bot_after(self, w: Waiter) -> None:
        await asyncio.sleep(BOT_WAIT)
        if self.waiting.get(w.user_id) is not w:
            return
        self.waiting.pop(w.user_id, None)
        q = self.queue.get(w.level, [])
        if w in q:
            q.remove(w)
        rnd = random.Random()
        bot = Player(
            None,
            rnd.choice(BOT_NAMES),
            max(0, w.points + rnd.randint(-30, 30)),
            bot=True,
            accuracy=bot_accuracy(w.points),
        )
        self._start(w.level, Player(w.user_id, w.name, w.points, w.conn), bot, rnd)

    def _start(self, level: str, p1: Player, p2: Player, rnd: random.Random | None = None) -> Match:
        m = Match(self, level, p1, p2, rnd)
        for p in (p1, p2):
            if p.user_id is not None:
                self.matches[p.user_id] = m
        m.task = asyncio.get_running_loop().create_task(m.run())
        return m

    def answer(self, user_id: int, i: int, choice: str) -> bool:
        m = self.matches.get(user_id)
        p = m.player_of(user_id) if m else None
        return bool(p and m.answer(p, i, choice))

    def leave(self, user_id: int) -> bool:
        m = self.matches.get(user_id)
        p = m.player_of(user_id) if m else None
        if not p:
            return False
        m.forfeit(p)
        return True

    def match_done(self, m: Match) -> None:
        for p in m.players:
            if p.user_id is not None and self.matches.get(p.user_id) is m:
                del self.matches[p.user_id]


HUB = Hub()


# ───────────────────────── DB so'rovlari (REST uchun) ─────────────────────────


async def today_count(session, user_id: int) -> int:
    start = datetime.combine(_today(), datetime.min.time()) - TASHKENT_OFFSET
    return int(
        (
            await session.execute(
                select(func.count(Battle.id)).where(
                    or_(Battle.p1_id == user_id, Battle.p2_id == user_id), Battle.created_at >= start
                )
            )
        ).scalar_one()
        or 0
    )


async def top(session, limit: int = 50) -> list[dict]:
    rows = (
        await session.execute(
            select(User.id, User.name, User.battle_points, User.battle_wins, User.battle_games)
            .where(User.battle_games > 0, User.is_demo == 0)
            .order_by(User.battle_points.desc(), User.battle_wins.desc(), User.id)
            .limit(limit)
        )
    ).all()
    return [
        {"rank": i + 1, "user_id": uid, "name": name or "O'quvchi", "points": pts or 0, "wins": w or 0, "games": g or 0, "league": league(pts or 0)}
        for i, (uid, name, pts, w, g) in enumerate(rows)
    ]


async def rank_of(session, user: User) -> int:
    if not user.battle_games:
        return 0
    higher = (
        await session.execute(
            select(func.count(User.id)).where(
                User.battle_games > 0, User.is_demo == 0, User.battle_points > (user.battle_points or 0)
            )
        )
    ).scalar_one()
    return int(higher or 0) + 1


async def history(session, user_id: int, limit: int = 20) -> list[dict]:
    rows = (
        await session.execute(
            select(Battle)
            .where(or_(Battle.p1_id == user_id, Battle.p2_id == user_id))
            .order_by(Battle.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    opp_ids = {r.p2_id if r.p1_id == user_id else r.p1_id for r in rows} - {None}
    names = {}
    if opp_ids:
        names = dict((await session.execute(select(User.id, User.name).where(User.id.in_(opp_ids)))).all())
    out = []
    for r in rows:
        me1 = r.p1_id == user_id
        opp_id = r.p2_id if me1 else r.p1_id
        my_idx = 1 if me1 else 2
        res = "draw" if r.winner == 0 else ("win" if r.winner == my_idx else "lose")
        out.append(
            {
                "id": r.id,
                "level": r.level,
                "opp": r.bot_name if opp_id is None else (names.get(opp_id) or "O'quvchi"),
                "bot": opp_id is None,
                "you": r.p1_score if me1 else r.p2_score,
                "them": r.p2_score if me1 else r.p1_score,
                "result": res,
                "forfeit": r.status == "forfeit",
                "delta": r.p1_delta if me1 else r.p2_delta,
                "at": (r.created_at + TASHKENT_OFFSET).strftime("%d.%m %H:%M") if r.created_at else "",
            }
        )
    return out
