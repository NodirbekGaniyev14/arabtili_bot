"""Streak va muzlatkich (streak freeze) mantiqini tekshirish."""

from datetime import date, timedelta

from services.stats import MAX_FREEZES, resolve_streak

TODAY = date(2026, 7, 22)  # chorshanba


def days_back(*offsets: int) -> set[date]:
    return {TODAY - timedelta(days=n) for n in offsets}


async def test_unbroken_chain_counts_all_days(session, make_user):
    user = await make_user()
    streak, _ = await resolve_streak(session, user.id, days_back(0, 1, 2, 3), TODAY)
    assert streak == 4


async def test_no_activity_gives_zero(session, make_user):
    user = await make_user()
    streak, _ = await resolve_streak(session, user.id, set(), TODAY)
    assert streak == 0


async def test_yesterday_only_still_counts(session, make_user):
    """Bugun hali mashq qilmagan bo'lsa ham kechagi streak yo'qolmaydi."""
    user = await make_user()
    streak, _ = await resolve_streak(session, user.id, days_back(1, 2), TODAY)
    assert streak == 2


async def test_freeze_covers_single_missed_day(session, make_user):
    """0,1 va 3-kunlar faol; 2-kun o'tkazib yuborilgan — muzlatkich yopadi."""
    user = await make_user()
    streak, left = await resolve_streak(session, user.id, days_back(0, 1, 3, 4), TODAY)
    assert streak == 4  # muzlatilgan kun sanoqqa kirmaydi, zanjir uzilmaydi
    assert left == MAX_FREEZES - 1
    assert (TODAY - timedelta(days=2)).isoformat() in user.frozen_days


async def test_freeze_is_not_reconsumed_on_second_call(session, make_user):
    """Ilova qayta ochilganda o'sha kun uchun yana muzlatkich yechilmaydi."""
    user = await make_user()
    active = days_back(0, 1, 3, 4)
    s1, left1 = await resolve_streak(session, user.id, active, TODAY)
    s2, left2 = await resolve_streak(session, user.id, active, TODAY)
    assert s1 == s2
    assert left1 == left2


async def test_two_missed_days_break_streak_when_freezes_exhausted(session, make_user):
    """2 ta muzlatkich birinchi bo'shliqni yopadi, ikkinchisiga yetmaydi."""
    user = await make_user()
    # 0 faol; 1,2 bo'sh (2 muzlatkich); 3 faol; 4,5 bo'sh; 6 faol
    active = days_back(0, 3, 6)
    streak, left = await resolve_streak(session, user.id, active, TODAY)
    assert left == 0
    assert streak == 2  # bugun + 3-kun; 4/5-kunlarni yopishga muzlatkich qolmadi


async def test_freeze_never_consumed_for_today(session, make_user):
    """Bugun hali tugamagan — uni muzlatish mumkin emas."""
    user = await make_user()
    streak, left = await resolve_streak(session, user.id, days_back(1, 2), TODAY)
    assert streak == 2
    assert left == MAX_FREEZES


async def test_no_freeze_spent_when_user_absent_today(session, make_user):
    """Bugun kirmagan odamning zaxirasi yoqilmaydi — hali ulgurishi mumkin."""
    user = await make_user()
    # kecha ham bo'sh, 2 kun oldin faol — bugun kelmagan
    streak, left = await resolve_streak(session, user.id, days_back(2, 3), TODAY)
    assert left == MAX_FREEZES
    assert user.frozen_days == ""


async def test_gap_larger_than_reserve_spends_nothing(session, make_user):
    """5 kunlik tanaffusni 2 muzlatkich yopolmaydi — behuda sarflanmaydi."""
    user = await make_user()
    streak, left = await resolve_streak(session, user.id, days_back(0, 6), TODAY)
    assert streak == 1  # faqat bugun
    assert left == MAX_FREEZES
    assert user.frozen_days == ""


async def test_two_day_gap_covered_by_both_freezes(session, make_user):
    """Ketma-ket 2 kun tanaffus — ikkala muzlatkich ishlatiladi, zanjir tirik."""
    user = await make_user()
    streak, left = await resolve_streak(session, user.id, days_back(0, 3, 4), TODAY)
    assert streak == 3
    assert left == 0


async def test_weekly_grant_tops_up_but_caps(session, make_user):
    user = await make_user(streak_freezes=0, freeze_granted_week="2026-07-13")
    _, left = await resolve_streak(session, user.id, days_back(0), TODAY)
    assert left == 1  # +1 berildi
    assert user.freeze_granted_week == "2026-07-20"  # shu hafta dushanbasi

    # Ayni haftada ikkinchi chaqiruv qo'shimcha bermaydi
    _, left2 = await resolve_streak(session, user.id, days_back(0), TODAY)
    assert left2 == 1


async def test_grant_does_not_exceed_max(session, make_user):
    user = await make_user(streak_freezes=MAX_FREEZES, freeze_granted_week="")
    _, left = await resolve_streak(session, user.id, days_back(0), TODAY)
    assert left == MAX_FREEZES


async def test_freeze_not_wasted_before_first_active_day(session, make_user):
    """Ro'yxatdan o'tishdan oldingi kunlarga muzlatkich sarflanmaydi."""
    user = await make_user()
    _, left = await resolve_streak(session, user.id, days_back(0), TODAY)
    assert left == MAX_FREEZES
