"""Arabiy bot logosini yasaydi (512x512 PNG) — 2 variant.

Ishlatish:  python branding/make_logo.py
Natija: branding/logo_a.png (ع-monogram) va branding/logo_b.png (tuya-maskot)
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
SIZE = 512

# Ranglar (ilova palitrasi)
EMERALD = (14, 107, 78)
EMERALD_DARK = (10, 58, 44)
CREAM = (250, 246, 238)
GOLD = (201, 162, 39)

AMIRI = str(HERE / "fonts" / "Amiri-Bold.ttf")
ARIAL = "C:/Windows/Fonts/arial.ttf"
ARIAL_BLACK = "C:/Windows/Fonts/ariblk.ttf"
EMOJI = "C:/Windows/Fonts/seguiemj.ttf"


def arabic_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(AMIRI, size)
    except Exception:
        return ImageFont.truetype(ARIAL, size)


def gradient_bg() -> Image.Image:
    """Diagonal zumrad gradient + yumshoq vinetka."""
    img = Image.new("RGB", (SIZE, SIZE))
    px = img.load()
    for y in range(SIZE):
        for x in range(SIZE):
            t = (x + y) / (2 * SIZE)
            r = int(EMERALD[0] * (1 - t) + EMERALD_DARK[0] * t)
            g = int(EMERALD[1] * (1 - t) + EMERALD_DARK[1] * t)
            b = int(EMERALD[2] * (1 - t) + EMERALD_DARK[2] * t)
            px[x, y] = (r, g, b)
    return img.convert("RGBA")


def draw_centered(draw, xy, text, font, fill, anchor="mm", **kw):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor, **kw)


def gold_ring(draw):
    inset = 30
    draw.ellipse(
        [inset, inset, SIZE - inset, SIZE - inset],
        outline=GOLD + (150,),
        width=5,
    )


def add_camel(base: Image.Image, size: int, center):
    """Segoe UI Emoji orqali 🐪 chizadi (COLR rangli)."""
    try:
        ef = ImageFont.truetype(EMOJI, size)
        layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.text(center, "🐪", font=ef, anchor="mm", embedded_color=True)
        base.alpha_composite(layer)
        return True
    except Exception as e:
        print(f"  emoji chizilmadi: {e!r}")
        return False


def variant_a():
    """ع monogrammasi asosiy + kichik tuya."""
    img = gradient_bg()
    d = ImageDraw.Draw(img)
    gold_ring(d)

    # Katta ع (krem)
    d.text((SIZE // 2, 232), "ع", font=arabic_font(300), fill=CREAM, anchor="mm")

    # Kichik tuya pastda
    add_camel(img, 96, (SIZE // 2, 388))

    # Kichik wordmark
    try:
        wf = ImageFont.truetype(ARIAL_BLACK, 34)
    except Exception:
        wf = ImageFont.truetype(ARIAL, 34)
    d = ImageDraw.Draw(img)
    d.text((SIZE // 2, 452), "ARABIY", font=wf, fill=GOLD, anchor="mm")

    out = HERE / "logo_a.png"
    img.convert("RGB").save(out, "PNG")
    print(f"✓ {out.name}")


def variant_b():
    """Tuya-maskot asosiy + ع suvbelgisi."""
    img = gradient_bg()

    # ع suvbelgisi (katta, xira oltin)
    wm = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    dw = ImageDraw.Draw(wm)
    dw.text((SIZE // 2, 250), "ع", font=arabic_font(400), fill=GOLD + (55,), anchor="mm")
    img.alpha_composite(wm)

    d = ImageDraw.Draw(img)
    gold_ring(d)

    # Katta tuya
    add_camel(img, 210, (SIZE // 2, 224))

    # Wordmark
    try:
        wf = ImageFont.truetype(ARIAL_BLACK, 52)
    except Exception:
        wf = ImageFont.truetype(ARIAL, 52)
    d = ImageDraw.Draw(img)
    d.text((SIZE // 2, 400), "ARABIY", font=wf, fill=CREAM, anchor="mm")

    out = HERE / "logo_b.png"
    img.convert("RGB").save(out, "PNG")
    print(f"✓ {out.name}")


def variant_c():
    """ع + tuya, yozuvsiz — avatar uchun eng toza."""
    img = gradient_bg()
    d = ImageDraw.Draw(img)

    # Ikki qavat oltin halqa (nozik ramka)
    d.ellipse([26, 26, SIZE - 26, SIZE - 26], outline=GOLD + (170,), width=6)
    d.ellipse([40, 40, SIZE - 40, SIZE - 40], outline=CREAM + (60,), width=2)

    # Katta ع markazda
    d.text((SIZE // 2, 250), "ع", font=arabic_font(330), fill=CREAM, anchor="mm")

    # Tuya harf ichida
    add_camel(img, 120, (SIZE // 2, 405))

    out = HERE / "logo_c.png"
    img.convert("RGB").save(out, "PNG")
    print(f"✓ {out.name}")


if __name__ == "__main__":
    variant_a()
    variant_b()
    variant_c()
    print("Tayyor.")
