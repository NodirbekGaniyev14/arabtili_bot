"""Daraja aniqlash testi (placement) — AI'siz, deterministik.

Muammo: ilgari daraja AI fallback'ida test foizidan chiqarilardi
(`ratio >= 0.8 -> A2`), savollar esa 6 ta juda oson savol edi — natijada
deyarli hamma A2 ga tushardi.

Endi: 5 bosqichli (A0 -> B2) test. Har bosqich 5 savol, >=80% (5 dan 4)
bo'lsa «o'tilgan». Bosqichlar pastdan yuqoriga beriladi va birinchi
yiqilishda to'xtaydi (adaptiv).

DARAJA = o'tilmagan BIRINCHI bosqich. Hammasi o'tilsa — B2.
"""

import json
from functools import lru_cache

from config import BASE_DIR

PLACEMENT_PATH = BASE_DIR / "content" / "placement.json"

TIERS = ["A0", "A1", "A2", "B1", "B2"]
# B2 bosqichi qo'shildi, ammo versiya ataylab oshirilmadi: eski foydalanuvchilar
# testni qaytadan topshirmaydi (K15.5 qarori).
PLACEMENT_VERSION = 2  # Plan.placement_version shu qiymatga yetsa qayta test so'ralmaydi


@lru_cache(maxsize=1)
def load_bank() -> dict:
    return json.loads(PLACEMENT_PATH.read_text(encoding="utf-8"))


def pass_ratio() -> float:
    return float(load_bank().get("pass_ratio", 0.8))


def tier_questions(tier: str) -> list[dict]:
    return load_bank()["tiers"][tier]["questions"] if tier in TIERS else []


def tier_title(tier: str) -> str:
    return load_bank()["tiers"].get(tier, {}).get("title_uz", tier)


def tier_passed(correct: int, total: int) -> bool:
    return total > 0 and (correct / total) >= pass_ratio()


def next_tier(results: dict[str, bool]) -> str | None:
    """Keyingi so'raladigan bosqich. Yiqilgan bosqichdan keyin test tugaydi."""
    for t in TIERS:
        if t not in results:
            return t
        if not results[t]:  # yiqildi — yuqorisini so'ramaymiz
            return None
    return None  # hammasi o'tilgan


def decide_level(results: dict[str, bool]) -> str:
    """Daraja = o'tilmagan birinchi bosqich; hammasi o'tilsa B2."""
    for t in TIERS:
        if not results.get(t, False):
            return t
    return TIERS[-1]


def level_reason(level: str, results: dict[str, bool]) -> str:
    passed = [t for t in TIERS if results.get(t)]
    if not passed:
        return (
            "Test harflar bosqichidan boshlanadi — poydevorni mustahkam qo'yamiz. "
            "Alifbo va o'qishdan boshlaymiz."
        )
    last = passed[-1]
    names = {
        "A0": "harflar va o'qish",
        "A1": "so'z va sodda gaplar",
        "A2": "sarf, olmoshlar va fe'l boblari",
        "B1": "yuqori grammatika",
        "B2": "nozik nahv va uslub",
    }
    if len(passed) == len(TIERS):
        return (
            f"Barcha bosqichlarni o'tdingiz — {names['B1']} ham mustahkam. "
            f"{TIERS[-1]} darajasidan davom etamiz."
        )
    return (
        f"{names[last].capitalize()} bo'yicha bilimingiz yetarli, "
        f"keyingi bosqichda esa bo'shliq bor. Shuning uchun {level} darajasidan "
        "boshlaymiz — shu yerda poydevor mustahkamlanadi."
    )


def total_questions() -> int:
    return sum(len(tier_questions(t)) for t in TIERS)
