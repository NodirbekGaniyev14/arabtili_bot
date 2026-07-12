from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    # SQLite'da bir xil formatda saqlanishi uchun naive UTC
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    username: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Kunlik eslatma yuborilgan oxirgi sana (Toshkent) — takror yubormaslik uchun
    notified_date: Mapped[str] = mapped_column(String(10), default="")
    # Demo raqib (liga jonli ko'rinishi uchun) — haqiqiy foydalanuvchi emas
    is_demo: Mapped[int] = mapped_column(Integer, default=0)


class Placement(Base):
    """Onboarding anketasi va mini-test natijalari (xom holda)."""

    __tablename__ = "placements"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    answers_json: Mapped[str] = mapped_column(Text, default="{}")
    test_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Progress(Base):
    """Tugatilgan darslar (har tugatish alohida yozuv)."""

    __tablename__ = "progress"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    lesson_id: Mapped[str] = mapped_column(String(64), index=True)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    xp_earned: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UserWord(Base):
    """SRS kartotekasi — o'rganilgan har bir harf/so'z/ibora."""

    __tablename__ = "user_words"
    __table_args__ = (UniqueConstraint("user_id", "ar", name="uq_user_word"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ar: Mapped[str] = mapped_column(String(128))
    translit: Mapped[str] = mapped_column(String(128), default="")
    uz: Mapped[str] = mapped_column(String(256), default="")
    audio: Mapped[str] = mapped_column(String(64), default="")
    kind: Mapped[str] = mapped_column(String(16), default="word")
    ease: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    due_date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class XpLog(Base):
    __tablename__ = "xp_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Achievement(Base):
    """Foydalanuvchi qo'lga kiritgan yutuqlar (badge'lar)."""

    __tablename__ = "achievements"
    __table_args__ = (
        UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    badge_id: Mapped[str] = mapped_column(String(48))
    earned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Plan(Base):
    """AI tuzgan shaxsiy o'quv reja."""

    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    level: Mapped[str] = mapped_column(String(4))
    level_reason: Mapped[str] = mapped_column(Text, default="")
    target_level: Mapped[str] = mapped_column(String(4))
    target_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    daily_xp_goal: Mapped[int] = mapped_column(Integer, default=30)
    daily_minutes: Mapped[int] = mapped_column(Integer, default=20)
    focus_areas_json: Mapped[str] = mapped_column(Text, default="[]")
    module_order_json: Mapped[str] = mapped_column(Text, default="[]")
    weekly_schedule_json: Mapped[str] = mapped_column(Text, default="[]")
    motivation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
