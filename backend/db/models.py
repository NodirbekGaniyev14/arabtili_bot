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
    # VIP tarif (AI ustoz) qachongacha faol; None = hech qachon olmagan
    vip_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Paywall birinchi ochilgan vaqt — chegirma taymeri shundan hisoblanadi
    paywall_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # K17.4 eslatmalar (services/vip_reminders.py): oxirgi yuborilgan VIP xabari
    # kaliti ("soon:<vip_until>" | "expired:<vip_until>") va chegirma xabari flagi
    vip_notice: Mapped[str] = mapped_column(String(24), default="")
    discount_notified: Mapped[int] = mapped_column(Integer, default=0)
    # K18.1 taklif va sinov (services/referral.py): kim taklif qilgan (users.id),
    # taklif mukofoti berilganmi, bir martalik VIP sinov oxiri
    invited_by: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ref_rewarded: Mapped[int] = mapped_column(Integer, default=0)
    trial_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # K18.4 haftalik speaking hisoboti (services/speaking_report.py): oxirgi
    # yuborilgan hafta kaliti (dushanba sanasi) — bir hafta uchun bir marta
    speak_report_key: Mapped[str] = mapped_column(String(10), default="")
    # K19.2 yozuv mashqi eslatmasi: oxirgi yuborilgan davr kaliti (2 kunlik)
    writing_notice: Mapped[str] = mapped_column(String(10), default="")
    # K20.1 qaytarish ketma-ketligi (services/winback.py): oxirgi yuborilgan bosqich
    # (3/7/30 kun) va vaqti; foydalanuvchi qaytsa bosqich nolga qaytadi
    winback_stage: Mapped[int] = mapped_column(Integer, default=0)
    winback_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # K20.4 ro'yxatdan o'tgan kunning ertasiga bitta xabar yuborildimi
    day2_notice: Mapped[int] = mapped_column(Integer, default=0)
    # K22.1 reja tuzilgan kuni 2 soat o'tib dars boshlanmagan — birinchi dars turtkisi (bir marta)
    first_nudge: Mapped[int] = mapped_column(Integer, default=0)


