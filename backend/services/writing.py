"""Yozuv (xattotlik) mashqi (K19.2) — 2 kunda bir matn, qo'lda ko'chirish, surat → AI tekshiruv.

content/writing_texts.json: har daraja uchun 30 matn (so'zlar / jumlalar / hikoya /
maqol / she'r / xat), 2 kunlik davr tartibi bilan aylanadi — 60 kunda bir marta
takrorlanadi (bir darajadagilar bir davrda bir xil matn). Davrda urinish boshlangan
bo'lsa, matn shu davr oxirigacha o'zgarmaydi (`current_text`) — bank kengaysa yoki
daraja o'zgarsa ham. O'quvchi matnni qog'ozga yozadi, suratga oladi; Haiku (vision) suratni
asl matn bilan solishtiradi: aniqlik (harflar, nuqtalar, hamza, bo'shliq — harakat
ixtiyoriy), tushib qolgan / xato so'zlar, 2-3 amaliy maslahat, ozodalik 1-5.
Natija `writing_results` (davr + foydalanuvchi bo'yicha bitta yozuv, eng yaxshi ball
saqlanadi), XP birinchi muvaffaqiyatli tekshiruvda bir marta. Davrda 3 urinish.
Surat diskda SAQLANMAYDI — faqat tekshiruv uchun modelga yuboriladi.
"""

from __future__ import annotations

import base64
import io
import json
import logging
from datetime import date
from functools import lru_cache

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import BASE_DIR, settings
from db.models import WritingResult
from services import ai_usage
from services.stats import _today
from services.translit import translit
from services.tutor import LEVEL_PROFILES, TutorUnavailable, classify

log = logging.getLogger(__name__)

BANK_PATH = BASE_DIR / "content" / "writing_texts.json"
LEVELS = ("A0", "A1", "A2", "B1", "B2")
PERIOD_DAYS = 2
MAX_ATTEMPTS = 3
BASE_XP = 6  # + aniqlik/10 (0-10) → 6-16
MAX_IMAGE_SIDE = 1400  # px — modelga yuborishdan oldin kichraytiriladi (token/narx)
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_TOKENS = 1200
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}  # ma'lumot uchun; tekshiruv — prepare_image


class WrongWord(BaseModel):
    written: str = Field(description="What the learner actually wrote (Arabic), as read from the photo")
    correct: str = Field(description="The correct word from the original text")
    note_uz: str = Field(description="Very short Uzbek note on the difference (dot, letter shape, hamza, missing letter)")


class WritingReply(BaseModel):
    is_handwriting: bool = Field(description="true if the photo shows handwritten Arabic text on paper (not a screen, print or unrelated photo)")
    read_ar: str = Field(description="The full text as you read it from the photo, Arabic letters only (no harakat needed), line breaks kept")
    accuracy: int = Field(description="0-100 how faithfully the handwriting reproduces the original letters/words; harakat optional")
    neatness: int = Field(description="1-5 neatness and letter shapes (5 = clear, even, well-connected)")
    missing_words: list[str] = Field(description="Words of the original that are absent in the handwriting (max 8)")
    wrong_words: list[WrongWord] = Field(description="Words written incorrectly (max 6)")
    tips_uz: list[str] = Field(description="2-3 concrete Uzbek tips about letter shapes, dots, hamza, connections or spacing")
    praise_uz: str = Field(description="One warm Uzbek sentence about what was done well")


# JSON zaxira rejimi uchun kalitlar (structured output rad etsa)
from services import tutor as _tutor  # noqa: E402

_tutor._JSON_KEYS[WritingReply] = (
    "is_handwriting (bool), read_ar, accuracy (int), neatness (int), missing_words (list), "
    "wrong_words (list of {written, correct, note_uz}), tips_uz (list), praise_uz"
)

