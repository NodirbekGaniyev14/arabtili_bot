"""Profil sozlamalari — hozircha ism tozalash/tekshirish."""

import re
import unicodedata

NAME_MIN = 2
NAME_MAX = 40

# Ko'rinmas belgilar: zero-width, RTL/LTR override, BOM. Ular reyting ro'yxatida
# taqlid qilish yoki qatorni buzish uchun ishlatilishi mumkin.
_INVISIBLE = re.compile("[​-‏‪-‮⁦-⁩﻿]")
_WS = re.compile(r"\s+")


def clean_name(raw: str) -> str:
    """Bir qatorli, ortiqcha bo'shliqsiz, ko'rinmas belgilarsiz ism."""
    text = unicodedata.normalize("NFC", raw or "")
    text = _INVISIBLE.sub("", text)
    # Boshqaruv belgilari (yangi qator, tab, ...) bo'shliqqa aylanadi —
    # "Ali\nValiyev" tashlab yuborilmay "Ali Valiyev" bo'lsin
    text = "".join(
        ch if not unicodedata.category(ch).startswith("C") else " " for ch in text
    )
    return _WS.sub(" ", text).strip()[:NAME_MAX]


def validate_name(raw: str) -> tuple[str, str]:
    """(tozalangan_ism, xato_matni). Xato bo'sh bo'lsa — ism yaroqli."""
    name = clean_name(raw)
    if len(name) < NAME_MIN:
        return "", f"Ism kamida {NAME_MIN} ta belgidan iborat bo'lsin"
    if not any(ch.isalpha() for ch in name):
        return "", "Ismda kamida bitta harf bo'lishi kerak"
    return name, ""
