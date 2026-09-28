"""Bot xabarlaridagi ism (K27.5): HTML-xavfsiz, harfsiz ism o'rniga zaxira, bidi-barqaror.

Nega kerak:
- xabarlar parse_mode=HTML bilan ketadi — ismda «<» yoki «&» bo'lsa Telegram butun xabarni
  rad etadi (haftalik reyting / Oktagon e'loni hech kimga yetmaydi, admin digest kelmaydi);
- «...» yoki faqat emojidan iborat ism reytingda noma'lum «...» bo'lib ko'rinadi;
- arabcha ismdan keyingi «(690)» ism oldiga sakraydi (bidi) — oxiriga LRM qo'yiladi.
"""

import html

LRM = chr(0x200E)  # chapdan-o'ngga belgisi (ko'rinmas)


def esc(text: str) -> str:
    """Telegram HTML uchun faqat & < > (apostrof o'zbekcha ismlarda ko'p — tegmaymiz)."""
    return html.escape(text or "", quote=False)


def show(name: str | None, fallback: str = "O'rganuvchi") -> str:
    """Xabarga qo'yiladigan ism: harfi bo'lmasa `fallback`, HTML escape, oxirida LRM."""
    n = (name or "").strip()
    if not any(ch.isalpha() for ch in n):
        n = fallback
    return esc(n) + LRM


def admin_show(name: str | None, username: str | None = "", tg_id: int | None = None) -> str:
    """Admin uchun: harfsiz ism o'rniga @username yoki ID (kimligi ko'rinsin)."""
    fallback = f"@{username}" if username else (f"ID {tg_id}" if tg_id else "—")
    return show(name, fallback)
