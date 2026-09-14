"""AI ustoz — darajaga mos jonli suhbat (speaking) dvigateli (K17).

Model: Haiku 4.5 (arzon, tez). Javob STRUCTURED OUTPUT (Pydantic) — model
qat'iy JSON qaytaradi, matn-marker parsing yo'q, hech qachon sinmaydi.

Token tejash:
  1. System prompt ikki blok: umumiy qoidalar + o'quvchi bloki (profil,
     daraja, lug'at). Oxirgi blokda `cache_control` — keyingi turnlarda
     90% arzon o'qiladi. Haiku 4.5 uchun cache minimal 4096 token, shuning
     uchun lug'at bloki ataylab to'liq (300+ so'z) — bu ham arzon, ham
     model o'quvchi lug'ati ichida gapiradi (i+1 tamoyili).
  2. Faqat oxirgi HISTORY_TURNS xabar yuboriladi.
  3. max_tokens kichik; javob uzunligi daraja profilida cheklangan.
  4. Kunlik limit (settings.tutor_daily_turns) — api qatlamida.

O'quvchi kiritishi: arabcha (harakatsiz ham), lotin translit, o'zbekcha yoki
mikrofon (STT xatolari bilan) — model ma'noga qarab tushunadi va har turnda
alohida `correction` maydonida tuzatadi.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import UserWord
from services.reference import normalize
from services.vocab import LEVELS, load_level

log = logging.getLogger(__name__)

HISTORY_TURNS = 10  # oxirgi xabarlar (user+assistant) — kontekst chegarasi
MAX_TOKENS = 400
KNOWN_WORDS_LIMIT = 200  # SRS'dan o'rganilgan so'zlar
TOPIC_WORDS_LIMIT = 200  # mavzu lug'ati (daraja ≤ o'quvchi darajasi)
MIN_TURNS_TO_END = 6  # AI suhbatni shundan oldin tugatmaydi


# ────────────────────────── Javob sxemasi ──────────────────────────


class NewWord(BaseModel):
    ar: str = Field(description="Arabic word with full harakat")
    translit: str = Field(description="Latin transliteration")
    uz: str = Field(description="Uzbek meaning")


class TutorReply(BaseModel):
    ar: str = Field(description="Your reply in Arabic with full harakat")
    translit: str = Field(description="Latin transliteration of `ar`")
    uz: str = Field(description="Uzbek translation of `ar` (may be empty per profile)")
    correction_ok: bool = Field(
        description="True if the learner's last message was acceptable for the level"
    )
    fixed_ar: str = Field(
        description="Corrected learner sentence with harakat; empty when correction_ok"
    )
    note_uz: str = Field(
        description="One short Uzbek sentence explaining the fix; empty when correction_ok"
    )
    hint_uz: str = Field(
        description="Short Uzbek suggestion of what the learner can answer; empty if none"
    )
    new_words: list[NewWord] = Field(
        default_factory=list, description="0-2 words introduced in this turn"
    )
    done: bool = Field(description="True only when the conversation naturally ended")


# ────────────────────────── Mavzular ──────────────────────────
# themes — content/vocab/*.json dagi `theme` maydonlari; bo'sh = umumiy lug'at

TOPICS: list[dict] = [
    {
        "id": "tanishish",
        "emoji": "👋",
        "title_uz": "Tanishish",
        "desc_uz": "Ism, qayerdan, nima ish qilasiz",
        "min_level": "A0",
        "themes": ["salomlashuv", "oila", "kasblar", "geografiya"],
        "role": "a friendly new neighbour in Madinah meeting the learner for the first time",
        "goal": "exchange names, where you are from, what you do, and say goodbye",
    },
    {
        "id": "oila",
        "emoji": "👨‍👩‍👧",
        "title_uz": "Oila",
        "desc_uz": "Oila a'zolari, yosh, kasblar",
        "min_level": "A0",
        "themes": ["oila", "kasblar", "son-olchov", "uy"],
        "role": "a curious friend who wants to know about the learner's family",
        "goal": "talk about family members, how many, their ages and jobs",
    },
    {
        "id": "kun_tartibi",
        "emoji": "⏰",
        "title_uz": "Kun tartibi",
        "desc_uz": "Ertalabdan kechgacha nima qilasiz",
        "min_level": "A1",
        "themes": ["vaqt", "fellar", "uy", "maktab", "ovqat"],
        "role": "a roommate chatting about daily routines",
        "goal": "describe the learner's day: waking up, meals, study or work, evening",
    },
    {
        "id": "bozor",
        "emoji": "🛒",
        "title_uz": "Bozor va xarid",
        "desc_uz": "Narx so'rash, savdolashish",
        "min_level": "A1",
        "themes": ["xarid", "ovqat", "son-olchov", "kiyim", "pul-bank", "rang-shakl"],
        "role": "a cheerful market seller in Jeddah",
        "goal": "the learner asks prices, bargains and buys something",
    },
    {
        "id": "restoran",
        "emoji": "🍽️",
        "title_uz": "Restoran",
        "desc_uz": "Buyurtma, halol so'rash, hisob",
        "min_level": "A1",
        "themes": ["restoran", "ovqat", "son-olchov"],
        "role": "a waiter in a restaurant in Makkah",
        "goal": "the learner orders food and drink, asks about halal, pays the bill",
    },
    {
        "id": "safar",
        "emoji": "✈️",
        "title_uz": "Sayohat va aeroport",
        "desc_uz": "Chipta, pasport, yo'l so'rash",
        "min_level": "A1",
        "themes": ["safar", "shahar-transport", "hujjat", "mehmonxona", "vaqt"],
        "role": "an airport officer, then a taxi driver, helping the learner travel",
        "goal": "passport check, finding the way, taking a taxi to the hotel",
    },
    {
        "id": "umra",
        "emoji": "🕋",
        "title_uz": "Umra va Makka",
        "desc_uz": "Haramda, mehmonxonada, yo'lda",
        "min_level": "A1",
        "themes": ["marosim", "safar", "mehmonxona", "shahar-transport", "salomlashuv"],
        "role": "a kind volunteer guide at the Haram in Makkah",
        "goal": "help the learner find their way, ask about prayer times, hotel and food",
    },
    {
        "id": "shifokor",
        "emoji": "🩺",
        "title_uz": "Shifokor qabulida",
        "desc_uz": "Shikoyat, dori, maslahat",
        "min_level": "A2",
        "themes": ["salomatlik", "vaqt", "son-olchov"],
        "role": "a doctor at a clinic",
        "goal": "the learner describes symptoms, the doctor asks questions and gives advice",
    },
    {
        "id": "ish",
        "emoji": "💼",
        "title_uz": "Ish va intervyu",
        "desc_uz": "Tajriba, rejalar, ish suhbati",
        "min_level": "B1",
        "themes": ["ish", "kasblar", "hujjat", "tafakkur", "texnologiya"],
        "role": "an HR manager interviewing the learner for a job",
        "goal": "discuss experience, strengths, plans and salary expectations",
    },
    {
        "id": "munozara",
        "emoji": "🗣️",
        "title_uz": "Munozara",
        "desc_uz": "Fikr bildirish, dalil keltirish",
        "min_level": "B1",
        "themes": [
            "yangiliklar",
            "davlat-qonun",
            "tafakkur",
            "texnologiya",
            "ekologiya",
            "iqtisod",
        ],
        "role": "a thoughtful debate partner who politely disagrees",
        "goal": "the learner states an opinion on a current topic and defends it with reasons",
    },
    {
        "id": "erkin",
        "emoji": "💬",
        "title_uz": "Erkin suhbat",
        "desc_uz": "Xohlagan mavzuda gaplashing",
        "min_level": "A0",
        "themes": [],
        "role": "a warm Arabic-speaking friend",
        "goal": "free conversation — follow whatever the learner wants to talk about",
    },
]

TOPIC_BY_ID = {t["id"]: t for t in TOPICS}


def topic_list(level: str) -> list[dict]:
    """Frontend uchun mavzular — o'quvchi darajasiga mos bo'lganlari oldinda."""
    li = _level_index(level)
    out = []
    for t in TOPICS:
        out.append(
            {
                "id": t["id"],
                "emoji": t["emoji"],
                "title_uz": t["title_uz"],
                "desc_uz": t["desc_uz"],
                "min_level": t["min_level"],
                # Yuqori daraja mavzusi qulflanmaydi — AI baribir moslashadi,
                # faqat "B1+" yorlig'i bilan ogohlantiriladi
                "recommended": _level_index(t["min_level"]) <= li,
            }
        )
    out.sort(key=lambda x: (not x["recommended"], 0))
    return out


# ────────────────────────── Daraja profillari ──────────────────────────

LEVEL_PROFILES = {
    "A0": (
        "Absolute beginner: knows the letters and a handful of words. `ar` is at most "
        "4 words. Use only greetings, names, 'I am', 'this is', simple nouns, yes/no "
        "questions. Accept one-word answers as correct. ALWAYS fill `hint_uz` with a "
        "concrete answer template, e.g. \"Ismingizni ayting: اِسْمِي ...\". "
        "`uz` is always filled."
    ),
    "A1": (
        "Beginner: `ar` is at most 8 words, present tense, simple questions (what, "
        "where, who, how many, do you like). ALWAYS fill `hint_uz` with what the "
        "learner can answer. `uz` is always filled."
    ),
    "A2": (
        "Elementary: `ar` is 1-2 short sentences (max 15 words), past and present, "
        "adjectives, simple conjunctions. Correct gender/number agreement and verb "
        "forms. `hint_uz` only when the learner seems stuck or answered with one "
        "word. `uz` is always filled."
    ),
    "B1": (
        "Intermediate: `ar` is up to 2 sentences (max 25 words). Ask for opinions and "
        "reasons (لِأَنَّ, لِذَلِكَ), use conditionals and connectors. `uz` is a SHORT "
        "paraphrase (max 8 words) so the learner reads the Arabic first. `hint_uz` "
        "stays empty unless the learner asks for help."
    ),
    "B2": (
        "Upper-intermediate: `ar` is 2-3 sentences (max 40 words), natural idioms, "
        "complex syntax, abstract topics. `uz` is EMPTY unless the sentence contains "
        "a word from `new_words`. Corrections also address style and word choice. "
        "`hint_uz` stays empty."
    ),
}


def _level_index(level: str) -> int:
    lv = (level or "A0").upper()
    return LEVELS.index(lv) if lv in LEVELS else 0


# ────────────────────────── Promptlar ──────────────────────────
# Qoidalar inglizcha — Haiku aniq ko'rsatmalarni inglizchada eng ishonchli
# bajaradi; o'quvchiga ko'rinadigan matnlar (uz maydonlari) o'zbekcha.

RULES = """You are "Jamal" (جَمَال), a warm, patient Arabic tutor inside the "Arabiy" app for Uzbek speakers. Goal: SPEAKING practice through a natural conversation on the given topic, adapted to the learner's level. You play the role described in the learner block.

