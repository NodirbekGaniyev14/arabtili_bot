"""Ulashish kartasi (K21.5) — haftalik natija rasmi, Telegram story formati (1080×1920).

Ichida: streak, bu hafta XP va darslar, o'rganilgan so'zlar, reyting o'rni, 7 kunlik
XP ustunlari, taklif havolasi + QR (do'st birinchi darsni tugatsa — ikkalasiga
REF_DAYS kun VIP). Rasm `data/share/` da; foydalanuvchi uchun faqat oxirgisi qoladi.
`GET /api/share/<fayl>` ochiq (havolani bilgan har kim) — Telegram `shareToStory`
rasmni o'z serveridan yuklaydi, shuning uchun auth'siz bo'lishi shart; fayl nomi
tasodifiy token. Emoji yo'q — Pillow'da Amiri shrifti emoji chizmaydi.
"""

import secrets
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import qrcode
from PIL import Image, ImageDraw
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import User
from services import referral
from services.certificate import CERT_DIR, EMERALD, EMERALD_DARK, GOLD, INK, SAND, _ar, _font
from services.league import leaderboard
from services.stats import user_stats

SHARE_DIR = CERT_DIR.parent / "share"
W, H = 1080, 1920
SOFT = (232, 224, 208)  # kartochka chegarasi
CARD = (255, 253, 247)
MUTED = (120, 112, 98)
WD = ("Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya")


def public_origin() -> str:
    """Mini App URL'idan sxema+host: https://arabiy.example — ochiq fayl havolalari uchun."""
    u = urlsplit(settings.webapp_url or "")
    return f"{u.scheme}://{u.netloc}" if u.scheme and u.netloc else ""


async def card_data(session: AsyncSession, user: User) -> dict:
    st = await user_stats(session, user.id)
    board = await leaderboard(session, user.id, "week")
    me = next((e for e in board["entries"] if e.get("is_me")), None)
    week = st.get("week") or []
    wd = []
    for d in week:
        try:
            y, m, dd = (int(x) for x in d["day"].split("-"))
            wd.append(WD[date(y, m, dd).weekday()])
        except (ValueError, KeyError):
            wd.append("")
    return {
        "name": (user.name or "O'rganuvchi").strip()[:24],
        "level": (me or {}).get("level") or "A0",
        "streak": int(st.get("streak") or 0),
        "words": int(st.get("words") or 0),
        "lessons_total": int(st.get("lessons") or 0),
        "week_xp": sum(int(d.get("xp") or 0) for d in week),
        "week_lessons": sum(int(d.get("lessons") or 0) for d in week),
        "week": [int(d.get("xp") or 0) for d in week],
        "week_days": wd,
        "rank": int(board.get("my_rank") or 0) if (me or {}).get("xp") else 0,
        "total": len(board.get("entries") or []),
        "ref_link": referral.link_for(user),
        "ref_days": referral.REF_DAYS,
    }


def _rounded(d: ImageDraw.ImageDraw, box, r: int, fill, outline=None, width: int = 2):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def _stat(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, value: str, label: str):
    _rounded(d, [x, y, x + w, y + h], 28, CARD, SOFT)
    f = _font(66)
    vw = d.textlength(value, font=f)
    d.text((x + (w - vw) / 2, y + 26), value, font=f, fill=EMERALD_DARK)
    lf = _font(26)
    lw = d.textlength(label, font=lf)
    d.text((x + (w - lw) / 2, y + h - 58), label, font=lf, fill=MUTED)


