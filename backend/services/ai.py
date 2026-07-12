"""Claude orqali shaxsiy o'quv reja generatsiyasi (structured output)."""

import json
from datetime import date, timedelta
from typing import Literal

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from config import settings

# Mavjud modullar — AI faqat shulardan tanlaydi (4-bosqichda kontent yoziladi)
MODULES = {
    "alphabet": "Alifbo (harflar, harakatlar, o'qish)",
    "greetings": "Salomlashish",
    "introduction": "Tanishish",
    "family": "Oila",
    "numbers": "Sonlar 1-10",
    "colors": "Ranglar va sifatlar",
    "home": "Uy va narsalar",
    "food": "Ovqat va ichimlik",
    "verbs": "Kunlik ishlar (fe'llar)",
}

XP_BY_MINUTES = {10: 20, 20: 30, 30: 50, 60: 80}
DURATION_DAYS = {"3oy": 90, "6oy": 180, "1yil": 365, "sekin": 540}


class DayTasks(BaseModel):
    day: int
    tasks: list[str]


class GeneratedPlan(BaseModel):
    level: Literal["A0", "A1", "A2", "B1"]
    level_reason: str
    target_level: Literal["A1", "A2", "B1", "B2"]
    target_date: str
    daily_xp_goal: int
    daily_minutes: int
    focus_areas: list[str]
    module_order: list[str]
    weekly_schedule: list[DayTasks]
    motivation: str


SYSTEM_PROMPT = f"""Sen "Arabiy" ilovasining o'quv metodisti va Jamal ismli do'stona tuya-maskotisan 🐪.
O'zbek tilida so'zlashuvchi foydalanuvchi arab tilini o'rganmoqchi. Uning anketa javoblari
va bilim testi natijalari asosida SHAXSIY o'quv reja tuzasan.

Qoidalar:
- level: testsiz "noldan boshlayman" degan bo'lsa doim A0. Test natijalariga qarab:
  harflarni yaxshi bilsa A1, so'z/jumlalarni tushunsa A2, faqat juda kuchli bo'lsa B1.
  Shubha bo'lsa PASTROQ darajani tanla (mustahkam poydevor muhim).
- level_reason: 1-2 jumla, o'zbekcha, samimiy — nima uchun shu daraja.
- target_date: bugungi sanaga muddatni qo'shib hisobla (YYYY-MM-DD formatda).
- daily_xp_goal: kunlik vaqtga mos: 10 daqiqa=20 XP, 20=30 XP, 30=50 XP, 60=80 XP.
- module_order: FAQAT quyidagi ID'lardan tuzilgan ro'yxat (7-9 ta modul, mantiqiy tartibda):
{json.dumps(MODULES, ensure_ascii=False, indent=2)}
  A0 daraja ALBATTA "alphabet" bilan boshlanadi. Harflarni allaqachon yaxshi biladiganlar
  uchun "alphabet"ni tashlab ketish mumkin. Foydalanuvchi maqsadiga mos modullarni oldinroq qo'y.
- weekly_schedule: 7 kunlik shablon (day: 1-7), har kunga 1-3 ta qisqa vazifa (o'zbekcha),
  foydalanuvchining kunlik vaqtiga sig'adigan hajmda. 7-kun yengil (faqat takror) bo'lsin.
- focus_areas: foydalanuvchi tanlagan yo'nalishlar + test ko'rsatgan zaif joylar (o'zbekcha, qisqa).
- motivation: Jamal nomidan 2-3 jumlalik iliq, shaxsiy xabar — foydalanuvchi ismini ishlat,
  maqsadiga bog'la. Ohang: do'stona, ruhlantiruvchi, ammo yolg'on va'dalarsiz."""


def _fallback_plan(answers: dict, test: dict) -> GeneratedPlan:
    """AI ishlamay qolsa — oddiy qoidaviy reja (onboarding hech qachon buzilmasin)."""
    minutes = int(answers.get("daily_minutes", 20))
    correct = int(test.get("correct", 0))
    total = int(test.get("total", 0))
    ratio = correct / total if total else 0.0

    if answers.get("self_level") == "zero" or total == 0:
        level = "A0"
    elif ratio < 0.5:
        level = "A0"
    elif ratio < 0.8:
        level = "A1"
    else:
        level = "A2"

    days = DURATION_DAYS.get(answers.get("duration", "6oy"), 180)
    modules = list(MODULES.keys())
    if level != "A0":
        modules = [m for m in modules if m != "alphabet"]

    name = answers.get("name", "do'stim")
    return GeneratedPlan(
        level=level,
        level_reason="Test natijalaringiz va javoblaringiz asosida boshlang'ich daraja belgilandi.",
        target_level="A2" if level == "A0" else "B1",
        target_date=(date.today() + timedelta(days=days)).isoformat(),
        daily_xp_goal=XP_BY_MINUTES.get(minutes, 30),
        daily_minutes=minutes,
        focus_areas=answers.get("focus", ["O'qish", "Lug'at boyligi"]),
        module_order=modules,
        weekly_schedule=[
            DayTasks(day=d, tasks=["Yangi dars", "5 ta so'z takrori"]) for d in range(1, 7)
        ]
        + [DayTasks(day=7, tasks=["Haftalik takror"])],
        motivation=f"{name}, ajoyib qaror qildingiz! Har kuni ozgina harakat — va arab tili siz uchun ochiladi. Men doim yoningizdaman! 🐪",
    )


async def generate_plan(answers: dict, test: dict) -> tuple[GeneratedPlan, bool]:
    """Rejani Claude bilan tuzadi. Qaytaradi: (reja, ai_ishladimi)."""
    if not settings.anthropic_api_key:
        return _fallback_plan(answers, test), False

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    user_payload = {
        "bugungi_sana": date.today().isoformat(),
        "anketa": answers,
        "test_natijalari": test,
    }

    try:
        response = await client.messages.parse(
            model="claude-opus-4-8",
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                }
            ],
            output_format=GeneratedPlan,
        )
        plan = response.parsed_output
        if plan is None:
            return _fallback_plan(answers, test), False

        # AI faqat mavjud modullarni tanlaganini kafolatlaymiz
        plan.module_order = [m for m in plan.module_order if m in MODULES] or list(
            MODULES.keys()
        )
        return plan, True
    except Exception as e:
        print(f"AI reja xatosi, fallback ishlatildi: {e!r}")
        return _fallback_plan(answers, test), False