HARD RULES
1. `ar` is ALWAYS Modern Standard Arabic with FULL harakat (tashkil) on every word. Never write English anywhere. Never write Latin letters inside `ar`.
2. Respect the length limit of the level profile. Ask exactly ONE question per turn so the learner can answer.
3. Use vocabulary from the LEARNER VOCABULARY and TOPIC VOCABULARY lists. You may introduce at most 1-2 new words per turn and MUST list them in `new_words`. Prefer words the learner already knows.
4. `translit`: Latin transliteration of `ar`, Uzbek-friendly: sh, ch, x for خ, gʻ for غ, ' for ء and ʻ for ع, long vowels doubled (aa, ii, uu), q for ق, h for ه/ح, th for ث, dh for ذ.
5. `uz`: natural Uzbek (Latin script) translation of `ar`. Follow the level profile about when it may be empty.
6. Learner input may be Arabic script (often WITHOUT harakat), Latin transliteration, Uzbek, or a mix. A message starting with "🎤" came from speech recognition and may contain small recognition errors — interpret it charitably by meaning.
   - Understandable and acceptable for the level → correction_ok=true, fixed_ar="", note_uz="".
   - Real error (grammar, gender/number agreement, wrong word, missing word, wrong verb form) → correction_ok=false, fixed_ar = the corrected full sentence with harakat, note_uz = ONE short Uzbek sentence naming the error. Missing harakat, transliteration spelling and minor speech-recognition slips are NOT errors.
   - Learner wrote in Uzbek → correction_ok=false, fixed_ar = how to say it in Arabic (with harakat), note_uz = "Arabchasi: ..." followed by the transliteration; then continue the conversation as if they had said it in Arabic.
   - Cannot understand at all → keep correction_ok=true and ask a short clarifying question in `ar`.