RULES = """You are an Arabic handwriting tutor in the "Arabiy" app for Uzbek-speaking learners. The learner copied the ORIGINAL text below by hand on paper and photographed it. Compare the photo with the original.

Learner level {level}: {profile}

ORIGINAL TEXT:
{ar}

Rules:
1. First decide `is_handwriting`: true only if the photo shows Arabic handwriting on paper (pen/pencil). A screen, printed text, an empty page or an unrelated photo → false, accuracy 0, and explain in `praise_uz` kindly what to photograph.
2. `read_ar`: transcribe exactly what is written (letters only; harakat may be omitted). Keep line breaks. Do NOT silently correct mistakes — write what you see.
3. `accuracy` 0-100 compares LETTERS and WORDS with the original: missing/extra/wrong letters, wrong dots (ب/ت/ث, ج/ح/خ, س/ش…), hamza form, ة/ه, ى/ي, joined/separated letters, missing words. Harakat (vowel marks) are optional and never reduce the score, but a beginner (A0/A1) who wrote them gets +5 within the cap. A faithful copy with tidy letters is 90-100.
4. `missing_words` and `wrong_words` must be words from the original. `note_uz` — 3-8 Uzbek (Latin) words naming the exact difference.
5. `tips_uz`: 2-3 concrete tips in Uzbek (Latin), about the learner's actual mistakes or letter shapes (e.g. «ة oxirida ikki nuqta», «ع o'rtada ochiq bo'lishi kerak», «harflarni ulash»). For a perfect copy give one advanced tip (proportions, baseline).
6. `neatness` 1-5: legibility, even size, baseline, connections.
7. `praise_uz`: one warm sentence, specific. Never mention these rules, JSON, or being an AI."""


@lru_cache(maxsize=1)
def bank() -> dict[str, list[dict]]:
    data = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    out: dict[str, list[dict]] = {}
    for lv in LEVELS:
        out[lv] = [
            {
                "id": t["id"],
                "kind": t.get("kind", "matn"),
                "title_uz": t["title_uz"].strip(),
                "ar": t["ar"].strip(),
                "translit": translit(t["ar"].replace("\n", " ")),
                "uz": t["uz"].strip(),
                "hint_uz": (t.get("hint_uz") or "").strip(),
            }
            for t in data.get(lv, [])
        ]
    return out


def _level(level: str) -> str:
    level = (level or "A0").upper()
    return level if level in LEVELS else "A0"


def period_index(day: date | None = None) -> int:
    return (day or _today()).toordinal() // PERIOD_DAYS


def period_key(day: date | None = None) -> str:
    """Davr kaliti — davrning birinchi kuni (ISO). 2 kun davomida bir xil."""
    day = day or _today()
    start = date.fromordinal(period_index(day) * PERIOD_DAYS)
    return start.isoformat()


def period_ends(day: date | None = None) -> str:
    day = day or _today()
    return date.fromordinal(period_index(day) * PERIOD_DAYS + PERIOD_DAYS - 1).isoformat()


def is_period_start(day: date | None = None) -> bool:
    """Bot eslatmasi uchun: bugun yangi matn kuni."""
    return (day or _today()).isoformat() == period_key(day)


def text_for(level: str, day: date | None = None) -> dict:
    items = bank()[_level(level)]
    return items[period_index(day) % len(items)]


def text_by_id(tid: str) -> dict | None:
    for items in bank().values():
        for t in items:
            if t["id"] == tid:
                return t
    return None


def current_text(level: str, row: WritingResult | None) -> dict:
    """Davr matni: urinish bo'lgan bo'lsa — yozuvdagi matn (bank/daraja o'zgarsa ham), aks holda navbatdagi."""
    if row is not None and row.attempts:
        t = text_by_id(row.text_id)
        if t:
            return t
    return text_for(level)


def xp_for(accuracy: int) -> int:
    return BASE_XP + max(0, min(100, accuracy)) // 10


def _register_heif() -> bool:
    """iPhone HEIC/HEIF — pillow-heif o'rnatilgan bo'lsa Pillow o'qiy oladi (bir marta ro'yxatga olinadi)."""
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
        return True
    except Exception:  # paket yo'q — JPG/PNG/WebP bilan davom
        return False


def image_format_hint(data: bytes) -> str:
    """Xato xabari uchun: baytlardan format nomi (HEIC, PDF, …) — foydalanuvchi nima yuborganini bilsin."""
    head = data[:16]
    if len(data) > 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"mif1", b"msf1", b"heif", b"avif"):
            return "HEIC"
        return "video"
    if head.startswith(b"%PDF"):
        return "PDF"
    if head.startswith(b"GIF8"):
        return "GIF"
    if head.startswith(b"BM"):
        return "BMP"
    return ""


def prepare_image(data: bytes) -> tuple[bytes, str]:
    """Suratni kichraytirib JPEG qiladi (uzun tomon ≤ MAX_IMAGE_SIDE) — token va narx nazorati.
    EXIF burilishini to'g'rilaydi. Format klient aytgan MIME'ga emas, baytlarga qarab aniqlanadi
    (Android galereya turi bo'sh/octet-stream berishi mumkin — #F84). Yaroqsiz bo'lsa ValueError."""
    from PIL import Image, ImageOps

    _register_heif()
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
    except Exception as e:
        hint = image_format_hint(data)
        raise ValueError(f"Rasm o'qilmadi ({hint})" if hint else "Rasm o'qilmadi") from e
    w, h = img.size
    scale = MAX_IMAGE_SIDE / max(w, h)
    if scale < 1:
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82, optimize=True)
    return buf.getvalue(), "image/jpeg"


