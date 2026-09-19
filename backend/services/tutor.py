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
from services import ai_usage
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
    answer_uz: str = Field(
        default="",
        description=(
            "If the learner asked a question or wanted an explanation (about a word, "
            "grammar, pronunciation, culture, how to say something), answer it here in "
            "clear Uzbek, 2-4 sentences, with Arabic examples with harakat. Otherwise empty."
        ),
    )
    done: bool = Field(description="True only when the conversation naturally ended")


class MockReply(BaseModel):
    """Speaking mock imtihoni: keyingi savol + oldingi javob bahosi."""

    ar: str = Field(description="Next exam question in Arabic with full harakat (closing line when done)")
    translit: str = Field(description="Latin transliteration of `ar`")
    uz: str = Field(description="Uzbek translation of `ar`")
    score: int = Field(
        description="0-100 overall score of the learner's previous answer; -1 on the first turn"
    )
    vocab: int = Field(
        description="0-100 vocabulary: range and appropriateness for the field and level; -1 on the first turn"
    )
    grammar: int = Field(
        description="0-100 grammar: agreement, verb forms, word order, case endings if attempted; -1 on the first turn"
    )
    content: int = Field(
        description="0-100 content and fluency: relevance to the question, completeness, natural flow; -1 on the first turn"
    )
    feedback_uz: str = Field(
        description="1-2 Uzbek sentences on the previous answer: what was good, what to fix; empty on the first turn"
    )
    ideal_ar: str = Field(
        description="A model answer to the previous question at the learner's level, with harakat; empty on the first turn"
    )
    done: bool = Field(description="True after the last answer has been graded")


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

# ────────────────────────── Speaking mock imtihonlari ──────────────────────────
# Kasb/soha bo'yicha 5 savollik og'zaki imtihon: har javob 0-100 baholanadi,
# o'rtacha ball natija va XP bo'ladi (api/v2.py tutor_finish).

MOCK_QUESTIONS = 5