def render(data: dict, out_path: Path) -> None:
    img = Image.new("RGB", (W, H), SAND)
    d = ImageDraw.Draw(img)

    # Yuqori yashil bosh
    d.rectangle([0, 0, W, 400], fill=EMERALD)
    d.rectangle([0, 400, W, 412], fill=GOLD)
    d.text((72, 78), "ARABIY", font=_font(92), fill=SAND)
    d.text((72, 190), "arab tilini o'rganish", font=_font(40), fill=(214, 236, 226))
    big = _font(150)
    ar = _ar("عَرَبِي")
    d.text((W - 72 - d.textlength(ar, font=big), 120), ar, font=big, fill=(214, 236, 226))

    # Ism + daraja
    d.text((72, 470), data["name"], font=_font(64), fill=INK)
    lvl = f"{data['level']} daraja"
    d.text((72, 552), lvl, font=_font(34), fill=MUTED)

    # Streak doirasi
    cx, cy, r = W - 72 - 150, 560, 130
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GOLD)
    d.ellipse([cx - r + 12, cy - r + 12, cx + r - 12, cy + r - 12], fill=(250, 246, 238))
    sf = _font(110)
    s = str(data["streak"])
    d.text((cx - d.textlength(s, font=sf) / 2, cy - 92), s, font=sf, fill=EMERALD_DARK)
    lf = _font(28)
    lab = "kun ketma-ket"
    d.text((cx - d.textlength(lab, font=lf) / 2, cy + 30), lab, font=lf, fill=MUTED)

    # Statistika 2×2
    gx, gy, gw, gh, gap = 72, 740, 456, 180, 24
    _stat(d, gx, gy, gw, gh, str(data["week_xp"]), "XP · so'nggi 7 kun")
    _stat(d, gx + gw + gap, gy, gw, gh, str(data["week_lessons"]), "dars · so'nggi 7 kun")
    _stat(d, gx, gy + gh + gap, gw, gh, str(data["words"]), "so'z o'rganildi")
    rank = f"#{data['rank']}" if data["rank"] else "—"
    _stat(d, gx + gw + gap, gy + gh + gap, gw, gh, rank, f"reyting · {data['total']} ishtirokchi")

    # 7 kunlik ustunlar
    by = gy + 2 * gh + gap + 40
    _rounded(d, [72, by, W - 72, by + 300], 28, CARD, SOFT)
    d.text((104, by + 24), "SO'NGGI 7 KUN · XP", font=_font(26), fill=MUTED)
    week = data["week"] or [0] * 7
    mx = max(week + [1])
    n = len(week)
    bw = (W - 144 - 64 - (n - 1) * 18) // max(n, 1)
    base = by + 225
    for i, v in enumerate(week):
        x = 104 + i * (bw + 18)
        hgt = max(int(140 * v / mx), 8 if v else 4)
        color = EMERALD if i == n - 1 else (EMERALD if v else SOFT)
        if v and i != n - 1:
            color = (126, 178, 156)
        _rounded(d, [x, base - hgt, x + bw, base], 10, color)
        day = (data.get("week_days") or [""] * n)[i] if i < len(data.get("week_days") or []) else ""
        df = _font(24)
        d.text((x + (bw - d.textlength(day, font=df)) / 2, base + 14), day, font=df, fill=MUTED)

    # Hikmat
    hy = by + 306
    hf = _font(56)
    hik = _ar("مَنْ جَدَّ وَجَدَ")
    d.text(((W - d.textlength(hik, font=hf)) / 2, hy), hik, font=hf, fill=EMERALD_DARK)
    tf = _font(30)
    t = "Kim tirishsa — topadi"
    d.text(((W - d.textlength(t, font=tf)) / 2, hy + 74), t, font=tf, fill=MUTED)

    # Taklif: havola + QR
    fy = H - 320
    d.rectangle([0, fy, W, H], fill=EMERALD_DARK)
    d.text((72, fy + 34), "Men bilan o'rganing", font=_font(46), fill=SAND)
    d.text((72, fy + 98), f"Do'stingiz birinchi darsni tugatsa — ikkalangizga {data['ref_days']} kun VIP", font=_font(26), fill=(190, 222, 208))
    link = data["ref_link"].replace("https://", "")
    d.text((72, fy + 152), link, font=_font(30), fill=GOLD)
    d.text((72, fy + 212), "@" + settings.bot_username, font=_font(30), fill=SAND)
    qr = qrcode.QRCode(box_size=6, border=1)
    qr.add_data(data["ref_link"])
    qr.make(fit=True)
    qimg = qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((230, 230))
    frame = Image.new("RGB", (254, 254), SAND)
    frame.paste(qimg, (12, 12))
    img.paste(frame, (W - 72 - 254, fy + 33))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)


async def issue(session: AsyncSession, user: User) -> tuple[Path, str]:
    """Kartani yasaydi; (fayl yo'li, /api/share/<fayl>). Foydalanuvchining eski kartalari o'chadi."""
    data = await card_data(session, user)
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    for old in SHARE_DIR.glob(f"week_{user.id}_*.png"):
        try:
            old.unlink()
        except OSError:
            pass
    name = f"week_{user.id}_{secrets.token_hex(8)}.png"
    path = SHARE_DIR / name
    render(data, path)
    return path, f"/api/share/{name}"


def caption(data: dict) -> str:
    parts = [f"🔥 {data['streak']} kun ketma-ket", f"{data['week_xp']} XP so'nggi 7 kunda"]
    if data["rank"]:
        parts.append(f"reytingda #{data['rank']}")
    return (
        f"Arabiy'da arab tili: {' · '.join(parts)}.\n"
        f"Men bilan o'rganing — havola orqali kelsangiz, birinchi darsdan keyin ikkalamizga {data['ref_days']} kun VIP:\n"
        f"{data['ref_link']}"
    )
