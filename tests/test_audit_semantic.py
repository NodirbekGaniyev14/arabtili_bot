"""K29.5 — kontentning MA'NO auditi (scripts/audit_semantic.py): audio ↔ javob muvofiqligi, ma'nodosh variantlar,
ovozi yaqin harflar uchun izoh (#F160: خَاء eshitilib ح tanlandi — nega xato ekani ko'rsatilmagan edi)."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("audit_semantic", ROOT / "scripts" / "audit_semantic.py")
audit_semantic = importlib.util.module_from_spec(_spec)
sys.modules["audit_semantic"] = audit_semantic
_spec.loader.exec_module(audit_semantic)

RES = audit_semantic.audit()


def test_audio_matches_answer_everywhere():
    assert RES["audio-javob"] == []


def test_no_duplicate_meaning_options():
    assert RES["dup-meaning"] == []


def test_confusable_letter_listening_has_notes():
    """Ovozi yaqin harflar (خ/ح, س/ش, ع/غ…) birga kelgan tinglash savolida xato variant izohi bo'lishi shart."""
    assert RES["letter-pairs"] == []


def test_letter_notes_are_in_exam_pool_and_name_both_letters():
    import json

    pool = json.loads((ROOT / "content" / "exams" / "a0_pool.json").read_text(encoding="utf-8"))
    item = next(i for i in pool["listening"] if i.get("audio") == "a0/harf_kha.mp3")
    note = item["option_notes"]["ح"]
    assert "ḥā'" in note and "«خ»" in note and "xā'" in note
    assert set(item["option_notes"]) <= set(item["options"]) - {item["answer"]}