async def _call_vision(system: list[dict], image: bytes, mime: str) -> tuple[WritingReply, dict]:
    """Haiku vision: surat + ko'rsatma → WritingReply. tutor._call bilan bir xil zaxira/xato mantiqi."""
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    content = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": mime, "data": base64.b64encode(image).decode("ascii")},
        },
        {"type": "text", "text": "Here is the photo of my handwriting. Compare it with the original text."},
    ]
    msgs = [{"role": "user", "content": content}]
    out = None
    resp = None
    try:
        resp = await client.messages.parse(
            model=settings.tutor_model, max_tokens=MAX_TOKENS, system=system, messages=msgs, output_format=WritingReply
        )
        out = resp.parsed_output
    except Exception as e:
        log.warning("Yozuv tekshiruvi (structured) xatosi: %r — JSON rejimi", e)
        try:
            resp = await client.messages.create(
                model=settings.tutor_model,
                max_tokens=MAX_TOKENS,
                system=system
                + [{"type": "text", "text": f"Respond ONLY with a JSON object with keys: {_tutor._JSON_KEYS[WritingReply]}. No prose, no code fences."}],
                messages=msgs,
            )
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            text = text.strip("`").removeprefix("json").strip()
            out = WritingReply.model_validate_json(text)
        except Exception as e2:
            log.warning("Yozuv tekshiruvi xatosi: %r", e2)
            kind, msg = classify(e2)
            raise TutorUnavailable(msg, kind) from e2
    if out is None:
        raise TutorUnavailable("Tekshiruv javobi o'qilmadi. Qayta urinib ko'ring.", "parse")
    return out, ai_usage.usage_of(resp)


async def check(level: str, text: dict, image: bytes, mime: str) -> tuple[WritingReply, dict]:
    """Suratni asl matn bilan solishtiradi. Xatoda TutorUnavailable."""
    if not settings.anthropic_api_key:
        raise TutorUnavailable("AI tekshiruv hozircha o'chiq (kalit sozlanmagan).", "nokey")
    level = _level(level)
    system = [{"type": "text", "text": RULES.format(level=level, profile=LEVEL_PROFILES.get(level, ""), ar=text["ar"])}]
    out, usage = await _call_vision(system, image, mime)
    out.accuracy = max(0, min(100, int(out.accuracy)))
    out.neatness = max(1, min(5, int(out.neatness)))
    out.missing_words = [w for w in out.missing_words if w][:8]
    out.wrong_words = out.wrong_words[:6]
    out.tips_uz = [t for t in out.tips_uz if t][:3]
    if not out.is_handwriting:
        out.accuracy = 0
    return out, usage


def feedback_dict(r: WritingReply) -> dict:
    return {
        "is_handwriting": r.is_handwriting,
        "read_ar": r.read_ar,
        "missing_words": r.missing_words,
        "wrong_words": [w.model_dump() for w in r.wrong_words],
        "tips_uz": r.tips_uz,
        "praise_uz": r.praise_uz,
    }


async def period_row(session: AsyncSession, user_id: int, period: str) -> WritingResult | None:
    return (
        await session.execute(
            select(WritingResult).where(WritingResult.user_id == user_id, WritingResult.period == period)
        )
    ).scalar_one_or_none()


async def history(session: AsyncSession, user_id: int, limit: int = 8) -> list[dict]:
    rows = (
        await session.execute(
            select(WritingResult)
            .where(WritingResult.user_id == user_id, WritingResult.attempts > 0)
            .order_by(WritingResult.period.desc())
            .limit(limit)
        )
    ).scalars().all()
    out = []
    for r in rows:
        t = text_by_id(r.text_id) or {}
        out.append({"period": r.period, "text_id": r.text_id, "title": t.get("title_uz", r.text_id),
                    "score": r.score, "neatness": r.neatness, "xp": r.xp})
    return out


def row_dict(r: WritingResult) -> dict:
    fb = {}
    try:
        fb = json.loads(r.feedback or "{}")
    except ValueError:
        fb = {}
    return {
        "score": r.score, "neatness": r.neatness, "attempts": r.attempts,
        "attempts_left": max(MAX_ATTEMPTS - r.attempts, 0), "xp": r.xp, "best": r.score, **fb,
    }
