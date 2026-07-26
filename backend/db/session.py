from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import BASE_DIR, settings

DB_PATH = Path(settings.db_path) if settings.db_path else BASE_DIR / "arabiy.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}")
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with SessionLocal() as session:
        yield session


# Mavjud jadvalga yangi ustunlar (SQLite create_all ustun qo'shmaydi)
_MIGRATIONS = {
    "users": {
        "notified_date": "VARCHAR(10) DEFAULT ''",
        "is_demo": "INTEGER DEFAULT 0",
        "rank_notice_at": "DATETIME",
        "last_rank": "INTEGER DEFAULT 0",
    },
    "user_words": {
        "card_type": "VARCHAR(16) DEFAULT 'word'",
        "deck": "VARCHAR(8) DEFAULT 'msa'",
    },
    "plans": {
        "start_lesson": "VARCHAR(12) DEFAULT 'a0-01'",
        "placement_version": "INTEGER DEFAULT 0",
    },
    "certificates": {
        "kind": "VARCHAR(8) DEFAULT 'level'",
    },
    "exam_attempts": {
        "kind": "VARCHAR(8) DEFAULT 'level'",
        "checkpoint": "INTEGER DEFAULT 0",
    },
}


async def _ensure_columns(conn) -> None:
    for table, columns in _MIGRATIONS.items():
        existing = {
            row[1]
            for row in (await conn.exec_driver_sql(f"PRAGMA table_info({table})"))
        }
        for col, ddl in columns.items():
            if col not in existing:
                await conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"
                )


async def _shift_a2_lessons(conn) -> None:
    """Bir martalik migratsiya: sarf moduli (9 dars) A2 boshiga qo'shilgani
    uchun eski a2-01..a2-45 identifikatorlari a2-10..a2-54 ga suriladi.
    Meta jadvalidagi kalit orqali qayta ishlamaydi."""
    key = "a2_sarf_shift_v1"
    row = (
        await conn.exec_driver_sql(
            "SELECT value FROM meta WHERE key = ?", (key,)
        )
    ).first()
    if row:
        return
    shift = (
        "UPDATE {t} SET {c} = printf('a2-%02d', "
        "CAST(substr({c}, 4) AS INTEGER) + 9) WHERE {c} LIKE 'a2-%'"
    )
    for table, col in (
        ("progress", "lesson_id"),
        ("lesson_ratings", "lesson_id"),
        ("plans", "start_lesson"),
    ):
        await conn.exec_driver_sql(shift.format(t=table, c=col))
    await conn.exec_driver_sql(
        "INSERT INTO meta (key, value) VALUES (?, 'done')", (key,)
    )


async def _remove_b1_quran_module(conn) -> None:
    """Bir martalik migratsiya: B1 dagi «Qur'on va hadis» moduli (b1-27..b1-34)
    olib tashlandi. Shu darslarning progressi o'chiriladi, keyingi darslar
    (b1-35..b1-50) 8 taga pastga suriladi: b1-27..b1-42."""
    key = "b1_quran_removal_v1"
    row = (
        await conn.exec_driver_sql(
            "SELECT value FROM meta WHERE key = ?", (key,)
        )
    ).first()
    if row:
        return

    removed = "{c} IN ('b1-27','b1-28','b1-29','b1-30','b1-31','b1-32','b1-33','b1-34')"
    kept = "CAST(substr({c}, 4) AS INTEGER) BETWEEN 35 AND 50"
    shift = (
        "UPDATE {t} SET {c} = printf('b1-%02d', "
        "CAST(substr({c}, 4) AS INTEGER) - 8) "
        "WHERE {c} LIKE 'b1-%' AND " + kept
    )

    # 1) O'chirilgan darslar yozuvlari
    for table, col in (("progress", "lesson_id"), ("lesson_ratings", "lesson_id")):
        await conn.exec_driver_sql(
            f"DELETE FROM {table} WHERE " + removed.format(c=col)
        )
    # start_lesson o'chirilgan darsga ishora qilsa — modul boshiga qaytaramiz
    await conn.exec_driver_sql(
        "UPDATE plans SET start_lesson = 'b1-27' WHERE "
        + removed.format(c="start_lesson")
    )

    # 2) Qolganini surish
    for table, col in (
        ("progress", "lesson_id"),
        ("lesson_ratings", "lesson_id"),
        ("plans", "start_lesson"),
    ):
        await conn.exec_driver_sql(shift.format(t=table, c=col))

    await conn.exec_driver_sql(
        "INSERT INTO meta (key, value) VALUES (?, 'done')", (key,)
    )


async def init_db():
    from db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_columns(conn)
        await _shift_a2_lessons(conn)
        await _remove_b1_quran_module(conn)
