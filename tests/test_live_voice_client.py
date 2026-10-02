"""K30 — brauzer tomoni: mikrofon AudioWorklet'i (webapp/public/pcm-capture.js) 48/44.1 kHz → 16 kHz PCM16."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "tests" / "js" / "pcm_capture_runner.cjs"

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node yo'q")


def run(rate: int, seconds: float = 1.0, freq: float = 440.0) -> dict:
    r = subprocess.run(
        ["node", str(RUNNER)], input=json.dumps({"rate": rate, "seconds": seconds, "freq": freq}),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.parametrize("rate", [48000, 44100, 16000, 8000])
def test_resamples_to_16k_in_100ms_chunks(rate):
    out = run(rate)
    # 1 soniya → 16 000 namuna = 10 ta 100 ms bo'lak (oxirgi to'lmagani yuborilmaydi)
    assert out["chunks"] in (9, 10) and out["samples"] == out["chunks"] * 1600
    # 440 Hz sinus: soniyasiga ~880 marta nol kesishma (chastota buzilmagan, uzilish yo'q)
    assert abs(out["crossings"] / (out["samples"] / 16000) - 880) < 12
    # amplituda 0.5 → ~16 383; interpolyatsiya biroz kamaytirishi mumkin, lekin oshirmaydi
    assert 15000 < out["maxAbs"] <= 16400
    assert 0.3 < out["level"] < 0.4  # sinus RMS = 0.5/√2 ≈ 0.354
