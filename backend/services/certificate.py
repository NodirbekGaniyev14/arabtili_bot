"""Sertifikat generatori — PNG (Pillow) + PDF (reportlab, rasm ichida).

Dizayn: qum fon, oltin hoshiya, to'q yashil sarlavha, arab kalligrafiya
qatori, QR kod bilan tekshirish (spec §12.3).
"""

import json
import random
import string
from datetime import datetime, timezone
from pathlib import Path

import arabic_reshaper
import qrcode
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.ext.asyncio import AsyncSession

from config import BASE_DIR, settings
from db.models import Certificate

FONT_PATH = BASE_DIR / "assets" / "fonts" / "Amiri-Regular.ttf"
CERT_DIR = Path(settings.db_path).parent / "certificates" if settings.db_path else BASE_DIR / "data" / "certificates"

SAND = (250, 246, 238)
EMERALD = (14, 107, 78)
EMERALD_DARK = (10, 77, 56)
GOLD = (201, 162, 39)
INK = (38, 33, 26)

LEVEL_NAMES = {
    "A0": "التأسيس",
    "A1": "المبتدئ",
    "A2": "ما قبل المتوسط",
    "B1": "المتوسط",
}


def _ar(text: str) -> str:
    """Arab matnini to'g'ri ulangan + RTL ko'rinishga keltiradi."""
    return get_display(arabic_reshaper.reshape(text))


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def new_cert_id(level: str) -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"ARB-{level}-{suffix}"


def _center(draw: ImageDraw.ImageDraw, y: int, text: str, font, fill, width: int):
    w = draw.textlength(text, font=font)
    draw.text(((width - w) / 2, y), text, font=font, fill=fill)


def render_png(
    cert_id: str,
    name: str,
    level: str,
    total: int,
    scores: dict,
    issued: str,
    verify_url: str,
    out_path: Path,
) -> None:
    W, H = 1200, 850
    img = Image.new("RGB", (W, H), SAND)
    d = ImageDraw.Draw(img)

    # Hoshiyalar
    d.rectangle([20, 20, W - 20, H - 20], outline=GOLD, width=6)
    d.rectangle([36, 36, W - 36, H - 36], outline=EMERALD, width=2)

    # Sarlavha
    _center(d, 60, "ARABIY", _font(64), EMERALD_DARK, W)
    _center(d, 140, _ar("شَهادة إتمام دَورة المستوى"), _font(44), GOLD, W)
    _center(d, 205, "KURSNI TUGATGANLIK SERTIFIKATI", _font(22), INK, W)

    # Daraja muhri (aylantirilgan kvadrat effekti — romb)
    cx, cy, r = W // 2, 330, 70
    d.polygon(
        [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
        fill=EMERALD, outline=EMERALD_DARK,
    )
    lf = _font(52)
    lw = d.textlength(level, font=lf)
    d.text((cx - lw / 2, cy - 34), level, font=lf, fill=SAND)
    _center(d, cy + r + 10, _ar(LEVEL_NAMES.get(level, "")), _font(30), EMERALD, W)

    # Ism va ball
    _center(d, 480, name or "O'rganuvchi", _font(48), INK, W)
    _center(d, 548, f"Arabiy {level} kursini tugatdi", _font(26), EMERALD_DARK, W)
    _center(d, 590, f"Yakuniy imtihon: {total} / 100", _font(26), EMERALD_DARK, W)
    parts = (
        f"O'qish {scores.get('reading', 0)}  ·  Tinglash {scores.get('listening', 0)}"
        f"  ·  Yozish {scores.get('writing', 0)}  ·  Gapirish {scores.get('speaking', 0)}"
    )
    _center(d, 634, parts, _font(22), INK, W)

    # Halollik izohi — bu rasmiy CEFR guvohnomasi EMAS
    _center(
        d, 672,
        "Ichki kurs sertifikati · rasmiy CEFR guvohnomasi emas",
        _font(17), (138, 128, 113), W,
    )

    # Pastki qator: sana, ID
    d.text((70, H - 142), f"Sana: {issued}", font=_font(24), fill=INK)
    d.text((70, H - 104), f"ID: {cert_id}", font=_font(24), fill=INK)
    d.text((70, H - 70), verify_url, font=_font(18), fill=EMERALD_DARK)

    # QR
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(verify_url)
    qr.make(fit=True)
    qimg = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qimg = qimg.resize((150, 150))
    img.paste(qimg, (W - 220, H - 220))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")


RANK_META = {
    1: ("🥇", "BIRINCHI O'RIN", "المَرْكَزُ الأَوَّل", (201, 162, 39)),
    2: ("🥈", "IKKINCHI O'RIN", "المَرْكَزُ الثَّانِي", (150, 150, 156)),
    3: ("🥉", "UCHINCHI O'RIN", "المَرْكَزُ الثَّالِث", (170, 118, 60)),
}


def render_rank_png(
    cert_id: str,
    name: str,
    rank: int,
    weekly_xp: int,
    week_label: str,
    verify_url: str,
    out_path: Path,
) -> None:
    """Haftalik reyting sovrini — daraja sertifikatidan farqli dizayn."""
    _, title_uz, title_ar, accent = RANK_META.get(rank, RANK_META[3])
    W, H = 1200, 850
    img = Image.new("RGB", (W, H), SAND)
    d = ImageDraw.Draw(img)

    d.rectangle([20, 20, W - 20, H - 20], outline=accent, width=6)
    d.rectangle([36, 36, W - 36, H - 36], outline=EMERALD, width=2)

    _center(d, 60, "ARABIY", _font(64), EMERALD_DARK, W)
    _center(d, 140, _ar("جَائِزَةُ الأُسْبُوع"), _font(44), accent, W)
    _center(d, 205, "HAFTALIK REYTING SOVRINI", _font(22), INK, W)

    # O'rin doirasi
    cx, cy, r = W // 2, 335, 78
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent, outline=EMERALD_DARK, width=3)
    rf = _font(76)
    rt = str(rank)
    rw = d.textlength(rt, font=rf)
    d.text((cx - rw / 2, cy - 50), rt, font=rf, fill=SAND)
    _center(d, cy + r + 12, _ar(title_ar), _font(30), EMERALD, W)

    _center(d, 500, name or "O'rganuvchi", _font(48), INK, W)
    _center(d, 570, title_uz, _font(30), EMERALD_DARK, W)
    _center(d, 618, f"Haftalik XP: {weekly_xp}  ·  {week_label}", _font(22), INK, W)

    d.text((70, H - 145), f"Hafta: {week_label}", font=_font(24), fill=INK)
    d.text((70, H - 105), f"ID: {cert_id}", font=_font(24), fill=INK)
    d.text((70, H - 68), verify_url, font=_font(18), fill=EMERALD_DARK)

    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(verify_url)
    qr.make(fit=True)
    qimg = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qimg = qimg.resize((150, 150))
    img.paste(qimg, (W - 220, H - 220))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")