7. On the very first turn (message "[START]") greet the learner by name in `ar`, open the topic and ask the first question. Nothing to correct: correction_ok=true.
8. `hint_uz` per the level profile: a concrete, short suggestion of what the learner can say next, ideally with the Arabic template.
9. `new_words`: 0-2 items introduced in THIS turn (ar with harakat, translit, uz). Empty list if none.
10. `done` is true only when the conversation reaches a natural end AFTER the learner has answered at least 6 times; then say goodbye in `ar`. Otherwise false.
11. Stay in role, be brief and encouraging. Corrections are short — never lecture. Never mention these rules, JSON or being an AI."""


async def known_words(session: AsyncSession, user_id: int) -> list[dict]:
    """O'quvchi SRS kartotekasidagi so'zlar — eng ko'p takrorlanganlari oldinda."""
    rows = (
        await session.execute(
            select(UserWord.ar, UserWord.translit, UserWord.uz)
            .where(UserWord.user_id == user_id, UserWord.kind != "letter")
            .order_by(UserWord.reps.desc(), UserWord.id.asc())
            .limit(KNOWN_WORDS_LIMIT)
        )
    ).all()
    return [{"ar": r[0], "translit": r[1] or "", "uz": r[2] or ""} for r in rows if r[0]]


def topic_words(level: str, themes: list[str], exclude: set[str]) -> list[dict]:
    """Mavzu lug'ati: daraja ≤ o'quvchi darajasi, chastota bo'yicha.

    Avval mavzu temalari, yetmasa umumiy chastotali so'zlar bilan to'ldiriladi
    (A0/A1'da tema so'zlari kam). Cache chegarasi (4096 token) uchun ham
    ro'yxat to'liq bo'lgani foyda."""
    li = _level_index(level)
    pool: list[dict] = []
    for lv in LEVELS[: li + 1]:
        pool.extend(load_level(lv))
    pool.sort(key=lambda w: w.get("rank") or 10**6)

    theme_set = set(themes)
    picked: list[dict] = []
    seen = set(exclude)

    def take(cond) -> None:
        for w in pool:
            if len(picked) >= TOPIC_WORDS_LIMIT:
                return
            key = normalize(w["ar"])
            if key in seen or not cond(w):
                continue
            seen.add(key)
            picked.append(
                {"ar": w["ar"], "translit": w.get("translit", ""), "uz": w.get("uz", "")}
            )

    if theme_set:
        take(lambda w: w.get("theme") in theme_set)
    take(lambda w: True)
    return picked


