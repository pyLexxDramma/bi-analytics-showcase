# -*- coding: utf-8 -*-
"""Бакеты «Просрочка заказчика» считают дни согласования (передача), не план сдачи."""
from __future__ import annotations

from datetime import date

import pandas as pd

from app.services.executive_docs_db import (
    _buckets,
    _contractor_late_days,
    _customer_late_days,
)


TODAY = date(2026, 9, 18)


def test_customer_late_uses_transfer_not_plan() -> None:
    """Кейс ИД: нет id_Deadline, передача 12 дней назад → как колонка «ПРОСРОЧКА СОГЛАС.»."""
    row = pd.Series(
        {
            "_plan": pd.NaT,
            "_fact": pd.NaT,
            "_transfer": pd.Timestamp("2026-09-06"),
        }
    )
    assert _customer_late_days(row, TODAY) == 12


def test_customer_late_ignores_plan_deadline() -> None:
    row = pd.Series(
        {
            "_plan": pd.Timestamp("2025-01-01"),
            "_fact": pd.NaT,
            "_transfer": pd.Timestamp("2026-09-06"),
        }
    )
    assert _customer_late_days(row, TODAY) == 12


def test_customer_late_none_without_transfer() -> None:
    row = pd.Series(
        {
            "_plan": pd.Timestamp("2026-08-01"),
            "_fact": pd.NaT,
            "_transfer": pd.NaT,
        }
    )
    assert _customer_late_days(row, TODAY) is None


def test_customer_buckets_7_30_match_detail_agree_days() -> None:
    """Шесть документов 12/17 дн. попадают в «7–30», а не в нули из‑за пустого плана."""
    days = pd.Series(
        [
            _customer_late_days(
                pd.Series(
                    {"_plan": pd.NaT, "_transfer": pd.Timestamp("2026-09-06")}
                ),
                TODAY,
            )
            for _ in range(4)
        ]
        + [
            _customer_late_days(
                pd.Series(
                    {"_plan": pd.NaT, "_transfer": pd.Timestamp("2026-09-01")}
                ),
                TODAY,
            )
            for _ in range(2)
        ]
    )
    buckets = _buckets(days)
    assert buckets == {
        "bucket_0_7": 0,
        "bucket_8_30": 6,
        "bucket_30_plus": 0,
    }


def test_customer_buckets_skip_missing_transfer() -> None:
    days = pd.Series(
        [
            _customer_late_days(
                pd.Series({"_transfer": pd.NaT, "_plan": pd.NaT}),
                TODAY,
            )
        ]
        * 6
    )
    assert _buckets(days) == {
        "bucket_0_7": 0,
        "bucket_8_30": 0,
        "bucket_30_plus": 0,
    }


def test_contractor_late_still_uses_plan_when_no_contract_dates() -> None:
    row = pd.Series(
        {
            "_end": pd.NaT,
            "_recv": pd.NaT,
            "_plan": pd.Timestamp("2026-09-01"),
            "_fact": pd.NaT,
            "_transfer": pd.Timestamp("2026-09-10"),
        }
    )
    assert _contractor_late_days(row, TODAY) == 17.0
