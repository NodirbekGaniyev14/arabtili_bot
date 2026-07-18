"""AI dars-generatori — spec §13 prompti bilan Claude orqali dars yaratadi.

Bu BUILD-VAQT pipeline (scripts/generate_lesson.py chaqiradi) — runtime emas.
Natija: content/modules/{level}/{id}.json + avtomatik validatsiya.
"""

import json

from anthropic import AsyncAnthropic
from pydantic import ValidationError

from config import settings
from services.curriculum import (
    lesson_file,
    lesson_order,
    load_curriculum,
    load_lesson_v2,
)
from services.lesson_schema import LessonV2, validate_lesson

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """SEN: Arab tili metodisti. O'zbek tilida so'zlashuvchilar uchun dars yaratasan.

KONTEKST:
- O'quvchi: o'zbek tilida so'zlashuvchi, {level} darajada
- Maqsad: Saudiya safari (umra/haj/ish) + rasmiy arab tili (فصحى)
- Bu {order}-dars ({lesson_id}), mavzu: {topic}
- Dars sarlavhasi (can-do uslubida): {title_uz}
- Qo'shimcha eslatma: {note}
- Allaqachon o'rganilgan mavzular: {previous_topics}
- Hali BILMAYDI (keyingi darslar): {not_yet_taught}

QAT'IY QOIDALAR:
1. Faqat o'quvchi allaqachon bilgan grammatikani ishlat. Kelajakdagi mavzuni ISHLATMA.
2. harakat_level="{harakat_level}" — shunga mos harakat qo'y. "full" bo'lsa HAR BIR arabcha so'zning HAR BIR undoshiga harakat (fatha/kasra/damma/sukun) qo'y — hatto keng tarqalgan so'zlarda ham. MASALAN: "باب" EMAS → "بَاب"; "ماء" EMAS → "مَاء"; "ساعة" EMAS → "سَاعَة"; "بيت" EMAS → "بَيْت". Harakatsiz bitta so'z ham dars validatsiyadan o'tmaydi.
3. Har bir yangi so'zning O'ZAGINI ko'rsat (root maydoni, "ك ت ب" formatida, bo'shliq bilan).
4. So'zning o'zbekcha o'zlashma varianti bo'lsa (kitob, maktab, ilm...) — uni uz maydonida yoki hook'da MAJBURIY eslat.
5. Tushuntirish tili: o'zbek (lotin alifbosi). Arabcha faqat misollarda.
6. Grammatikani "qoida" emas, "nima qila olaman" sifatida ber.
7. Diniy kontentda aniq va hurmatli bo'l. Oyat keltirilsa — sura va oyat raqami.
8. Lug'at: {words_target} ta atrofida yangi so'z (±2). 70% yuqori chastotali so'zlar.
9. hejazi maydoni: {hejazi_rule}
10. micro_test: 5-7 savol, kamida 3 xil tur. mcq'da answer — options ichidagi MATN (indeks emas).
11. audio maydonlari: "{audio_prefix}/<lotin-nom>.mp3" formatida yoz (masalan "{audio_prefix}/bayt.mp3").
12. skills.speaking.eval="self_check", skills.writing.eval="ai_grammar".
13. srs_cards: har yangi so'z uchun word karta; darsda o'zak bo'lsa root karta; vazn bo'lsa pattern karta.
14. id="{lesson_id}", level="{level}", module="{module}", order={order}, prerequisites={prerequisites} — aynan shu qiymatlar.

Dars tuzilmasi to'liq bo'lsin: hook_uz (qiziqtiruvchi 1-2 jumla, o'zbekcha o'zlashma ko'prigi bilan),
grammar (jadval + keng tarqalgan xatolar), roots (kamida 1 o'zak, agar mavzuga mos bo'lsa),
vocabulary, skills (4 ko'nikma — o'qish matni o'rganilgan so'zlardan, 2-5 gap), micro_test, srs_cards."""


def _topics_before(lesson_id: str, limit: int = 30) -> list[str]:
    order = lesson_order()
    idx = order.index(lesson_id)
    cur = load_curriculum()
    prev = order[max(0, idx - limit): idx]
    return [f"{cur[i]['title_uz']} ({cur[i]['topic']})" for i in prev]


def _topics_after(lesson_id: str, limit: int = 8) -> list[str]:
    order = lesson_order()
    idx = order.index(lesson_id)
    cur = load_curriculum()
    nxt = order[idx + 1: idx + 1 + limit]
    return [cur[i]["topic"] for i in nxt]


