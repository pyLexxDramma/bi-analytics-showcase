# -*- coding: utf-8 -*-
"""Regression: ключ сопоставления полного шифра РД (план ↔ TESSA InternalID)."""
from __future__ import annotations

import sys
from pathlib import Path

from streamlit_stub import ensure_streamlit_stub

ensure_streamlit_stub()

CORE = Path(__file__).resolve().parents[3] / "bi-analytics-v-5-main"
sys.path.insert(0, str(CORE))

from dashboards._renderers import _rd_cipher_match_key  # noqa: E402


def test_rd_cipher_match_key_aupt_block_and_hyphen_aliases() -> None:
    """АУПТ↔АПТ (сегмент), В→B, схлопывание «--», запятая→точка — один ключ."""
    pairs = (
        ("65-ХСА-1/24-АУПТ-А", "65-ХСА-1/24-АПТ-A"),
        ("65-ХСА-1/24-АУПТ-В", "65-ХСА-1/24-АПТ-B"),
        ("65-ХСА-1/24-АУПТ-С", "65-ХСА-1/24-АПТ-C"),
        ("65-ХСА-1/24-АУПТ-U1,U2", "65-ХСА-1/24-АПТ-U1.U2"),
        ("65-ХСА-1/24-ВК-В", "65-ХСА-1/24-ВК-B"),
        ("65-ХСА-1/24-КЖ1-А", "65-ХСА-1/24--КЖ1-A"),
        ("65-ХСА-1/24-ЭОМ-В", "65-ХСА-1/24-ЭОМ-B"),
    )
    for plan, tessa in pairs:
        assert _rd_cipher_match_key(plan) == _rd_cipher_match_key(tessa), (
            f"ожидался один ключ для {plan!r} и {tessa!r}"
        )


def test_rd_cipher_match_key_keeps_different_blocks_apart() -> None:
    """Разные буквы блока (и АУПТ/АПТ с разным блоком) не схлопываются."""
    assert _rd_cipher_match_key("65-ХСА-1/24-ВК-В") != _rd_cipher_match_key(
        "65-ХСА-1/24-ВК-C"
    )
    assert _rd_cipher_match_key("65-ХСА-1/24-ВК-В") != _rd_cipher_match_key(
        "65-ХСА-1/24-ВК-С"
    )
    assert _rd_cipher_match_key("65-ХСА-1/24-АУПТ-А") != _rd_cipher_match_key(
        "65-ХСА-1/24-АПТ-B"
    )


def test_rd_cipher_match_key_same_shape_cyrillic_latin_pairs() -> None:
    """Одинаковое начертание: кириллический суффикс и латинский дают один ключ."""
    pairs = (
        ("65-ХСА-1/24-АС5-А", "65-ХСА-1/24-АС5-A"),
        ("65-ХСА-1/24-АС5-В", "65-ХСА-1/24-АС5-B"),
        ("65-ХСА-1/24-АС5-Е", "65-ХСА-1/24-АС5-E"),
        ("65-ХСА-1/24-АС5-К", "65-ХСА-1/24-АС5-K"),
        ("65-ХСА-1/24-АС5-М", "65-ХСА-1/24-АС5-M"),
        ("65-ХСА-1/24-АС5-Н", "65-ХСА-1/24-АС5-H"),
        ("65-ХСА-1/24-АС5-О", "65-ХСА-1/24-АС5-O"),
        ("65-ХСА-1/24-АС5-Р", "65-ХСА-1/24-АС5-P"),
        ("65-ХСА-1/24-АС5-С", "65-ХСА-1/24-АС5-C"),
        ("65-ХСА-1/24-АС5-Т", "65-ХСА-1/24-АС5-T"),
        ("65-ХСА-1/24-АС5-У", "65-ХСА-1/24-АС5-Y"),
        ("65-ХСА-1/24-АС5-Х", "65-ХСА-1/24-АС5-X"),
        ("65-ХСА-1/24-АС5-І", "65-ХСА-1/24-АС5-I"),
    )
    for cyr, lat in pairs:
        assert _rd_cipher_match_key(cyr) == _rd_cipher_match_key(lat), (
            f"ожидался один ключ для {cyr!r} и {lat!r}"
        )


def test_rd_cipher_match_key_keeps_non_lookalike_letters_apart() -> None:
    """Разное начертание: П≠P, И≠N, У≠U, В≠V — ключи остаются разными."""
    pairs = (
        ("65-ХСА-1/24-АС5-П", "65-ХСА-1/24-АС5-P"),
        ("65-ХСА-1/24-АС5-И", "65-ХСА-1/24-АС5-N"),
        ("65-ХСА-1/24-АС5-У", "65-ХСА-1/24-АС5-U"),
        ("65-ХСА-1/24-АС5-В", "65-ХСА-1/24-АС5-V"),
    )
    for cyr, lat in pairs:
        assert _rd_cipher_match_key(cyr) != _rd_cipher_match_key(lat), (
            f"ожидались разные ключи для {cyr!r} и {lat!r}"
        )