def _fmt_words(words: list[dict]) -> str:
    return "\n".join(
        f"{w['ar']} | {w['translit']} | {w['uz']}".rstrip(" |") for w in words
    )


def build_system(
    *, name: str, level: str, topic: dict, known: list[dict], extra: list[dict]
) -> list[dict]:
    """System prompt bloklari. Oxirgi blok cache'lanadi (prefix barqaror)."""
    lv = level.upper() if level.upper() in LEVEL_PROFILES else "A0"
    learner_block = (
        f"LEARNER\n- Name: {name or 'the learner'}\n- Level: {lv}\n"
        f"- Topic: {topic['title_uz']} — goal: {topic['goal']}\n"
        f"- Your role: {topic['role']}\n\n"
        f"LEVEL PROFILE ({lv})\n{LEVEL_PROFILES[lv]}\n\n"
        f"LEARNER VOCABULARY (ar | translit | uz) — already studied, prefer these:\n"
        f"{_fmt_words(known) or '(none yet)'}\n\n"
        f"TOPIC VOCABULARY (allowed; may be new to the learner):\n"
        f"{_fmt_words(extra) or '(none)'}"
    )
    return [
        {"type": "text", "text": RULES},
        {
            "type": "text",
            "text": learner_block,
            "cache_control": {"type": "ephemeral"},
        },
    ]


