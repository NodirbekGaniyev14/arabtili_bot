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
    # Oxirgi "o'rin boy berildi" xabari — kuniga ko'p yubormaslik uchun
    rank_notice_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Oxirgi tekshiruvdagi haftalik reyting o'rni (0 = hali hisoblanmagan)
    last_rank: Mapped[int] = mapped_column(Integer, default=0)
    # Joriy liga (bronze|silver|gold|emerald) — haftalik ko'tarilish/tushish
    league_id: Mapped[str] = mapped_column(String(12), default="bronze")
    # Streak himoyasi: qolgan muzlatkichlar soni (haftada +1, ko'pi bilan 2)
    streak_freezes: Mapped[int] = mapped_column(Integer, default=2)
    # Muzlatkich ishlatilgan kunlar, vergul bilan: "2026-07-18,2026-07-25"
    frozen_days: Mapped[str] = mapped_column(Text, default="")
    # Oxirgi muzlatkich berilgan hafta (YYYY-MM-DD, dushanba) — haftada 1 marta
    freeze_granted_week: Mapped[str] = mapped_column(String(10), default="")


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
    """SRS kartotekasi — o'rganilgan har bir harf/so'z/ibora.

    v2: card_type (word/root/pattern/phrase) va deck (msa/hejazi) qo'shildi.
    """

    __tablename__ = "user_words"
    __table_args__ = (UniqueConstraint("user_id", "ar", name="uq_user_word"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ar: Mapped[str] = mapped_column(String(128))
    translit: Mapped[str] = mapped_column(String(128), default="")
    uz: Mapped[str] = mapped_column(String(256), default="")
    audio: Mapped[str] = mapped_column(String(64), default="")
    kind: Mapped[str] = mapped_column(String(16), default="word")
    card_type: Mapped[str] = mapped_column(String(16), default="word")
    deck: Mapped[str] = mapped_column(String(8), default="msa")
    ease: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    due_date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RootProgress(Base):
    """O'zak bo'yicha progress (Root Lab + darslardagi uchrashuvlar)."""

    __tablename__ = "root_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "root", name="uq_user_root"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    root: Mapped[str] = mapped_column(String(16))
    seen_count: Mapped[int] = mapped_column(Integer, default=0)
    mastered: Mapped[int] = mapped_column(Integer, default=0)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class XpLog(Base):
    __tablename__ = "xp_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class ExamAttempt(Base):
    """Imtihon urinishlari: yakuniy daraja imtihoni (kind='level', spec §12)
    va oraliq mini-imtihonlar (kind='mini', checkpoint=25/50/75)."""

    __tablename__ = "exam_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    level: Mapped[str] = mapped_column(String(4))
    kind: Mapped[str] = mapped_column(String(8), default="level")
    checkpoint: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    score_reading: Mapped[int] = mapped_column(Integer, default=0)
    score_listening: Mapped[int] = mapped_column(Integer, default=0)
    score_writing: Mapped[int] = mapped_column(Integer, default=0)
    score_speaking: Mapped[int] = mapped_column(Integer, default=0)
    total_score: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    questions_json: Mapped[str] = mapped_column(Text, default="{}")


class Certificate(Base):
    """Berilgan sertifikatlar (QR bilan tekshiriladi)."""

    __tablename__ = "certificates"

    id: Mapped[int] = mapped_column(primary_key=True)
    cert_id: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # "level" — daraja imtihoni sertifikati; "weekly" — haftalik reyting sovrini
    kind: Mapped[str] = mapped_column(String(8), default="level")
    level: Mapped[str] = mapped_column(String(4))
    score: Mapped[int] = mapped_column(Integer)
    scores_json: Mapped[str] = mapped_column(Text, default="{}")
    holder_name: Mapped[str] = mapped_column(String(128), default="")
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    png_path: Mapped[str] = mapped_column(String(256), default="")
    pdf_path: Mapped[str] = mapped_column(String(256), default="")
    revoked: Mapped[int] = mapped_column(Integer, default=0)


class Meta(Base):
    """Oddiy kalit-qiymat saqlash (deploy versiyasi va h.k.)."""

    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256), default="")


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


class Feedback(Base):
    """Foydalanuvchi fikr-mulohazasi (ilova yoki /fikr orqali)."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="app")  # app | bot
    context: Mapped[str] = mapped_column(String(64), default="")  # sahifa/dars
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class LessonRating(Base):
    """Dars oxiridagi 1-bosishli baho (👍 / 👎)."""

    __tablename__ = "lesson_ratings"
    __table_args__ = (
        UniqueConstraint("user_id", "lesson_id", name="uq_user_lesson_rating"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    lesson_id: Mapped[str] = mapped_column(String(16), index=True)
    rating: Mapped[int] = mapped_column(Integer)  # +1 (👍) yoki -1 (👎)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ClientError(Base):
    """Player/ilovada yuz bergan JS xatolari (diagnostika uchun)."""

    __tablename__ = "client_errors"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    message: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class WeeklyAward(Base):
    """Reyting sovrini: haftalik top-3 yoki oylik top-5.

    Bir davr uchun bir marta beriladi. `week_start` — davr kaliti:
    haftalik uchun dushanba sanasi "YYYY-MM-DD", oylik uchun "YYYY-MM".
    Ular hech qachon to'qnashmaydi (uzunligi farq qiladi), shuning uchun
    (user_id, week_start) unikal konstreynti ikkala davr uchun ham to'g'ri.
    """

    __tablename__ = "weekly_awards"
    __table_args__ = (UniqueConstraint("user_id", "week_start", name="uq_award_week"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    week_start: Mapped[str] = mapped_column(String(10), index=True)  # davr kaliti
    period: Mapped[str] = mapped_column(String(8), default="week")  # week | month
    rank: Mapped[int] = mapped_column(Integer)  # haftada 1-3, oyda 1-5
    weekly_xp: Mapped[int] = mapped_column(Integer, default=0)
    cert_id: Mapped[str] = mapped_column(String(24), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


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
    # v2 curriculum: foydalanuvchi kursni qaysi darsdan boshlaydi
    start_lesson: Mapped[str] = mapped_column(String(12), default="a0-01")
    # Daraja qaysi versiyadagi placement testi bilan aniqlangan (services/placement.py)
    placement_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
