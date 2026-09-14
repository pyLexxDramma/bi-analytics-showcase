# -*- coding: utf-8 -*-
"""Период date_from/date_to режет KPI и детальный отчёт ИД по CreationDate."""
from __future__ import annotations

from datetime import date

import pandas as pd

from app.services.executive_docs_db import filter_by_creation_date


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "CardId": ["a", "b", "c", "d"],
            "_cd": pd.to_datetime(
                ["2026-01-05", "2026-01-10", "2026-01-20", "2026-03-01"]
            ),
            "Статус": ["На доработке", "На согласовании", "Отказ", "На доработке"],
        }
    )


def test_filter_by_creation_date_inclusive_bounds() -> None:
    out = filter_by_creation_date(
        _frame(),
        date_from=date(2026, 1, 6),
        date_to=date(2026, 1, 23),
    )
    assert list(out["CardId"]) == ["b", "c"]


def test_filter_by_creation_date_from_only() -> None:
    out = filter_by_creation_date(_frame(), date_from=date(2026, 1, 20), date_to=None)
    assert list(out["CardId"]) == ["c", "d"]


def test_filter_by_creation_date_to_only() -> None:
    out = filter_by_creation_date(_frame(), date_from=None, date_to=date(2026, 1, 10))
    assert list(out["CardId"]) == ["a", "b"]


def test_filter_by_creation_date_noop_without_bounds() -> None:
    src = _frame()
    out = filter_by_creation_date(src, date_from=None, date_to=None)
    assert len(out) == len(src)


def test_filter_by_creation_date_includes_end_day() -> None:
    """date_to — включительно (весь календарный день)."""
    out = filter_by_creation_date(
        pd.DataFrame(
            {
                "CardId": ["edge"],
                "_cd": pd.to_datetime(["2026-01-23 18:30:00"]),
            }
        ),
        date_from=date(2026, 1, 6),
        date_to=date(2026, 1, 23),
    )
    assert list(out["CardId"]) == ["edge"]
