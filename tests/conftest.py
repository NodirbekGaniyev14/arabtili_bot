"""Test uchun umumiy fixture'lar — har test o'z vaqtinchalik SQLite bazasida."""

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# Baza yo'lini import'dan OLDIN o'rnatamiz (config settings shu paytda o'qiladi)
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("DEV_AUTH", "0")


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    """Toza bazaga bog'langan sessiya yaratuvchi (SessionLocal o'rniga qo'yiladi)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from db.models import Base

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(session_factory):
    """Toza bazadagi AsyncSession."""
    async with session_factory() as s:
        yield s


@pytest.fixture
def make_user(session):
    """Haqiqiy foydalanuvchi yaratuvchi yordamchi."""
    from db.models import User

    counter = {"n": 0}

    async def _make(name: str = "Test", **kw):
        counter["n"] += 1
        u = User(tg_id=100_000 + counter["n"], name=name, **kw)
        session.add(u)
        await session.flush()
        return u

    return _make
