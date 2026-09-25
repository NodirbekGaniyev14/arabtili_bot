"""Bildirishnoma sozlamalari (K26) — o'quvchi qaysi bot xabarlarini olishni o'zi tanlaydi.

Saqlash: `users.notify_off` — o'chirilgan kalitlar vergul bilan ("daily,news"). Bo'sh = hammasi yoniq
(yangi turlar ham avtomatik yoniq bo'ladi). Har yuboruvchi xabar oldidan `enabled(user, key)` ni tekshiradi.

Doim keladigan (sozlanmaydigan) xabarlar: fikringizga javob, to'lov/VIP faollashuvi, sertifikat va
reyting sovrini, do'stning jangga chaqirishi, taklif mukofoti — bular so'rovga javob yoki shaxsiy natija.
"""

from __future__ import annotations

from typing import Any

# (kalit, guruh, belgi, nom, tavsif) — ilovadagi «Bildirishnomalar» sahifasi shu tartibda
ITEMS: list[dict[str, str]] = [
    {"key": "daily", "group": "types", "icon": "🔥", "title": "Kunlik eslatma",
     "desc": "Kunlik maqsad bajarilmagan kuni kechqurun qisqa turtki — streak o'chib qolmasin."},
    {"key": "writing", "group": "types", "icon": "✍️", "title": "Yozuv mashqi",
     "desc": "Har 2 kunda yangi yozuv matni chiqqanda eslatamiz."},
    {"key": "speaking", "group": "types", "icon": "🗣", "title": "Speaking hisoboti",
     "desc": "Har dushanba: o'tgan haftadagi speaking natijangiz."},
    {"key": "rating", "group": "types", "icon": "🏆", "title": "Reyting",
     "desc": "Haftalik va oylik reyting yakuni, o'rningiz tushib qolganda."},
    {"key": "oktagon", "group": "types", "icon": "⚔️", "title": "Oktagon natijalari",
     "desc": "Haftalik jadval va mavsum yakuni."},
    {"key": "vip", "group": "types", "icon": "👑", "title": "VIP muddati",
     "desc": "VIP tugashiga oz qolganda va chegirma bo'lganda eslatamiz."},
    {"key": "survey", "group": "types", "icon": "💬", "title": "So'rov va fikr",
     "desc": "Ba'zan bitta qisqa savol beramiz — javobingiz ilovani yaxshilaydi."},
    {"key": "fixed", "group": "types", "icon": "🐞", "title": "Xato tuzatildi",
     "desc": "Siz bildirgan xato tuzatilganda xabar beramiz."},
    {"key": "news", "group": "other", "icon": "📣", "title": "Ilova yangiliklari",
     "desc": "Yangi bo'limlar va muhim e'lonlar."},
    {"key": "comeback", "group": "other", "icon": "👋", "title": "Qaytish eslatmalari",
     "desc": "Bir necha kun kirmasangiz, eslatib qo'yamiz."},
]
KEYS = frozenset(i["key"] for i in ITEMS)
ALWAYS_NOTE = "To'lov, sertifikat, fikringizga javob va do'stning jangga chaqirishi kabi muhim xabarlar doim keladi."


def disabled(user: Any) -> set[str]:
    raw = getattr(user, "notify_off", "") or ""
    return {k for k in raw.split(",") if k in KEYS}


def enabled(user: Any, key: str) -> bool:
    """Bu turdagi xabar shu foydalanuvchiga yuborilsinmi. Noma'lum kalit — doim ha."""
    return key not in KEYS or key not in disabled(user)


def enabled_raw(notify_off: str | None, key: str) -> bool:
    """Faqat ustun qiymati bilan (select(User.tg_id, User.notify_off) so'rovlari uchun)."""
    return key not in KEYS or key not in {k for k in (notify_off or "").split(",") if k}


def set_pref(user: Any, key: str, on: bool) -> None:
    if key not in KEYS:
        raise ValueError(key)
    off = disabled(user)
    if on:
        off.discard(key)
    else:
        off.add(key)
    user.notify_off = ",".join(k for k in (i["key"] for i in ITEMS) if k in off)


def public(user: Any) -> dict:
    off = disabled(user)
    return {
        "items": [{**i, "on": i["key"] not in off} for i in ITEMS],
        "always": ALWAYS_NOTE,
    }
