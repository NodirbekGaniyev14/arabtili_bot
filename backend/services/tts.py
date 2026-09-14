"""Dinamik matn → ovoz (edge-tts) — AI ustoz javoblari uchun.

Dars audiosi build vaqtida tayyorlanadi (content/build_audio.py); ustoz
javobi esa har safar yangi, shuning uchun serverda vaqtida yaratiladi va
matn xeshi bo'yicha diskda cache'lanadi. Bir xil jumla ikkinchi marta
bepul. Brauzer speechSynthesis'ga tayanmaymiz — Telegram WebView'da ko'pincha
jim.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from pathlib import Path

from config import BASE_DIR, settings

log = logging.getLogger(__name__)

VOICE = "ar-SA-HamedNeural"  # dars audiosi bilan bir xil ovoz
VOLUME = "+25%"
RATES = {"A0": "-30%", "A1": "-25%", "A2": "-18%", "B1": "-10%", "B2": "-5%"}
_SEM = asyncio.Semaphore(3)  # edge-tts parallel so'rovlar chegarasi
MAX_CHARS = 400


def cache_dir() -> Path:
    """DB bilan yonma-yon (prod: doimiy disk), aks holda loyiha ildizi."""
    base = Path(settings.db_path).parent if settings.db_path else BASE_DIR / "data"
    d = base / "tts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def key_for(text: str, level: str) -> str:
    rate = RATES.get(level.upper(), RATES["A2"])
    h = hashlib.sha1(f"{VOICE}|{rate}|{VOLUME}|{text}".encode("utf-8")).hexdigest()
    return h[:24]


def path_for(key: str) -> Path:
    return cache_dir() / f"{key}.mp3"


# Fonda ishlayotgan sintezlar: kalit → task. Endpoint tayyor bo'lishini kutadi.
_PENDING: dict[str, asyncio.Task] = {}


def schedule(text: str, level: str) -> str:
    """Sintezni fonda boshlaydi, kalitni DARHOL qaytaradi (bo'sh matnda '').

    Javob matni o'quvchiga kutdirmasdan ketsin — mp3 1-3 soniyada tayyor
    bo'ladi; /tutor/audio endpointi (wait_for) va klient retry uni oladi."""
    text = (text or "").strip()[:MAX_CHARS]
    if not text:
        return ""
    key = key_for(text, level)
    if path_for(key).exists() or key in _PENDING:
        return key
    task = asyncio.create_task(synthesize(text, level))
    _PENDING[key] = task
    task.add_done_callback(lambda _t: _PENDING.pop(key, None))
    return key


async def wait_for(key: str, timeout: float = 6) -> None:
    task = _PENDING.get(key)
    if task is None:
        return
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
    except Exception:
        pass  # tayyor bo'lmasa endpoint 404 beradi, klient qayta so'raydi


async def synthesize(text: str, level: str) -> str:
    """mp3 yaratadi (yoki cache'dan oladi) va kalitni qaytaradi. Xatoda ''."""
    text = (text or "").strip()[:MAX_CHARS]
    if not text:
        return ""
    key = key_for(text, level)
    out = path_for(key)
    if out.exists() and out.stat().st_size > 0:
        return key

    rate = RATES.get(level.upper(), RATES["A2"])
    tmp = out.with_suffix(".part")
    try:
        import edge_tts

        async with _SEM:
            comm = edge_tts.Communicate(text, VOICE, rate=rate, volume=VOLUME)
            await asyncio.wait_for(comm.save(str(tmp)), timeout=20)
        os.replace(tmp, out)  # atomik — yarim fayl hech qachon ko'rinmaydi
        return key
    except Exception as e:
        log.warning("TTS xatosi: %r", e)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return ""