MOCKS: list[dict] = [
    {
        "id": "shifokor",
        "emoji": "🩺",
        "title_uz": "Shifokor / hamshira",
        "desc_uz": "Bemor bilan muloqot, shikoyat, dori",
        "min_level": "A2",
        "themes": ["salomatlik", "vaqt", "son-olchov"],
        "field": "healthcare: a doctor or nurse talking with patients, symptoms, medicine, advice",
    },
    {
        "id": "haydovchi",
        "emoji": "🚕",
        "title_uz": "Haydovchi",
        "desc_uz": "Yo'l, manzil, narx, yo'lovchi bilan gap",
        "min_level": "A1",
        "themes": ["shahar-transport", "safar", "son-olchov", "pul-bank"],
        "field": "a taxi or bus driver: routes, directions, fares, talking with passengers",
    },
    {
        "id": "sotuvchi",
        "emoji": "🛍️",
        "title_uz": "Sotuvchi / savdo",
        "desc_uz": "Mahsulot, narx, savdolashish, mijoz",
        "min_level": "A1",
        "themes": ["xarid", "pul-bank", "son-olchov", "kiyim", "ovqat"],
        "field": "a shop or market seller: products, prices, bargaining, serving customers",
    },
    {
        "id": "mehmonxona",
        "emoji": "🏨",
        "title_uz": "Mehmonxona xodimi",
        "desc_uz": "Bron, xona, mehmon muammolari",
        "min_level": "A1",
        "themes": ["mehmonxona", "safar", "uy", "vaqt"],
        "field": "hotel reception: bookings, rooms, guest requests and complaints",
    },
    {
        "id": "oshpaz",
        "emoji": "👨‍🍳",
        "title_uz": "Oshpaz / ofitsiant",
        "desc_uz": "Menyu, taomlar, buyurtma",
        "min_level": "A1",
        "themes": ["restoran", "ovqat", "son-olchov"],
        "field": "a cook or waiter: menu, dishes, ingredients, taking orders",
    },
    {
        "id": "oqituvchi",
        "emoji": "📚",
        "title_uz": "O'qituvchi",
        "desc_uz": "Dars, o'quvchilar, tushuntirish",
        "min_level": "A2",
        "themes": ["maktab", "tafakkur", "vaqt"],
        "field": "a teacher: lessons, students, explaining topics, school life",
    },
    {
        "id": "it",
        "emoji": "💻",
        "title_uz": "IT mutaxassisi",
        "desc_uz": "Dastur, kompyuter, muammo yechish",
        "min_level": "B1",
        "themes": ["texnologiya", "ish", "tafakkur"],
        "field": "an IT specialist: software, computers, solving technical problems, teamwork",
    },
    {
        "id": "gid",
        "emoji": "🕋",
        "title_uz": "Umra gidi",
        "desc_uz": "Ziyoratchilar, Makka-Madina, tartib",
        "min_level": "A2",
        "themes": ["marosim", "safar", "shahar-transport", "mehmonxona"],
        "field": "an umrah group guide: helping pilgrims in Makkah and Madinah, schedules, places",
    },
    {
        "id": "intervyu",
        "emoji": "💼",
        "title_uz": "Ish intervyusi",
        "desc_uz": "Tajriba, kuchli tomonlar, rejalar",
        "min_level": "B1",
        "themes": ["ish", "kasblar", "hujjat", "tafakkur"],
        "field": "a job interview: experience, strengths, weaknesses, plans, salary",
    },
    {
        "id": "talaba",
        "emoji": "🎓",
        "title_uz": "Talaba",
        "desc_uz": "Universitet, fanlar, kelajak",
        "min_level": "A2",
        "themes": ["maktab", "tafakkur", "vaqt", "kasblar"],
        "field": "a university student: studies, subjects, daily life, future plans",
    },
    {
        "id": "tikuvchi",
        "emoji": "🧵",
        "title_uz": "Tikuvchi",
        "desc_uz": "O'lchov, mato, buyurtma, muddat",
        "min_level": "A1",
        "themes": ["kiyim", "xarid", "son-olchov", "rang-shakl", "pul-bank"],
        "field": "a tailor or seamstress: taking measurements, fabrics, colours, orders and deadlines, prices",
    },
    {
        "id": "quruvchi",
        "emoji": "🏗️",
        "title_uz": "Quruvchi",
        "desc_uz": "Ish joyi, asboblar, xavfsizlik",
        "min_level": "A1",
        "themes": ["ish", "uy", "son-olchov", "kasblar"],
        "field": "a construction worker: the site, tools and materials, safety, working hours, talking with the foreman",
    },
    {
        "id": "sartarosh",
        "emoji": "💈",
        "title_uz": "Sartarosh",
        "desc_uz": "Soch, soqol, mijoz xohishi",
        "min_level": "A1",
        "themes": ["xarid", "son-olchov", "rang-shakl", "munosabat"],
        "field": "a barber or hairdresser: haircuts, beard, what the customer wants, prices, appointments",
    },
    {
        "id": "aeroport",
        "emoji": "✈️",
        "title_uz": "Aeroport xodimi",
        "desc_uz": "Ro'yxat, yuk, pasport, reys",
        "min_level": "A2",
        "themes": ["safar", "hujjat", "vaqt", "shahar-transport"],
        "field": "airport or airline staff: check-in, luggage, passports and visas, flight times, helping passengers",
    },
    {
        "id": "farmatsevt",
        "emoji": "💊",
        "title_uz": "Dorixona",
        "desc_uz": "Dori, retsept, qanday ichish",
        "min_level": "A2",
        "themes": ["salomatlik", "son-olchov", "vaqt", "pul-bank"],
        "field": "a pharmacist: prescriptions, medicines, dosage and timing, side effects, advising customers",
    },
    {
        "id": "masjid",
        "emoji": "🕌",
        "title_uz": "Masjid xodimi",
        "desc_uz": "Namoz vaqtlari, ziyoratchi, xayriya",
        "min_level": "A2",
        "themes": ["marosim", "vaqt", "munosabat", "his-tuygu"],
        "field": "a mosque worker or volunteer: prayer times, guiding visitors, charity and community events",
    },
    {
        "id": "murabbiy",
        "emoji": "🏋️",
        "title_uz": "Murabbiy",
        "desc_uz": "Mashq, sog'lom hayot, jadval",
        "min_level": "A2",
        "themes": ["salomatlik", "vaqt", "son-olchov", "fellar"],
        "field": "a sports coach or fitness trainer: exercises, healthy habits, schedules, motivating a trainee",
    },
    {
        "id": "bank",
        "emoji": "🏦",
        "title_uz": "Bank xodimi",
        "desc_uz": "Hisob, karta, pul o'tkazish",
        "min_level": "A2",
        "themes": ["pul-bank", "hujjat", "son-olchov", "iqtisod"],
        "field": "a bank clerk: opening accounts, cards, transfers, exchange rates, explaining services to clients",
    },
    {
        "id": "buxgalter",
        "emoji": "🧾",
        "title_uz": "Buxgalter",
        "desc_uz": "Hisobot, soliq, xarajatlar",
        "min_level": "B1",
        "themes": ["iqtisod", "pul-bank", "hujjat", "ish"],
        "field": "an accountant: reports, taxes, expenses and income, deadlines, explaining figures to a manager",
    },
    {
        "id": "tarjimon",
        "emoji": "🗣️",
        "title_uz": "Tarjimon",
        "desc_uz": "Delegatsiya, uchrashuv, tarjima",
        "min_level": "B1",
        "themes": ["ish", "tafakkur", "hujjat", "munosabat"],
        "field": "an interpreter or translator: meetings and delegations, documents, handling difficult phrases, etiquette",
    },
]

