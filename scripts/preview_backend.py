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

uvicorn.run("main:app", host="127.0.0.1", port=8000)
