# -*- coding: utf-8 -*-
"""Строения: нормализация площади + матч короткого/полного имени."""
from __future__ import annotations

import pandas as pd

from app.services import baseline_deviation as bd
from app.services.deviation_reasons import (
    _apply_building_slice,
    _building_base_key,
    _pick_building_label,
    _unique_building_labels,
)


def test_building_base_key_strips_area() -> None:
    assert _building_base_key("Блок В") == _building_base_key("Блок В (19 437 м2)")
    assert _building_base_key("Блок U1. U2 (5 000 м2)") == _building_base_key("Блок U1. U2")
    assert _building_base_key("Блок А (29 000 м2)") == _building_base_key("Блок А")
    assert _building_base_key("Блок U1. U2 (5 000 м2)") == _building_base_key("Блок U1U2")
    assert _building_base_key("Блок U3. U4 (5 000 м2)") == _building_base_key("Блок U3U4")
    # Паритет с экраном «Отклонение от БП».
    assert bd._building_base_key("Блок В") == bd._building_base_key("Блок В (13 947 м2)")
    assert bd._building_base_key("Блок Асц") == bd._building_base_key("Блок Асц (1 500 м2)")


def test_unique_building_labels_prefers_full_msp_name() -> None:
    raw = [
        "Блок В",
        "Блок В (19 437 м2)",
        "Блок В",
        "Блок А",
        "Блок А (100 м2)",
        "Блок U1U2",
        "Блок U1. U2 (5 000 м2)",
    ]
    expected = [
        "Блок U1. U2 (5 000 м2)",
        "Блок А (100 м2)",
        "Блок В (19 437 м2)",
    ]
    assert _unique_building_labels(raw) == expected
    assert bd._unique_building_labels(raw) == expected


def test_pick_building_label_matches_short_or_full() -> None:
    available = ["Все", "Блок В (19 437 м2)", "Блок А (100 м2)"]
    assert _pick_building_label("Блок В", available) == "Блок В (19 437 м2)"
    assert _pick_building_label("Блок В (19 437 м2)", available) == "Блок В (19 437 м2)"
    assert bd._pick_building_label("Блок В", available) == "Блок В (19 437 м2)"


def test_apply_building_slice_matches_both_forms() -> None:
    df = pd.DataFrame(
        [
            {"level": 2.0, "task name": "СМР"},
            {"level": 3.0, "task name": "Блок В"},
            {"level": 5.0, "task name": "Работа 1"},
            {"level": 3.0, "task name": "Блок В (19 437 м2)"},
            {"level": 5.0, "task name": "Работа 2"},
            {"level": 3.0, "task name": "Блок А"},
            {"level": 5.0, "task name": "Работа 3"},
        ]
    )
    for apply in (_apply_building_slice, bd._apply_building_slice):
        sliced = apply(
            df, building="Блок В (19 437 м2)", level_col="level", task_col="task name"
        )
        names = sliced["task name"].tolist()
        assert "Блок В" in names
        assert "Блок В (19 437 м2)" in names
        assert "Работа 1" in names
        assert "Работа 2" in names
        assert "Блок А" not in names
        assert "Работа 3" not in names