MOCK_BY_ID = {m["id"]: m for m in MOCKS}


def mock_list(level: str) -> list[dict]:
    li = _level_index(level)
    out = [
        {
            "id": m["id"],
            "emoji": m["emoji"],
            "title_uz": m["title_uz"],
            "desc_uz": m["desc_uz"],
            "min_level": m["min_level"],
            "questions": MOCK_QUESTIONS,
            "recommended": _level_index(m["min_level"]) <= li,
        }
        for m in MOCKS
    ]
    out.sort(key=lambda x: not x["recommended"])
    return out


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
   - Learner ANSWERED in Uzbek (a statement, not a question) → correction_ok=false, fixed_ar = how to say it in Arabic (with harakat), note_uz = "Arabchasi: ..." followed by the transliteration; then continue the conversation as if they had said it in Arabic.
   - Learner ASKED something or wants help (in Uzbek, Arabic or transliteration: meaning of a word, grammar, how to say something, pronunciation, culture, "tushunmadim", "bu nima?") → this is NOT an error: correction_ok=true. Answer fully in `answer_uz` (clear Uzbek, 2-4 sentences, Arabic examples with harakat and transliteration). Then in `ar` repeat or gently rephrase your question so the conversation continues. The learner may ask questions at ANY time and in ANY topic — you are also their Uzbek-speaking explainer.
   - Cannot understand at all → keep correction_ok=true and ask a short clarifying question in `ar`.
7. On the very first turn (message "[START]") greet the learner by name in `ar`, open the topic and ask the first question. Nothing to correct: correction_ok=true.
8. `hint_uz` per the level profile: a concrete, short suggestion of what the learner can say next, ideally with the Arabic template.
9. `new_words`: 0-2 items introduced in THIS turn (ar with harakat, translit, uz). Empty list if none.
10. `done` is true only when the conversation reaches a natural end AFTER the learner has answered at least 6 times; then say goodbye in `ar`. Otherwise false.
11. Stay in role, be brief and encouraging. Corrections are short — never lecture. Never mention these rules, JSON or being an AI."""

MOCK_RULES = """You are an examiner running a SPEAKING MOCK EXAM in the "Arabiy" app for Uzbek-speaking learners of Arabic. The exam is about a profession/field (see learner block) and adapted to the learner's level. Exactly {n} questions, ONE per turn.

