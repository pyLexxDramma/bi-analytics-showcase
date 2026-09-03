# -*- coding: utf-8 -*-
"""Regression: ЗОС-плашки не обнуляются фильтром блока СМР (Доработки 02.09 п.6)."""
from __future__ import annotations

import pandas as pd

from app.services.baseline_deviation import _pick_metric_row


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "project name": "Дмитровский",
                "task name": "ЗОС",
                "block": "Прочее",
                "base end": pd.Timestamp("2027-06-30"),
                "plan end": pd.Timestamp("2027-08-15"),
            },
            {
                "project name": "Дмитровский",
                "task name": "СМР блок А",
                "block": "СМР",
                "base end": pd.Timestamp("2026-12-01"),
                "plan end": pd.Timestamp("2026-11-01"),
            },
        ]
    )


def test_zos_missing_in_smr_block_present_in_project_scope() -> None:
    df = _frame()
    smr = df.loc[df["block"].astype(str).str.casefold() == "смр"].copy()
    project = df.copy()
    assert _pick_metric_row(smr, "task name", "ЗОС") is None
    zrow = _pick_metric_row(project, "task name", "ЗОС")
    assert zrow is not None
    assert str(zrow.get("task name")) == "ЗОС"
    assert pd.notna(zrow.get("base end"))
    assert pd.notna(zrow.get("plan end"))
