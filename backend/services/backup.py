"""Ma'lumotlar bazasi zaxira nusxasi (K23.1).

2026-09-22 hodisasi (eski arxiv kod ustidan yozildi) ko'rsatdi: 1257 foydalanuvchi progressi bitta
SQLite faylda, bitta serverda, nusxasiz. Endi:

- Har kuni BACKUP_HOUR (03:00 Toshkent) dan keyin bir marta (Meta «backup_done» = sana):
  SQLite online backup API (ilova yozayotganda ham izchil nusxa) → PRAGMA quick_check → gzip →
  data/backups/arabiy-YYYY-MM-DD.db.gz; KEEP ta oxirgi nusxa saqlanadi.
- Adminga Telegram hujjat sifatida yuboriladi — serverdan TASHQARIDA nusxa (Telegram limiti 50 MB;
  kattaroq bo'lsa faqat serverda qoladi, admin ogohlantiriladi — scp bilan olish kerak).
- /zaxira — qo'lda hozir; /tekshir — oxirgi nusxa vaqti va soni.

Tiklash (deploy/DEPLOY.md): systemctl stop arabiy → gunzip -c arabiy-….db.gz > data/arabiy.db → start.
"""

import asyncio
import gzip
import logging
import shutil
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import Meta, User, utcnow
from services.stats import TASHKENT_OFFSET

log = logging.getLogger(__name__)

BACKUP_HOUR = 3  # Toshkent — eng jim vaqt
CHECK_INTERVAL = 15 * 60
KEEP = 14  # kunlik nusxalar soni
MARKER = "backup_done"
TG_LIMIT = 49 * 1024 * 1024  # Telegram bot hujjati ≤ 50 MB
STALE_HOURS = 36  # /tekshir: shundan eski bo'lsa ogohlantirish
PREFIX = "arabiy-"


def db_path() -> Path:
    from db.session import DB_PATH

    return Path(DB_PATH)


def backup_dir() -> Path:
    return db_path().parent / "backups"


def _local(now: datetime) -> datetime:
    return now + TASHKENT_OFFSET


@dataclass
class BackupInfo:
    path: Path
    raw_size: int
    gz_size: int
    check: str  # PRAGMA quick_check natijasi ("ok" kutiladi)
    seconds: float


def create_backup(src: Path | None = None, dest_dir: Path | None = None, now: datetime | None = None) -> BackupInfo:
    """Sinxron — thread'da chaqiriladi. Online backup API: ilova yozayotganda ham to'liq, izchil nusxa
    (fayl nusxalash EMAS — u yozuv o'rtasida buzilgan nusxa berishi mumkin)."""
    src = src or db_path()
    dest_dir = dest_dir or backup_dir()
    now = now or utcnow()
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / f"{PREFIX}{_local(now).date().isoformat()}.db.gz"
    tmp = dest_dir / f"{PREFIX}tmp-{int(time.time())}.db"
    t0 = time.monotonic()
    try:
        # file:///… URI — Windows yo'llarida ham ishlaydi; mode=ro — manbaga yozilmaydi
        con = sqlite3.connect(Path(src).resolve().as_uri() + "?mode=ro", uri=True)
        try:
            out = sqlite3.connect(str(tmp))
            try:
                # pages/sleep — bo'laklab, yozuvchilarni uzoq bloklamasdan
                con.backup(out, pages=2048, sleep=0.02)
                check = str(out.execute("PRAGMA quick_check").fetchone()[0])
            finally:
                out.close()
        finally:
            con.close()
        raw_size = tmp.stat().st_size
        with open(tmp, "rb") as f_in, gzip.open(final, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out, 1024 * 1024)
    finally:
        tmp.unlink(missing_ok=True)
    return BackupInfo(final, raw_size, final.stat().st_size, check, time.monotonic() - t0)


def list_backups(dest_dir: Path | None = None) -> list[Path]:
    dest_dir = dest_dir or backup_dir()
    if not dest_dir.exists():
        return []
    return sorted(p for p in dest_dir.glob(f"{PREFIX}*.db.gz") if p.is_file())


