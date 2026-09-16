"""Xavfsiz lokal preview backend'i (.claude/launch.json → "backend-preview").

Prod .env'dagi qiymatlarga tegmasdan:
  - BOT_TOKEN bo'sh — Telegram polling ishga tushmaydi (prod bot bilan
    to'qnashmaydi), DEV_AUTH shu tufayli ham faollashadi;
  - DB — arabiy.db NUSXASI (data/preview/), asl ma'lumot o'zgarmaydi;
  - TTS cache ham shu papkada.
ANTHROPIC/STT kalitlari .env'dan olinadi — AI ustoz jonli sinovdan o'tadi.
"""

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREVIEW = ROOT / "data" / "preview"
PREVIEW.mkdir(parents=True, exist_ok=True)

src, dst = ROOT / "arabiy.db", PREVIEW / "arabiy.db"
if src.exists() and not dst.exists():
    shutil.copy(src, dst)

os.environ["BOT_TOKEN"] = ""
os.environ["DB_PATH"] = str(dst)
os.environ.setdefault("DEV_AUTH", "1")

# Ixtiyoriy qo'shimcha o'zgaruvchilar (masalan mock AI: scripts/mock_anthropic.py)
extra = PREVIEW / ".env.preview"
if extra.exists():
    for line in extra.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import uvicorn  # noqa: E402

from main import app  # noqa: E402


class _FakePayBot:
    """PREVIEW_FAKE_PAY=1 (.env.preview) — avto to'lov UI'ni Telegram'siz ko'rish:
    invoice havolasi soxta, xabarlar konsolga. PAY_PROVIDER_TOKEN ham berilishi kerak."""

    async def create_invoice_link(self, **kw):
        print(f"[preview] invoice: {kw.get('title')} {kw['prices'][0].amount // 100} so'm payload={kw.get('payload')}")
        return "https://t.me/$preview_fake_invoice"

    async def send_message(self, chat_id, text, **kw):
        print(f"[preview] send_message → {chat_id}: {text[:80]!r}")


if os.environ.get("PREVIEW_FAKE_PAY") == "1":
    app.state.bot = _FakePayBot()

uvicorn.run(app, host="127.0.0.1", port=8000)