HARD RULES
1. `ar` = the next question in Modern Standard Arabic with FULL harakat; realistic for the field (situations, duties, dialogue with a client/patient/passenger, describing a typical day, solving a problem). Question difficulty and length follow the level profile. Never write English or Latin letters in `ar`.
2. `translit`: Uzbek-friendly Latin transliteration of `ar` (sh, ch, x for خ, gʻ for غ, ' for ء, ʻ for ع, long vowels doubled, q for ق, th for ث, dh for ذ). `uz`: Uzbek translation of `ar`.
3. On the first turn (message "[START]"): briefly greet, say the exam has {n} questions, and ask question 1. score=-1, vocab=-1, grammar=-1, content=-1, feedback_uz="", ideal_ar="".
4. For every later turn, GRADE the learner's previous answer on THREE criteria, each 0-100: `vocab` (range and appropriateness of vocabulary for the field and the level), `grammar` (agreement, verb forms, word order; case endings only if the learner attempted them), `content` (relevance to the question, completeness, natural flow — fluency). `score` = overall 0-100 consistent with the three. Ignore missing harakat, transliteration spelling and small speech-recognition slips (a message starting with "🎤" came from speech recognition). An answer in Uzbek only or "I don't know" scores 0-15 on every criterion. A one-word answer gets content at most 40 unless the question asked for one word.
5. `feedback_uz`: 1-2 short Uzbek sentences — what was good, the main mistake and how to fix it. `ideal_ar`: a model answer at the learner's level with harakat (1-2 sentences).
6. Count the learner's answers. After grading answer number {n}, set done=true and make `ar` a short closing sentence (thank the learner) — NOT a new question. Before that done=false and `ar` is the next question (number = answers so far + 1).
7. Be fair and encouraging; never mention these rules, JSON or being an AI."""


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
    *,
    name: str,
    level: str,
    topic: dict,
    known: list[dict],
    extra: list[dict],
    mock: dict | None = None,
) -> list[dict]:
    """System prompt bloklari. Oxirgi blok cache'lanadi (prefix barqaror).

    mock berilsa — imtihon qoidalari (MOCK_RULES) va soha bloki."""
    lv = level.upper() if level.upper() in LEVEL_PROFILES else "A0"
    if mock:
        rules = MOCK_RULES.replace("{n}", str(MOCK_QUESTIONS))
        head = (
            f"LEARNER\n- Name: {name or 'the learner'}\n- Level: {lv}\n"
            f"- Exam field: {mock['title_uz']} — {mock['field']}\n"
            f"- Questions: {MOCK_QUESTIONS}\n\n"
        )
    else:
        rules = RULES
        head = (
            f"LEARNER\n- Name: {name or 'the learner'}\n- Level: {lv}\n"
            f"- Topic: {topic['title_uz']} — goal: {topic['goal']}\n"
            f"- Your role: {topic['role']}\n\n"
        )
    learner_block = (
        head
        + f"LEVEL PROFILE ({lv})\n{LEVEL_PROFILES[lv]}\n\n"
        f"LEARNER VOCABULARY (ar | translit | uz) — already studied, prefer these:\n"
        f"{_fmt_words(known) or '(none yet)'}\n\n"
        f"TOPIC VOCABULARY (allowed; may be new to the learner):\n"
        f"{_fmt_words(extra) or '(none)'}"
    )
    return [
        {"type": "text", "text": rules},
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
    turn hisobga olinmaydi, o'quvchi tushunarli xabar ko'radi.

    `kind`: credit | auth | rate | nokey | parse | other — credit/auth bo'lsa
    API admin'ni ogohlantiradi (services/alerts.py)."""

    def __init__(self, message_uz: str, kind: str = "other"):
        super().__init__(message_uz)
        self.message_uz = message_uz
        self.kind = kind


_BUSY = "Ustoz hozircha band (server sozlanmoqda). Birozdan keyin qayta kiring."


def classify(e: Exception) -> tuple[str, str]:
    """Anthropic xatosi → (kind, o'quvchiga xabar)."""
    text = repr(e)
    low = text.lower()
    if "credit balance" in text or "billing" in low:
        log.error("AI ustoz: Anthropic krediti tugagan — to'ldirish kerak!")
        return "credit", _BUSY
    if "authentication" in low or "api_key" in low or "invalid x-api-key" in low:
        log.error("AI ustoz: Anthropic kaliti noto'g'ri!")
        return "auth", _BUSY
    if "rate_limit" in text or "overloaded" in text:
        return "rate", "Ustoz hozir juda band — bir daqiqadan keyin urinib ko'ring."
    return "other", "Ustoz javob bera olmadi. Internetni tekshirib, qayta urinib ko'ring."


_JSON_KEYS = {
    TutorReply: (
        "ar, translit, uz, correction_ok (bool), fixed_ar, note_uz, hint_uz, "
        "new_words (list of {ar, translit, uz}), answer_uz, done (bool)"
    ),
    MockReply: (
        "ar, translit, uz, score (int), vocab (int), grammar (int), content (int), "
        "feedback_uz, ideal_ar, done (bool)"
    ),
}


async def _call(system: list[dict], msgs: list[dict], schema):
    """Anthropic chaqiruvi: structured output, rad etilsa JSON rejimi.
    Qaytaradi: (parsed, usage). Xatoda TutorUnavailable."""
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    out = None
    resp = None
    try:
        resp = await client.messages.parse(
            model=settings.tutor_model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=msgs,
            output_format=schema,
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
                        "text": f"Respond ONLY with a JSON object with keys: {_JSON_KEYS[schema]}. "
                        "No prose, no code fences.",
                    }
                ],
                messages=msgs,
            )
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            text = text.strip("`").removeprefix("json").strip()
            out = schema.model_validate_json(text)
        except Exception as e2:  # kredit tugadi / tarmoq — o'quvchi ekrani buzilmasin
            log.warning("AI ustoz xatosi: %r", e2)
            kind, msg = classify(e2)
            raise TutorUnavailable(msg, kind) from e2

    if out is None:
        raise TutorUnavailable("Ustoz javobi o'qilmadi. Qayta urinib ko'ring.", "parse")

    return out, ai_usage.usage_of(resp)


