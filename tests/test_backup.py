"""K23.1 — DB zaxira nusxasi: online backup + gzip, aylanish, kuniga bir marta (Meta), adminga hujjat,
Telegram limiti, /tekshir qatori."""

import gzip
import sqlite3
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from db.models import Meta
from services import backup


class FakeBot:
    def __init__(self):
        self.docs: list[tuple[int, str, str]] = []
        self.sent: list[tuple[int, str]] = []

    async def send_document(self, chat_id, document, caption="", **kw):
        self.docs.append((chat_id, str(document.path), caption))

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


def _make_db(path, rows=50):
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    con.executemany("INSERT INTO users (name) VALUES (?)", [(f"u{i}",) for i in range(rows)])
    con.commit()
    con.close()


def test_create_backup_is_consistent_gzip(tmp_path):
    src = tmp_path / "arabiy.db"
    _make_db(src, 120)
    now = datetime(2026, 9, 22, 22, 30)  # 03:30 Toshkent 23.09 → fayl nomi 2026-09-23
    info = backup.create_backup(src, tmp_path / "backups", now)
    assert info.path.name == "arabiy-2026-09-23.db.gz" and info.check == "ok"
    assert info.raw_size > 0 and 0 < info.gz_size < info.raw_size
    assert not list((tmp_path / "backups").glob("*tmp*")), "vaqtinchalik fayl o'chirilgan"
    restored = tmp_path / "restored.db"
    restored.write_bytes(gzip.decompress(info.path.read_bytes()))
    con = sqlite3.connect(str(restored))
    assert con.execute("SELECT count(*) FROM users").fetchone()[0] == 120
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    con.close()
    # Manba o'zgarmagan (read-only ochilgan)
    assert sqlite3.connect(str(src)).execute("SELECT count(*) FROM users").fetchone()[0] == 120


def test_rotate_and_status(tmp_path, monkeypatch):
    d = tmp_path / "backups"
    d.mkdir()
    for i in range(1, 18):
        (d / f"arabiy-2026-09-{i:02d}.db.gz").write_bytes(b"x" * i)
    (d / "boshqa.txt").write_text("qolsin")
    removed = backup.rotate(d, keep=14)
    assert [p.name for p in removed] == ["arabiy-2026-09-01.db.gz", "arabiy-2026-09-02.db.gz", "arabiy-2026-09-03.db.gz"]
    assert len(backup.list_backups(d)) == 14 and (d / "boshqa.txt").exists()
    st = backup.status(d)
    assert st["count"] == 14 and st["path"].name == "arabiy-2026-09-17.db.gz" and st["stale"] is False
    assert backup.status(tmp_path / "yoq")["count"] == 0


@pytest.mark.asyncio
async def test_process_once_per_day_and_sends_document(session, tmp_path, monkeypatch):
    from config import settings

    src = tmp_path / "arabiy.db"
    _make_db(src)
    monkeypatch.setattr(settings, "admin_id", 42)
    monkeypatch.setattr(backup, "db_path", lambda: src)
    monkeypatch.setattr(backup, "backup_dir", lambda: tmp_path / "backups")
    bot = FakeBot()
    early = datetime(2026, 9, 21, 21, 0)  # 02:00 Toshkent 22.09 — hali erta
    assert await backup.process(session, bot, early) is False
    at = datetime(2026, 9, 21, 22, 10)  # 03:10 Toshkent 22.09
    assert await backup.process(session, bot, at) is True
    assert len(bot.docs) == 1 and bot.docs[0][0] == 42 and bot.docs[0][1].endswith("arabiy-2026-09-22.db.gz")
    assert "Zaxira nusxa" in bot.docs[0][2] and "✅ butun" in bot.docs[0][2] and "foydalanuvchi" in bot.docs[0][2]
    marker = (await session.execute(select(Meta).where(Meta.key == backup.MARKER))).scalar_one()
    assert marker.value == "2026-09-22"
    # O'sha kuni yana — yo'q; ertasi — yana bir marta
    assert await backup.process(session, bot, at + timedelta(hours=5)) is False
    assert await backup.process(session, bot, at + timedelta(days=1)) is True
    assert len(bot.docs) == 2 and len(backup.list_backups(tmp_path / "backups")) == 2


@pytest.mark.asyncio
async def test_run_too_big_for_telegram_warns(session, tmp_path, monkeypatch):
    from config import settings

    src = tmp_path / "arabiy.db"
    _make_db(src, 500)
    monkeypatch.setattr(settings, "admin_id", 42)
    monkeypatch.setattr(backup, "db_path", lambda: src)
    monkeypatch.setattr(backup, "backup_dir", lambda: tmp_path / "backups")
    monkeypatch.setattr(backup, "TG_LIMIT", 10)  # baytlar — hamma narsa «katta»
    bot = FakeBot()
    r = await backup.run(session, bot, datetime(2026, 9, 21, 22, 10), manual=True)
    assert r["sent"] is False and bot.docs == []
    assert len(bot.sent) == 1 and "limitidan katta" in bot.sent[0][1] and "scp" in bot.sent[0][1]
    assert r["info"].path.exists(), "nusxa serverda baribir qoladi"


@pytest.mark.asyncio
async def test_process_failure_notifies_admin(session, tmp_path, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 42)
    monkeypatch.setattr(backup, "db_path", lambda: tmp_path / "yoq.db")  # manba yo'q → xato
    monkeypatch.setattr(backup, "backup_dir", lambda: tmp_path / "backups")
    bot = FakeBot()
    assert await backup.process(session, bot, datetime(2026, 9, 21, 22, 10)) is False
    assert len(bot.sent) == 1 and "olinmadi" in bot.sent[0][1]


def test_diag_line(tmp_path, monkeypatch):
    from services import diag

    monkeypatch.setattr(backup, "backup_dir", lambda: tmp_path / "backups")
    assert "hali yo'q" in diag.check_backup() and diag.check_backup().startswith("⚠️")
    d = tmp_path / "backups"
    d.mkdir()
    (d / "arabiy-2026-09-22.db.gz").write_bytes(b"x" * 2048)
    line = diag.check_backup()
    assert line.startswith("✅") and "1 ta" in line and "0.0 MB" in line
    monkeypatch.setattr(backup, "STALE_HOURS", -1)
    assert diag.check_backup().startswith("⚠️") and "ESKI" in diag.check_backup()
