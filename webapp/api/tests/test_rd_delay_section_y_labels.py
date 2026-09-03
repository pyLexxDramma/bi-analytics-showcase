# -*- coding: utf-8 -*-
"""Regression: Gantt «По разделу» не схлопывает строки с одним коротким Шифр."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from streamlit_stub import ensure_streamlit_stub

ensure_streamlit_stub()

CORE = Path(__file__).resolve().parents[3] / "bi-analytics-v-5-main"
sys.path.insert(0, str(CORE))

from dashboards._renderers import (  # noqa: E402
    _rd_delay_build_date_rows,
    _rd_delay_section_y_labels,
)


def _aupt_frame() -> pd.DataFrame:
    """Четыре раздела АУПТ с общим коротким шифром АПТ — как Дмитровский-1."""
    name = "Автоматическая установка пожаротушения"
    rows = []
    for full in (
        "37-ИЧ/24/1-АУПТ-D",
        "37-ИЧ/24/1-АУПТ-А",
        "37-ИЧ/24/1-АУПТ-U1,U2",
        "37-ИЧ/24/1-АУПТ-U3,U4",
    ):
        rows.append(
            {
                "Проект": "Дмитровский-1",
                "Шифр": "АПТ",
                "Шифр полный": full,
                "Наименование разделов работ": name,
                "Дата выдачи разделов по Договору": "30.08.2026",
                "Прогнозная дата выдачи разделов": "",
                "Дата выдачи в производство работ": "",
                "Статус": "Не выдано",
            }
        )
    return pd.DataFrame(rows)


def test_section_y_labels_unique_by_full_cipher() -> None:
    labels = _rd_delay_section_y_labels(_aupt_frame()).tolist()
    assert len(labels) == 4
    assert len(set(labels)) == 4
    assert all("АУПТ" in lb for lb in labels)


def test_delay_gantt_one_bar_per_full_cipher() -> None:
    gdf, y_col = _rd_delay_build_date_rows(
        _aupt_frame(),
        by_section=True,
        ts_report=pd.Timestamp("2026-09-03"),
        show_forecast=True,
    )
    assert y_col == "Раздел"
    assert len(gdf) == 4
    assert gdf["Раздел"].nunique() == 4