def rotate(dest_dir: Path | None = None, keep: int = KEEP) -> list[Path]:
    """Eng eski nusxalar o'chiriladi — `keep` ta qoladi (nom = sana, tartib shunga ko'ra)."""
    files = list_backups(dest_dir)
    removed = files[: max(0, len(files) - keep)]
    for p in removed:
        p.unlink(missing_ok=True)
    return removed


def status(dest_dir: Path | None = None) -> dict:
    """/tekshir uchun: soni, oxirgisi (Toshkent vaqti), hajmi, eskirganmi."""
    files = list_backups(dest_dir)
    if not files:
        return {"count": 0, "last": None, "size": 0, "stale": True}
    last = files[-1]  # nom = sana → eng yangisi oxirida
    at = datetime.fromtimestamp(last.stat().st_mtime, tz=timezone.utc).replace(tzinfo=None)
    return {
        "count": len(files),
        "last": _local(at),
        "size": last.stat().st_size,
        "stale": utcnow() - at > timedelta(hours=STALE_HOURS),
        "path": last,
    }


def _mb(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB"


async def run(session: AsyncSession, bot, now: datetime | None = None, manual: bool = False) -> dict:
    """Zaxira + tozalash + adminga hujjat. Qaytaradi: {"info", "removed", "sent", "users"}."""
    now = now or utcnow()
    info = await asyncio.to_thread(create_backup, None, None, now)
    removed = rotate()
    users = (await session.execute(select(func.count(User.id)))).scalar_one()
    local = _local(now)
    caption = (
        f"🗄 <b>Zaxira nusxa</b> · {local:%d.%m %H:%M}{' (qo‘lda)' if manual else ''}\n"
        f"Baza {_mb(info.raw_size)} → {_mb(info.gz_size)} · {users} foydalanuvchi · "
        f"{'✅ butun' if info.check == 'ok' else '⚠️ quick_check: ' + info.check[:60]} · {info.seconds:.1f}s\n"
        f"Serverda {len(list_backups())} ta ({KEEP} kun saqlanadi). Tiklash: DEPLOY.md «Tiklash»."
    )
    sent = False
    if bot is not None and settings.admin_id:
        try:
            if info.gz_size <= TG_LIMIT:
                from aiogram.types import FSInputFile

                await bot.send_document(settings.admin_id, FSInputFile(str(info.path)), caption=caption, parse_mode="HTML")
                sent = True
            else:
                await bot.send_message(
                    settings.admin_id,
                    caption + f"\n\n⚠️ Fayl {_mb(info.gz_size)} — Telegram limitidan katta, faqat serverda: "
                    f"<code>scp root@server:{info.path} .</code>",
                    parse_mode="HTML",
                )
        except Exception as e:  # tarmoq — nusxa serverda bor, keyingi kun yana urinadi
            log.warning("Zaxira yuborilmadi: %r", e)
    if info.check != "ok":
        log.error("Zaxira quick_check: %s", info.check)
    return {"info": info, "removed": removed, "sent": sent, "users": users}


async def process(session: AsyncSession, bot, now: datetime | None = None) -> bool:
    """Kuniga bir marta, BACKUP_HOUR dan keyin (Meta marker). Bajarilsa True."""
    now = now or utcnow()
    local = _local(now)
    if local.hour < BACKUP_HOUR:
        return False
    key = local.date().isoformat()
    marker = (await session.execute(select(Meta).where(Meta.key == MARKER))).scalar_one_or_none()
    if marker and marker.value == key:
        return False
    if marker:
        marker.value = key
    else:
        marker = Meta(key=MARKER, value=key)
    session.add(marker)
    await session.commit()
    try:
        await run(session, bot, now)
    except Exception as e:
        log.error("Zaxira xatosi: %r", e)
        if bot is not None and settings.admin_id:
            try:
                await bot.send_message(settings.admin_id, f"🔴 Zaxira nusxa olinmadi: {type(e).__name__}: {str(e)[:200]}")
            except Exception:
                pass
        return False
    return True


async def loop(bot) -> None:
    from db.session import SessionLocal

    while True:
        try:
            async with SessionLocal() as session:
                await process(session, bot)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("Zaxira halqasi xatosi: %r", e)
        await asyncio.sleep(CHECK_INTERVAL)
