"""K28.3 — Sonnet 5 → Sonnet 5.5: VIP suhbat/mock va qo'lyozma o'qish modeli.

Standart yangi avlod; serverdagi .env da eski `claude-sonnet-5` qolgan bo'lsa kod uni o'zi yangilaydi
(server faylini men o'zgartira olmayman) va /tekshir «.env ni yangilang» deb ogohlantiradi.
Bepul o'quvchilar hamda kunlik savol / yozuv / onboarding / rol o'yini Haiku'da qoladi.
"""

import pytest

import config


def _fresh(monkeypatch, **env):
    for k in ("TUTOR_VIP_MODEL", "WRITING_MODEL", "TUTOR_MODEL"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    config.UPGRADED.clear()
    return config.Settings(_env_file=None)


@pytest.fixture(autouse=True)
def _restore_upgraded():
    before = dict(config.UPGRADED)
    yield
    config.UPGRADED.clear()
    config.UPGRADED.update(before)


def test_defaults_are_sonnet_5_5_only_for_vip_and_handwriting(monkeypatch):
    s = _fresh(monkeypatch)
    assert s.tutor_vip_model == "claude-sonnet-5-5" and s.writing_model == "claude-sonnet-5-5"
    assert s.tutor_model.startswith("claude-haiku-4-5"), "bepul o'quvchilar va kunlik savol — Haiku"
    assert not config.UPGRADED


def test_legacy_sonnet_5_in_env_is_upgraded(monkeypatch, caplog):
    with caplog.at_level("WARNING", logger="config"):
        s = _fresh(monkeypatch, TUTOR_VIP_MODEL="claude-sonnet-5", WRITING_MODEL="claude-sonnet-5")
    assert s.tutor_vip_model == s.writing_model == "claude-sonnet-5-5"
    assert config.UPGRADED == {
        "TUTOR_VIP_MODEL": ("claude-sonnet-5", "claude-sonnet-5-5"),
        "WRITING_MODEL": ("claude-sonnet-5", "claude-sonnet-5-5"),
    }
    assert "TUTOR_VIP_MODEL=claude-sonnet-5 eski avlod" in caplog.text


def test_explicit_choices_are_respected(monkeypatch):
    # bo'sh = VIP'da ham Haiku (o'chirish usuli); boshqa modellar tegilmaydi
    s = _fresh(monkeypatch, TUTOR_VIP_MODEL="", WRITING_MODEL="claude-haiku-4-5-20251001")
    assert s.tutor_vip_model == "" and s.writing_model == "claude-haiku-4-5-20251001" and not config.UPGRADED
    assert _fresh(monkeypatch, TUTOR_VIP_MODEL="claude-opus-5-5").tutor_vip_model == "claude-opus-5-5"
    # aniq eski nom faqat ROSA «claude-sonnet-5» — boshqa avlodlar tegilmaydi
    assert _fresh(monkeypatch, TUTOR_VIP_MODEL="claude-sonnet-4-6").tutor_vip_model == "claude-sonnet-4-6"


def test_env_example_matches_defaults():
    from pathlib import Path

    text = (Path(__file__).resolve().parent.parent / ".env.example").read_text(encoding="utf-8")
    assert "TUTOR_VIP_MODEL=claude-sonnet-5-5" in text and "WRITING_MODEL=claude-sonnet-5-5" in text
    assert "claude-sonnet-5 " not in text and "claude-sonnet-5\n" not in text, "eski avlod nomi qolmasin"


def test_only_vip_gets_the_stronger_model(monkeypatch):
    from services import tutor

    monkeypatch.setattr(config.settings, "tutor_vip_model", "claude-sonnet-5-5")
    assert tutor.model_for(True) == "claude-sonnet-5-5"
    assert tutor.model_for(False) == config.settings.tutor_model


def test_diag_warns_when_env_is_stale(monkeypatch):
    from services import diag

    monkeypatch.setitem(config.UPGRADED, "TUTOR_VIP_MODEL", ("claude-sonnet-5", "claude-sonnet-5-5"))
    lines = diag.check_settings()
    stale = [ln for ln in lines if "TUTOR_VIP_MODEL=claude-sonnet-5 → claude-sonnet-5-5" in ln]
    assert stale and "⚠" in stale[0], lines
    assert any("Qo'lyozma o'qish modeli" in ln for ln in lines)


def test_prices_cover_both_generations():
    from services import ai_usage

    same = {"in": 2.0, "out": 10.0, "cache_read": 0.2, "cache_write": 2.5}
    assert ai_usage.prices_for("claude-sonnet-5-5") == same == ai_usage.prices_for("claude-sonnet-5")
    assert ai_usage.short_model("claude-sonnet-5-5") == "Sonnet 5.5"
