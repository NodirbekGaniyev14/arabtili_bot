"""Profil ismini o'zgartirish — tozalash va tekshirish."""

import pytest

from services.profile import NAME_MAX, clean_name, validate_name


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  Ali   Valiyev  ", "Ali Valiyev"),
        ("Ali\nValiyev", "Ali Valiyev"),
        ("Ali\tValiyev", "Ali Valiyev"),
        ("Zamira", "Zamira"),
        ("محمد", "محمد"),
    ],
)
def test_clean_name_normalizes_whitespace(raw, expected):
    assert clean_name(raw) == expected


def test_clean_name_strips_invisible_characters():
    """Zero-width va RTL override — reytingda taqlid uchun ishlatilishi mumkin."""
    assert clean_name("A​li‮") == "Ali"
    assert clean_name("﻿Ali") == "Ali"


def test_clean_name_truncates():
    assert len(clean_name("x" * 200)) == NAME_MAX


@pytest.mark.parametrize("raw", ["", " ", "A", "1", "123", "!!!", "​​"])
def test_invalid_names_rejected(raw):
    name, err = validate_name(raw)
    assert name == ""
    assert err


@pytest.mark.parametrize("raw", ["Ali", "Ali Valiyev", "محمد", "O'ktam"])
def test_valid_names_accepted(raw):
    name, err = validate_name(raw)
    assert err == ""
    assert name == raw
