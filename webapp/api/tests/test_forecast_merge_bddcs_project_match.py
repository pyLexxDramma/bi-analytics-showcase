# -*- coding: utf-8 -*-
"""Regression: merge БДДС 1С→лоты soft-match UI «Дмитровский» ↔ 1С «Дмитровский-1»."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from streamlit_stub import ensure_streamlit_stub

ensure_streamlit_stub()

CORE = Path(__file__).resolve().parents[3] / "bi-analytics-v-5-main"
sys.path.insert(0, str(CORE))

from dashboards import _renderers as ren  # noqa: E402


def _msp_lot_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ЛОТ": ["Лот №15. Козырьки"],
            "ЛОТ_ID": ["lot-15"],
            "budget plan": [0.0],
            "budget fact": [0.0],
        }
    )


def _turnover_child_project() -> pd.DataFrame:
    """Обороты 1С с child-именем проекта (как в снимке Дмитровский-1)."""
    return pd.DataFrame(
        [
            {
                "Проект": "Дмитровский-1",
                "Сценарий": "Бюджет",
                "СтатьяОборотов": "ЛОТ №15. Козырьки",
                "ТипСтатьи": "БДДС",
                "Сумма": 10_000_000.0,
                "ID_Лота": "lot-15",
            },
            {
                "Проект": "Дмитровский-1",
                "Сценарий": "Факт",
                "СтатьяОборотов": "ЛОТ №15. Козырьки",
                "ТипСтатьи": "БДДС",
                "Сумма": 4_000_000.0,
                "ID_Лота": "lot-15",
            },
        ]
    )


def test_merge_bddcs_soft_matches_parent_ui_to_child_1c(monkeypatch) -> None:
    monkeypatch.setattr(ren, "_forecast_find_turnover_dataframe", _turnover_child_project)
    out = ren._forecast_merge_bddcs_from_1c(_msp_lot_frame(), "Дмитровский")
    assert float(out["budget plan"].sum()) > 0.0
    assert float(out["budget fact"].sum()) > 0.0
    assert out.attrs.get("forecast_bddcs_injected_from_1c") is True


def test_merge_bddcs_exact_project_name_still_works(monkeypatch) -> None:
    monkeypatch.setattr(ren, "_forecast_find_turnover_dataframe", _turnover_child_project)
    out = ren._forecast_merge_bddcs_from_1c(_msp_lot_frame(), "Дмитровский-1")
    assert float(out["budget plan"].sum()) > 0.0
    assert float(out["budget fact"].sum()) > 0.0