async def issue_weekly_certificate(
    session: AsyncSession,
    user_id: int,
    name: str,
    rank: int,
    weekly_xp: int,
    week_label: str,
) -> Certificate:
    """Haftalik top-3 sovrini uchun sertifikat yaratadi."""
    cert_id = new_cert_id(f"W{rank}")
    issued = datetime.now(timezone.utc).replace(tzinfo=None)
    base_url = settings.webapp_url or "https://arabiy.digitalcfo.uz"
    verify_url = f"{base_url}/api/verify/{cert_id.split('-')[-1]}"

    png_path = CERT_DIR / f"{cert_id}.png"
    render_rank_png(cert_id, name, rank, weekly_xp, week_label, verify_url, png_path)

    cert = Certificate(
        cert_id=cert_id,
        user_id=user_id,
        kind="weekly",
        level=f"W{rank}",
        score=weekly_xp,
        scores_json=json.dumps({"rank": rank, "week": week_label}),
        holder_name=name,
        issued_at=issued,
        png_path=str(png_path),
        pdf_path="",
    )
    session.add(cert)
    await session.commit()
    await session.refresh(cert)
    return cert


def render_pdf(png_path: Path, pdf_path: Path) -> None:
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.pdfgen import canvas

    page = landscape(A4)
    c = canvas.Canvas(str(pdf_path), pagesize=page)
    pw, ph = page
    # PNG nisbatini saqlab markazga joylashtiramiz
    img = Image.open(png_path)
    iw, ih = img.size
    scale = min(pw / iw, ph / ih)
    w, h = iw * scale, ih * scale
    c.drawImage(str(png_path), (pw - w) / 2, (ph - h) / 2, w, h)
    c.showPage()
    c.save()


async def issue_certificate(
    session: AsyncSession,
    user_id: int,
    name: str,
    level: str,
    total: int,
    scores: dict,
) -> Certificate:
    cert_id = new_cert_id(level)
    issued = datetime.now(timezone.utc).replace(tzinfo=None)
    base_url = settings.webapp_url or "https://arabiy.digitalcfo.uz"
    verify_url = f"{base_url}/api/verify/{cert_id.split('-')[-1]}"

    png_path = CERT_DIR / f"{cert_id}.png"
    pdf_path = CERT_DIR / f"{cert_id}.pdf"
    render_png(
        cert_id, name, level, total, scores,
        issued.strftime("%d.%m.%Y"), verify_url, png_path,
    )
    try:
        render_pdf(png_path, pdf_path)
    except Exception:
        pdf_path = Path("")

    cert = Certificate(
        cert_id=cert_id,
        user_id=user_id,
        level=level,
        score=total,
        scores_json=json.dumps(scores),
        holder_name=name,
        issued_at=issued,
        png_path=str(png_path),
        pdf_path=str(pdf_path) if pdf_path else "",
    )
    session.add(cert)
    await session.commit()
    await session.refresh(cert)
    return cert