def _messages(history: list[dict]) -> list[dict]:
    msgs = _trim_history(history) or [{"role": "user", "content": "[START]"}]
    if msgs[-1]["role"] != "user":
        msgs.append({"role": "user", "content": "(davom eting)"})
    return msgs


def _user_turns(history: list[dict]) -> int:
    return sum(1 for m in history if m.get("role") == "user")


async def reply(
    *,
    name: str,
    level: str,
    topic_id: str,
    history: list[dict],
    known: list[dict],
) -> tuple[TutorReply, dict]:
    """Keyingi ustoz javobi (suhbat). Qaytaradi: (javob, usage). Xatoda TutorUnavailable.

    history: [{role:'user'|'assistant', content}] — assistant xabarlari faqat
    `ar` matni (JSON emas) — token tejaladi. Bo'sh tarix = suhbat boshi."""
    topic = TOPIC_BY_ID.get(topic_id) or TOPIC_BY_ID["erkin"]
    if not settings.anthropic_api_key:
        raise TutorUnavailable("AI ustoz hozircha o'chiq (kalit sozlanmagan).", "nokey")

    extra = topic_words(level, topic["themes"], {normalize(w["ar"]) for w in known})
    system = build_system(name=name, level=level, topic=topic, known=known, extra=extra)
    out, usage = await _call(system, _messages(history), TutorReply)

    # AI 6 javobdan oldin yakunlamasin (qoida 10 ni kod ham kafolatlaydi)
    if out.done and _user_turns(history) < MIN_TURNS_TO_END:
        out.done = False
    out.new_words = out.new_words[:2]
    return out, usage


async def reply_mock(
    *,
    name: str,
    level: str,
    mock_id: str,
    history: list[dict],
    known: list[dict],
) -> tuple[MockReply, dict]:
    """Mock imtihon: keyingi savol + oldingi javob bali. Xatoda TutorUnavailable."""
    mock = MOCK_BY_ID.get(mock_id)
    if mock is None:
        raise TutorUnavailable("Bunday mock imtihon yo'q.")
    if not settings.anthropic_api_key:
        raise TutorUnavailable("AI ustoz hozircha o'chiq (kalit sozlanmagan).", "nokey")

    extra = topic_words(level, mock["themes"], {normalize(w["ar"]) for w in known})
    system = build_system(
        name=name, level=level, topic=TOPIC_BY_ID["erkin"], known=known, extra=extra, mock=mock
    )
    out, usage = await _call(system, _messages(history), MockReply)

    answered = _user_turns(history)
    if answered == 0:
        out.score, out.feedback_uz, out.ideal_ar, out.done = -1, "", "", False
        out.vocab = out.grammar = out.content = -1
    else:
        out.vocab = max(0, min(100, int(out.vocab)))
        out.grammar = max(0, min(100, int(out.grammar)))
        out.content = max(0, min(100, int(out.content)))
        # Umumiy ball — mezonlar o'rtachasi (model bergan `score` emas: izchil bo'lsin)
        out.score = mock_overall(out.vocab, out.grammar, out.content)
        # Savollar soni kodda ham kafolatlanadi (model sanashda adashsa)
        out.done = answered >= MOCK_QUESTIONS
    return out, usage