def build_prompt(lesson_id: str) -> str:
    meta = load_curriculum()[lesson_id]
    level_dir = lesson_id.split("-")[0]
    hejazi_rule = (
        "bu funksional dars — 2-4 ta MSA↔Hijoziy juftlik qo'sh (deck=hejazi srs kartalari bilan)"
        if meta.get("hejazi")
        else "bo'sh ro'yxat qoldir (bu dars uchun hijoziy blok yo'q)"
    )
    return SYSTEM_PROMPT.format(
        level=meta["level"],
        order=meta["order"],
        lesson_id=lesson_id,
        topic=meta["topic"],
        title_uz=meta["title_uz"],
        note=meta.get("note") or "—",
        previous_topics="; ".join(_topics_before(lesson_id)) or "hech narsa (birinchi dars)",
        not_yet_taught="; ".join(_topics_after(lesson_id)),
        harakat_level=meta["harakat_level"],
        words_target=(
            meta["words_target"]
            if meta.get("words_target")
            else "0 (yangi so'z SHART EMAS — bu talaffuz/mashq darsi, ko'pi bilan 2-3 misol so'z)"
        ),
        hejazi_rule=hejazi_rule,
        audio_prefix=level_dir,
        module=meta["module"],
        prerequisites=json.dumps(meta.get("prerequisites", [])),
    )


def _extract_json(text: str) -> str:
    """Model javobidan JSON obyektni ajratib oladi (```fence yoki xom matn)."""
    text = text.strip()
    if "```" in text:
        # ```json ... ``` yoki ``` ... ``` ichidan
        parts = text.split("```")
        for part in parts:
            p = part.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{"):
                text = p
                break
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return text
    return text[start : end + 1]


# Model javobini yo'naltirish uchun sxema (strict grammar emas — matnli ko'rsatma)
_SCHEMA_HINT = json.dumps(LessonV2.model_json_schema(), ensure_ascii=False)


async def generate_lesson(
    lesson_id: str, save: bool = True
) -> tuple[dict | None, list[str], list[str]]:
    """Darsni generatsiya qiladi. Qaytaradi: (dars, errors, warnings).

    Eslatma: strict `output_format` (messages.parse) SXEMA JUDA KATTA bo'lgani
    uchun "compiled grammar too large" xatosini beradi. Shu sabab oddiy
    messages.create + JSON parse ishlatamiz; validatsiya lokal (bepul) qoladi.
    """
    meta = load_curriculum().get(lesson_id)
    if not meta:
        return None, [f"curriculum'da yo'q: {lesson_id}"], []
    if meta["type"] == "exam":
        return None, ["Imtihon darslari alohida pipeline'da (K3)"], []

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    user_msg = (
        f"{lesson_id} darsini to'liq yarat.\n\n"
        f"JAVOB FORMATI: FAQAT bitta JSON obyekt qaytar (izohsiz, markdown "
        f"belgisisiz). U quyidagi JSON Schema'ga to'liq mos bo'lsin:\n\n"
        f"{_SCHEMA_HINT}"
    )

    response = await client.messages.create(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=build_prompt(lesson_id),
        messages=[{"role": "user", "content": user_msg}],
    )

    text = "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()
    if not text:
        return None, ["AI matnli javob qaytarmadi (bo'sh)"], []

    try:
        raw = json.loads(_extract_json(text))
    except json.JSONDecodeError as e:
        return None, [f"JSON parse xatosi: {e}"], []

    try:
        lesson = LessonV2.model_validate(raw)
    except ValidationError as e:
        msgs = [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()[:8]]
        return None, ["Sxemaga mos emas:"] + msgs, []

    data = lesson.model_dump()
    errors, warnings = validate_lesson(
        data, meta=meta, known_lesson_ids=set(lesson_order())
    )

    if save and not errors:
        f = lesson_file(lesson_id)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    return data, errors, warnings


def review_sheet(lesson_id: str) -> str:
    """Arab tili o'qituvchisi uchun tekshiruv varag'i (Markdown)."""
    data = load_lesson_v2(lesson_id)
    if not data:
        return f"{lesson_id}: fayl topilmadi"
    lines = [
        f"# Tekshiruv varag'i — {lesson_id}: {data['title_uz']}",
        f"**Can-do:** {data['can_do_uz']}",
        f"**Harakat darajasi:** {data['harakat_level']}",
        "",
        "## Lug'at (harakat va tarjima to'g'riligini tekshiring)",
        "| Arabcha | Translit | O'zbekcha | O'zak | Vazn | ✓/✗ |",
        "|---|---|---|---|---|---|",
    ]
    for v in data.get("vocabulary", []):
        lines.append(
            f"| {v['ar']} | {v['translit']} | {v['uz']} | {v.get('root','')} | {v.get('pattern','')} | |"
        )
    g = data.get("grammar") or {}
    if g.get("point_ar"):
        lines += ["", "## Grammatika", f"**Nuqta:** {g['point_ar']}", g.get("explanation_uz", "")]
        for row in g.get("table", []):
            lines.append(f"- {row['ar']} — {row['uz']}")
    lines += ["", "## Mikro-test javoblari"]
    for i, t in enumerate(data.get("micro_test", []), 1):
        lines.append(f"{i}. [{t['type']}] {t.get('q_uz') or t.get('q_ar','')} → **{t.get('answer','')}**")
    lines += ["", "_Izohlar uchun joy:_", "", "---"]
    return "\n".join(lines)
