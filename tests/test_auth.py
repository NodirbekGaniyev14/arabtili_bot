"""Telegram initData tekshiruvi: imzo, muddat va DEV_AUTH qulfi."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from services.telegram_auth import MAX_AUTH_AGE_SECONDS, validate_init_data

TOKEN = "123456:TEST-TOKEN-FOR-UNIT-TESTS"


def make_init_data(token: str = TOKEN, auth_date: int | None = None, **extra) -> str:
    """Haqiqiy Telegram algoritmi bo'yicha to'g'ri imzolangan initData."""
    fields = {
        "user": json.dumps({"id": 42, "first_name": "Ali"}),
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        **extra,
    }
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


# ── Imzo ──


def test_valid_signature_returns_user():
    user = validate_init_data(make_init_data(), TOKEN)
    assert user is not None
    assert user["id"] == 42


def test_wrong_token_rejected():
    assert validate_init_data(make_init_data(), "999:OTHER-TOKEN") is None


def test_tampered_payload_rejected():
    """Imzo saqlanib, user o'zgartirilsa — rad etiladi."""
    data = make_init_data()
    tampered = data.replace("%2242%22", "%229999%22").replace("42", "9999", 1)
    assert validate_init_data(tampered, TOKEN) is None


def test_missing_hash_rejected():
    assert validate_init_data("user=%7B%22id%22%3A1%7D", TOKEN) is None


def test_garbage_input_rejected():
    for junk in ("", "????", "hash=", "a=b&c=d"):
        assert validate_init_data(junk, TOKEN) is None


# ── Muddat ──


def test_expired_auth_date_rejected():
    old = int(time.time()) - MAX_AUTH_AGE_SECONDS - 60
    assert validate_init_data(make_init_data(auth_date=old), TOKEN) is None


def test_just_within_expiry_accepted():
    fresh = int(time.time()) - MAX_AUTH_AGE_SECONDS + 120
    assert validate_init_data(make_init_data(auth_date=fresh), TOKEN) is not None


def test_far_future_auth_date_rejected():
    """Soat farqi uchun kichik zaxira bor, lekin bir soat oldinga — yo'q."""
    future = int(time.time()) + 3600
    assert validate_init_data(make_init_data(auth_date=future), TOKEN) is None


def test_small_clock_skew_tolerated():
    assert validate_init_data(
        make_init_data(auth_date=int(time.time()) + 60), TOKEN
    ) is not None


def test_non_numeric_auth_date_rejected():
    assert validate_init_data(make_init_data(auth_date="abc"), TOKEN) is None


def test_missing_auth_date_rejected():
    """auth_date yo'q = 0 = juda eski."""
    fields = {"user": json.dumps({"id": 1})}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    assert validate_init_data(urlencode(fields), TOKEN) is None


# ── DEV_AUTH qulfi ──


@pytest.mark.parametrize(
    "dev_auth,token,expected",
    [
        (True, "", True),        # lokal: token yo'q → dev rejim ishlaydi
        (True, "123:ABC", False),  # PROD: token bor → majburan o'chiq
        (False, "", False),
        (False, "123:ABC", False),
        (True, "   ", True),       # bo'sh joy = token yo'q
    ],
)
def test_dev_auth_only_without_bot_token(monkeypatch, dev_auth, token, expected):
    """DEV_AUTH prod'da (token bor joyda) hech qachon faollashmasin."""
    import config

    monkeypatch.setattr(config.settings, "dev_auth", dev_auth)
    monkeypatch.setattr(config.settings, "bot_token", token)
    assert config.dev_auth_active() is expected