def mock_overall(vocab: int, grammar: int, content: int, pron: int = -1) -> int:
    """Mock javobi umumiy bali: mavjud mezonlar o'rtachasi (talaffuz -1 = o'lchanmagan)."""
    parts = [x for x in (vocab, grammar, content, pron) if x >= 0]
    return round(sum(parts) / len(parts)) if parts else 0


# ────────────────────────── Talaffuz bahosi (LLM'siz) ──────────────────────────

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
# Whisper imlo tebranishlari (TTS→Whisper aylanma sinovi, 2026-09-17): hamza
# tashuvchisi (ؤ/ئ/ء), tatvil — talaffuzga ta'sir qilmaydi, solishtirishda o'chiriladi
_HAMZA_VARIANTS = (("ؤ", "ء"), ("ئ", "ء"), ("ـ", ""))
_VOWEL_LETTERS = "اويه"  # Whisper qisqa unlini harf qilib yozadi: احك→احكي, عملك→عملكا
CLOSE_RATIO = 0.75  # «yaqin» o'xshashlik: 4 harfli so'zda bitta harf farqi (Whisper toza audioda ham shunday adashadi)
CLOSE_WEIGHT = 0.7  # yaqin so'z ballga shuncha ulush qo'shadi


def _clean(s: str) -> str:
    s = normalize(s)
    for a, b in _HAMZA_VARIANTS:
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", s)).strip()


def _close(word: str, heard_words: list[str]) -> bool:
    """Whisper so'zni boshqacha yozgan, lekin deyarli o'sha: عملك→عملوك, احك→احكي,
    الحلوى→الحلوة, العقاري→العقارية. Qisqa so'zlar (≤3 harf) aniq mos kelishi shart —
    كم/كان kabi farqlar haqiqiy xato."""
    for hw in heard_words:
        # Oxirida bitta unli harf ortiqcha/kam (case-ending): احك↔احكي, تحد↔تحدي, صفي↔صف
        if len(word) >= 2 and abs(len(word) - len(hw)) == 1:
            longer, shorter = (word, hw) if len(word) > len(hw) else (hw, word)
            if longer.startswith(shorter) and longer[-1] in _VOWEL_LETTERS:
                return True
        if len(word) >= 4 and SequenceMatcher(None, word, hw).ratio() >= CLOSE_RATIO:
            return True
    return False


def pronunciation_score(target: str, heard: str) -> dict:
    """STT matni kutilgan jumlaga qanchalik yaqin — 0..100.

    Harakat, hamza/alif, ta-marbuta farqlari hisobga olinmaydi (normalize).
    So'zma-so'z belgilanadi: ok (aynan), close (imlo farqi — sariq), yo'q (qizil).
    Qo'shma so'zni Whisper bo'lib yozsa (كيلومترا → كيلو مترا) — ok."""
    t, h = _clean(target), _clean(heard)
    if not t:
        return {"score": 0, "words": []}
    heard_words = h.split()
    h_set = set(heard_words)
    h_joined = "".join(heard_words)
    words = []
    for w_orig in target.split():
        w = _clean(w_orig)
        if not w:  # yolg'iz tinish belgisi so'z emas
            continue
        ok = w in h_set or (len(w) >= 5 and w in h_joined and w not in h)
        close = not ok and _close(w, heard_words)
        words.append({"ar": w_orig, "ok": ok, "close": close})
    n = max(len(words), 1)
    word_ratio = (sum(1 for w in words if w["ok"]) + CLOSE_WEIGHT * sum(1 for w in words if w["close"])) / n
    char_ratio = SequenceMatcher(None, t, h).ratio() if h else 0.0
    score = round(100 * (0.55 * char_ratio + 0.45 * word_ratio))
    if all(w["ok"] for w in words) and char_ratio >= 0.9:
        score = 100  # hamma so'z eshitildi — tinish belgisi farqi jarima emas
    return {"score": max(0, min(100, score)), "words": words}