def _trim_history(history: list[dict]) -> list[dict]:
    """Faqat matnli, navbatma-navbat xabarlar; oxirgi HISTORY_TURNS tasi."""
    msgs = [
        {"role": m["role"], "content": str(m.get("content", "")).strip()}
        for m in history
        if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()
    ]
    msgs = msgs[-HISTORY_TURNS:]
    # Tarix doim ustozning ochilish savoli (assistant) bilan boshlanadi; API
    # esa navbat user'dan boshlanishini talab qiladi — oldiga [START] qo'yamiz
    # (ochilishda ham aynan shu xabar yuborilgan, model uchun izchil)
    if msgs and msgs[0]["role"] != "user":
        msgs.insert(0, {"role": "user", "content": "[START]"})
    # Ketma-ket bir xil rol bo'lsa birlashtiramiz
    merged: list[dict] = []
    for m in msgs:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1]["content"] += "\n" + m["content"]
        else:
            merged.append(dict(m))
    return merged


class TutorUnavailable(Exception):
    """AI javob bera olmadi (kalit/kredit/tarmoq) — API 503 qaytaradi,
    turn hisobga olinmaydi, o'quvchi tushunarli xabar ko'radi."""

    def __init__(self, message_uz: str):
        super().__init__(message_uz)
        self.message_uz = message_uz


def _user_message(e: Exception) -> str:
    text = repr(e)
    if "credit balance" in text or "billing" in text.lower():
        log.error("AI ustoz: Anthropic krediti tugagan — to'ldirish kerak!")
        return "Ustoz hozircha band (server sozlanmoqda). Birozdan keyin qayta kiring."
    if "authentication" in text.lower() or "api_key" in text.lower():
        log.error("AI ustoz: Anthropic kaliti noto'g'ri!")
        return "Ustoz hozircha band (server sozlanmoqda). Birozdan keyin qayta kiring."
    if "rate_limit" in text or "overloaded" in text:
        return "Ustoz hozir juda band — bir daqiqadan keyin urinib ko'ring."
    return "Ustoz javob bera olmadi. Internetni tekshirib, qayta urinib ko'ring."


