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


async def init_db():
    from db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_columns(conn)
