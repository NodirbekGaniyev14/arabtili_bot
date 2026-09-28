"""Audio yaxlitligi: bir fayl = bir matn, hamma fayl mavjud va dolzarb.

Tarix: `build_audio.py` mavjud faylni o'tkazib yuborardi va bitta nomga bir
nechta matn biriktirilsa jimgina birinchisini olardi. Natijada darslar boshqa
harfning ovozini chalgan (masalan `a0/harf_ba.mp3` "بَاء" o'rniga "بُ").
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "webapp" / "public" / "audio"

_spec = importlib.util.spec_from_file_location(
    "build_audio", ROOT / "content" / "build_audio.py"
)
build_audio = importlib.util.module_from_spec(_spec)
sys.modules["build_audio"] = build_audio
_spec.loader.exec_module(build_audio)


def test_no_filename_conflicts():
    """Bitta mp3 nomiga ikki xil matn biriktirilmagan."""
    conflicts = build_audio.find_conflicts()
    assert not conflicts, "bir nomga bir nechta matn: " + "; ".join(
        f"{n} -> {sorted(t)}" for n, t in sorted(conflicts.items())
    )


def test_every_referenced_file_exists():
    missing = [n for n in build_audio.collect() if not (AUDIO_DIR / n).exists()]
    assert not missing, f"{len(missing)} ta audio yo'q: {missing[:10]}"


def test_no_truncated_audio():
    """#F122: yarim saqlangan fayl (vocab/jazar.mp3 2 KB, 0.3 s) — «talaffuz xato» deb ko'rinadi."""
    dist = ROOT / "webapp" / "dist" / "audio"
    small = [
        f"{d.name}/{n}"
        for n in build_audio.collect()
        for d in (AUDIO_DIR, dist)
        if (d / n).exists() and (d / n).stat().st_size < build_audio.MIN_BYTES
    ]
    assert not small, f"kesilgan audio: {small[:10]} — `python content/build_audio.py` qayta yaratadi"


def test_is_stale_detects_truncated_file(tmp_path, monkeypatch):
    monkeypatch.setattr(build_audio, "OUT_DIR", tmp_path)
    text = "جَزَر"
    manifest = {"v.mp3": build_audio._key(text)}
    assert build_audio.is_stale("v.mp3", text, manifest), "fayl yo'q"
    (tmp_path / "v.mp3").write_bytes(b"x" * 2160)
    assert build_audio.is_stale("v.mp3", text, manifest), "kesilgan (MIN_BYTES dan kichik)"
    (tmp_path / "v.mp3").write_bytes(b"x" * 14400)
    assert not build_audio.is_stale("v.mp3", text, manifest)
    assert build_audio.is_stale("v.mp3", text + "ٌ", manifest), "matn o'zgargan"


def test_manifest_matches_content():
    """Dars matni o'zgargan bo'lsa audio ham qayta yaratilgan bo'lishi kerak."""
    manifest = build_audio.load_manifest()
    stale = [
        n
        for n, text in build_audio.collect().items()
        if manifest.get(n) != build_audio._key(text)
    ]
    assert not stale, (
        f"{len(stale)} ta audio eskirgan — `python content/build_audio.py` ishlating: "
        f"{stale[:10]}"
    )


def test_no_empty_or_latin_audio_text():
    """Arabcha ovoz uchun matn arab yozuvida bo'lishi shart."""
    bad = [
        (n, t)
        for n, t in build_audio.collect().items()
        if not any("؀" <= ch <= "ۿ" for ch in t)
    ]
    assert not bad, f"arabcha bo'lmagan audio matn: {bad[:10]}"


@pytest.mark.parametrize(
    "name,expected",
    [
        ("a0/harf_ba.mp3", "بَاء"),
        ("a0/harf_ta.mp3", "تَاء"),
        ("a0/harf_tha.mp3", "ثَاء"),
        ("a0/harf_ha.mp3", "حَاء"),
        ("a0/harf_haa.mp3", "هَاء"),
        ("a0/harf_jim.mp3", "جِيم"),
        ("a0/harf_kha.mp3", "خَاء"),
        ("a0/harf_dal.mp3", "دَال"),
        ("a0/harf_dhal.mp3", "ذَال"),
        ("a0/harf_sad.mp3", "صَاد"),
        ("a0/harf_sin.mp3", "سِين"),
        ("a0/harf_tah.mp3", "طَاء"),
        ("a0/harf_zah.mp3", "ظَاء"),
        ("a0/harf_ayn.mp3", "عَيْن"),
        ("a0/harf_ghayn.mp3", "غَيْن"),
    ],
)
def test_letter_audio_says_its_own_name(name, expected):
    """Harf fayli o'z nomini aytadi — qo'shni harfnikini emas."""
    assert build_audio.collect().get(name) == expected