async def reply(
    *,
    name: str,
    level: str,
    topic_id: str,
    history: list[dict],
    known: list[dict],
) -> tuple[TutorReply, dict]:
    """Keyingi ustoz javobi. Qaytaradi: (javob, usage). Xatoda TutorUnavailable.

    history: [{role:'user'|'assistant', content}] — assistant xabarlari faqat
    `ar` matni (JSON emas) — token tejaladi. Bo'sh tarix = suhbat boshi."""
    topic = TOPIC_BY_ID.get(topic_id) or TOPIC_BY_ID["erkin"]
    if not settings.anthropic_api_key:
        raise TutorUnavailable("AI ustoz hozircha o'chiq (kalit sozlanmagan).")

    from anthropic import AsyncAnthropic

    extra = topic_words(level, topic["themes"], {normalize(w["ar"]) for w in known})
    system = build_system(name=name, level=level, topic=topic, known=known, extra=extra)
    msgs = _trim_history(history) or [{"role": "user", "content": "[START]"}]
    if msgs[-1]["role"] != "user":
        msgs.append({"role": "user", "content": "(davom eting)"})

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    out: TutorReply | None = None
    resp = None
    try:
        resp = await client.messages.parse(
            model=settings.tutor_model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=msgs,
            output_format=TutorReply,
        )
        out = resp.parsed_output
    except Exception as e:
        # Structured output rad etilsa (model/versiya) — oddiy JSON rejimi
        log.warning("AI ustoz (structured) xatosi: %r — JSON rejimiga o'tildi", e)
        try:
            resp = await client.messages.create(
                model=settings.tutor_model,
                max_tokens=MAX_TOKENS,
                system=system
                + [
                    {
                        "type": "text",
                        "text": "Respond ONLY with a JSON object with keys: ar, translit, uz, "
                        "correction_ok (bool), fixed_ar, note_uz, hint_uz, new_words "
                        "(list of {ar, translit, uz}), done (bool). No prose, no code fences.",
                    }
                ],
                messages=msgs,
            )
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            text = text.strip("`").removeprefix("json").strip()
            out = TutorReply.model_validate_json(text)
        except Exception as e2:  # kredit tugadi / tarmoq — o'quvchi ekrani buzilmasin
            log.warning("AI ustoz xatosi: %r", e2)
            raise TutorUnavailable(_user_message(e2)) from e2

    if out is None:
        raise TutorUnavailable("Ustoz javobi o'qilmadi. Qayta urinib ko'ring.")

    u = getattr(resp, "usage", None)
    usage = {
        "in": getattr(u, "input_tokens", 0),
        "out": getattr(u, "output_tokens", 0),
        "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
    }
    # AI 6 javobdan oldin yakunlamasin (qoida 10 ni kod ham kafolatlaydi)
    user_turns = sum(1 for m in history if m.get("role") == "user")
    if out.done and user_turns < MIN_TURNS_TO_END:
        out.done = False
    out.new_words = out.new_words[:2]
    return out, usage


# ────────────────────────── Talaffuz bahosi (LLM'siz) ──────────────────────────

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def _clean(s: str) -> str:
    return _PUNCT.sub(" ", normalize(s)).strip()


def pronunciation_score(target: str, heard: str) -> dict:
    """STT matni kutilgan jumlaga qanchalik yaqin — 0..100.

    Harakat, hamza/alif, ta-marbuta farqlari hisobga olinmaydi (normalize).
    So'zma-so'z belgilanadi: qaysi so'z eshitilmadi — o'quvchi ko'radi."""
    t, h = _clean(target), _clean(heard)
    if not t:
        return {"score": 0, "words": []}
    h_set = set(h.split())
    words = []
    for w_orig in target.split():
        w = _clean(w_orig)
        if w:  # yolg'iz tinish belgisi so'z emas
            words.append({"ar": w_orig, "ok": w in h_set})
    word_ratio = sum(1 for w in words if w["ok"]) / max(len(words), 1)
    char_ratio = SequenceMatcher(None, t, h).ratio() if h else 0.0
    score = round(100 * (0.55 * char_ratio + 0.45 * word_ratio))
    if word_ratio == 1.0 and char_ratio >= 0.9:
        score = 100  # hamma so'z eshitildi — tinish belgisi farqi jarima emas
    return {"score": max(0, min(100, score)), "words": words}
