"""Savol bankidan TAKRORLANMAYDIGAN tanlov (K14).

Foydalanuvchi yiqilib qayta topshirganda aynan o'sha savollar tushmasligi
kerak — aks holda javoblar yodlanib qolinadi va test hech narsani o'lchamaydi.
Shu modul barcha imtihon turlari uchun umumiy ikkita ishni bajaradi:

  * `qhash` — savolni matni bo'yicha barqaror belgilaydi (bank fayllarida ID
    yo'q, shuning uchun xesh ishlatiladi);
  * `pick_fresh` — avval KO'RILMAGAN savollarni oladi, yetmasa qolganidan
    to'ldiradi (bank tugab qolsa ham imtihon berilishi kerak).
"""

import hashlib
import json
import random

# Xeshga kiradigan maydonlar: savol matni va javobi (variantlar tartibi emas)
_FIELDS = ("type", "q_uz", "q_ar", "answer", "audio", "task_uz", "text_ar", "root")


def qhash(item: dict) -> str:
    """Savolning barqaror belgisi — matn o'zgarmasa xesh ham o'zgarmaydi."""
    parts = [str(item.get(f, "")) for f in _FIELDS]
    # Matnli topshiriqlarda (passages) savollar ham farqlovchi bo'lib xizmat qiladi
    if item.get("questions"):
        parts.append(
            json.dumps(
                [q.get("q_uz", "") for q in item["questions"]], ensure_ascii=False
            )
        )
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


def pick_fresh(
    items: list[dict],
    n: int,
    seen: set[str] | None = None,
    rnd: random.Random | None = None,
) -> list[dict]:
    """n ta savol: birinchi navbatda ko'rilmaganlardan.

    Bank tugagan bo'lsa (hammasi ko'rilgan) — eskilaridan tasodifiy oladi,
    lekin oldingi urinishga imkon qadar o'xshamasligi uchun aralashtiradi.
    """
    if n <= 0 or not items:
        return []
    rnd = rnd or random.Random()
    seen = seen or set()

    fresh = [it for it in items if qhash(it) not in seen]
    stale = [it for it in items if qhash(it) in seen]
    rnd.shuffle(fresh)
    rnd.shuffle(stale)

    out = fresh[:n]
    if len(out) < n:
        out += stale[: n - len(out)]
    return out


def shuffle_options(items: list[dict], rnd: random.Random) -> list[dict]:
    """Variantlarni aralashtiradi (tartib yodda qolmasin), takrorlarini olib tashlaydi."""
    out = []
    for it in items:
        it = dict(it)
        opts = it.get("options")
        if opts:
            uniq: list[str] = []
            for o in opts:
                if o not in uniq:
                    uniq.append(o)
            rnd.shuffle(uniq)
            it["options"] = uniq
        out.append(it)
    return out