class Placement(Base):
    """Onboarding anketasi va mini-test natijalari (xom holda)."""

    __tablename__ = "placements"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    answers_json: Mapped[str] = mapped_column(Text, default="{}")
    test_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Progress(Base):
    """Dars urinishlari (har urinish alohida yozuv).

    `passed` — mikro-test 60% dan yuqori bo'lganmi. Faqat `passed=1` yozuvi
    darsni TUGATILGAN qiladi (keyingi darsni ochadi); yiqilgan urinish ham
    saqlanadi, chunki urinish soni qayta topshirishda boshqa savollar
    tanlash uchun ishlatiladi (services/lesson_test.py).
    """

    __tablename__ = "progress"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    lesson_id: Mapped[str] = mapped_column(String(64), index=True)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    xp_earned: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=1)
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
    # Admin javobi — faqat fikr egasiga DM qilinadi, anonim ("Arabiy jamoasi")
    reply_text: Mapped[str] = mapped_column(Text, default="")
    replied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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
    # Sovrin sifatida berilgan VIP kunlari (0 = faqat sertifikat)
    vip_days: Mapped[int] = mapped_column(Integer, default=0)
    period: Mapped[str] = mapped_column(String(8), default="week")  # week | month
    rank: Mapped[int] = mapped_column(Integer)  # haftada 1-3, oyda 1-5
    weekly_xp: Mapped[int] = mapped_column(Integer, default=0)
    cert_id: Mapped[str] = mapped_column(String(24), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TutorTurn(Base):
    """AI ustoz suhbatidagi bitta o'quvchi javobi (services/tutor.py).

    Har javob alohida qator: kunlik limit shu yerdan sanaladi, suhbat
    yakunida XP `session_key` bo'yicha hisoblanadi. Suhbat matni
    saqlanmaydi — faqat baho (ok) va kirish turi (voice).
    """

    __tablename__ = "tutor_turns"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    session_key: Mapped[str] = mapped_column(String(36), index=True)
    topic: Mapped[str] = mapped_column(String(24), default="")
    level: Mapped[str] = mapped_column(String(4), default="")
    ok: Mapped[int] = mapped_column(Integer, default=1)  # xatosiz javob = 1
    voice: Mapped[int] = mapped_column(Integer, default=0)  # mikrofon orqali = 1
    mode: Mapped[str] = mapped_column(String(8), default="chat")  # chat | mock
    score: Mapped[int] = mapped_column(Integer, default=-1)  # mock: javob bali 0-100
    # Mock mezonlari (K17.6): lug'at / grammatika / mazmun-ravonlik (LLM),
    # talaffuz-aniqlik (STT ishonchi); -1 = o'lchanmagan
    vocab: Mapped[int] = mapped_column(Integer, default=-1)
    grammar: Mapped[int] = mapped_column(Integer, default=-1)
    content: Mapped[int] = mapped_column(Integer, default=-1)
    pron: Mapped[int] = mapped_column(Integer, default=-1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class MockResult(Base):
    """Speaking mock imtihoni natijasi (services/tutor.py MOCKS)."""

    __tablename__ = "mock_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    mock_id: Mapped[str] = mapped_column(String(24))
    level: Mapped[str] = mapped_column(String(4), default="")
    score: Mapped[int] = mapped_column(Integer)  # 0-100 o'rtacha
    vocab: Mapped[int] = mapped_column(Integer, default=-1)
    grammar: Mapped[int] = mapped_column(Integer, default=-1)
    content: Mapped[int] = mapped_column(Integer, default=-1)
    pron: Mapped[int] = mapped_column(Integer, default=-1)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    session_key: Mapped[str] = mapped_column(String(36), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PaymentRequest(Base):
    """VIP to'lov cheki — foydalanuvchi yuklaydi, admin Telegram'da tasdiqlaydi."""

    __tablename__ = "payment_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan: Mapped[str] = mapped_column(String(8))  # 1oy | 3oy
    amount: Mapped[int] = mapped_column(Integer, default=0)
    receipt_path: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|approved|rejected
    days: Mapped[int] = mapped_column(Integer, default=0)  # tasdiqlangan muddat
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # K18.5 avto to'lov (services/payments.py): receipt (chek) | telegram (Payme/Click);
    # Telegram va provayder tranzaksiya ID'lari — takror update va qaytarish uchun
    provider: Mapped[str] = mapped_column(String(12), default="receipt")
    charge_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    provider_charge_id: Mapped[str] = mapped_column(String(64), default="")


class TutorMistake(Base):
    """Xatolar daftari (K17.5): ustoz tuzatgan jumla yoki past baholangan mock
    javobi — o'quvchi keyin ko'rib, eshitib, qayta aytib mashq qiladi."""

    __tablename__ = "tutor_mistakes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8), default="chat")  # chat | mock
    topic: Mapped[str] = mapped_column(String(24), default="")
    said_ar: Mapped[str] = mapped_column(String(400), default="")
    fixed_ar: Mapped[str] = mapped_column(String(400), default="")
    note_uz: Mapped[str] = mapped_column(String(400), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class DrillResult(Base):
    """Talaffuz mashqi yakuni (K17.5): mavzu bo'yicha o'rtacha o'xshashlik bali."""

    __tablename__ = "drill_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    topic: Mapped[str] = mapped_column(String(24), default="")
    level: Mapped[str] = mapped_column(String(4), default="")
    score: Mapped[int] = mapped_column(Integer)  # 0-100
    count: Mapped[int] = mapped_column(Integer, default=0)  # aytilgan jumlalar
    xp: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class DailySpeaking(Base):
    """Kunlik speaking savoli javobi (services/daily.py) — kuniga bitta, streak."""

    __tablename__ = "daily_speaking"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_daily_user_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    day: Mapped[str] = mapped_column(String(10), index=True)  # Toshkent sanasi YYYY-MM-DD
    question_id: Mapped[str] = mapped_column(String(12), default="")
    level: Mapped[str] = mapped_column(String(4), default="")
    score: Mapped[int] = mapped_column(Integer, default=0)
    voice: Mapped[int] = mapped_column(Integer, default=0)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    answer: Mapped[str] = mapped_column(String(400), default="")
    feedback: Mapped[str] = mapped_column(String(400), default="")
    ideal: Mapped[str] = mapped_column(String(400), default="")
    fixed: Mapped[str] = mapped_column(String(400), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Testimonial(Base):
    """Paywall'dagi haqiqiy fikrlar — foydalanuvchi bot orqali ROZILIK bergan
    fikr (services/feedback.py + bot/admin.py /sharh)."""

    __tablename__ = "testimonials"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    feedback_id: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(64), default="")
    level: Mapped[str] = mapped_column(String(4), default="")
    text: Mapped[str] = mapped_column(String(400), default="")
    published: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ListeningResult(Base):
    """Tinglab tushunish yakuni (K18.3): mavzu + rejim (choice|dictation) bo'yicha o'rtacha."""

    __tablename__ = "listening_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    topic: Mapped[str] = mapped_column(String(24), default="")
    kind: Mapped[str] = mapped_column(String(10), default="choice")
    level: Mapped[str] = mapped_column(String(4), default="")
    score: Mapped[int] = mapped_column(Integer)
    count: Mapped[int] = mapped_column(Integer, default=0)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class TraceResult(Base):
    """Harf chizish mashqi yakuni (K21.6): sessiyadagi harflar ballari (JSON {harf: 0-100})."""

    __tablename__ = "trace_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    scores: Mapped[str] = mapped_column(Text, default="{}")
    avg: Mapped[int] = mapped_column(Integer, default=0)
    count: Mapped[int] = mapped_column(Integer, default=0)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class WritingResult(Base):
    """K19.2 yozuv (xattotlik) mashqi — davr (2 kun) + foydalanuvchi uchun bitta yozuv:
    eng yaxshi ball, ozodalik, urinishlar soni, oxirgi eng yaxshi tekshiruv (JSON), XP."""

    __tablename__ = "writing_results"
    __table_args__ = (UniqueConstraint("user_id", "period", name="uq_writing_period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    period: Mapped[str] = mapped_column(String(10), index=True)  # davr boshi YYYY-MM-DD
    text_id: Mapped[str] = mapped_column(String(12), default="")
    level: Mapped[str] = mapped_column(String(4), default="")
    score: Mapped[int] = mapped_column(Integer, default=0)  # eng yaxshi aniqlik 0-100
    neatness: Mapped[int] = mapped_column(Integer, default=0)  # 1-5
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    feedback: Mapped[str] = mapped_column(Text, default="")  # JSON: read_ar, wrong_words, tips_uz…
    xp: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TutorRating(Base):
    """Sifat halqasi (K18.2): suhbat/mock/kunlik savol/talaffuz yakunida 👍/👎.
    Suhbat matni saqlanmaydi — bu yagona sifat signali. Har sessiya uchun bitta."""

    __tablename__ = "tutor_ratings"
    __table_args__ = (UniqueConstraint("user_id", "session_key", name="uq_rating_user_session"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    session_key: Mapped[str] = mapped_column(String(36))
    mode: Mapped[str] = mapped_column(String(8), default="chat")  # chat|mock|daily|drill
    topic: Mapped[str] = mapped_column(String(24), default="")
    level: Mapped[str] = mapped_column(String(4), default="")
    good: Mapped[int] = mapped_column(Integer, default=1)  # 1 👍 / 0 👎
    comment: Mapped[str] = mapped_column(String(400), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AiUsage(Base):
    """Har bir Claude chaqiruvining token hisobi (services/ai_usage.py).

    Admin `/ustoz` buyrug'i shu yerdan kunlik/oylik $ sarfini hisoblaydi —
    kredit qachon tugashini oldindan ko'rish uchun. Matn saqlanmaydi.
    """

    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    feature: Mapped[str] = mapped_column(String(12))  # tutor|mock|roleplay|writing|onboarding
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cache_read: Mapped[int] = mapped_column(Integer, default=0)
    cache_write: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


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
