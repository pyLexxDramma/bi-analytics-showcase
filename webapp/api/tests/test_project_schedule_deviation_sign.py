# -*- coding: utf-8 -*-
"""Знак отклонений графика проекта: база − факт (просрочка < 0)."""
from __future__ import annotations

import pandas as pd

from app.services.project_schedule import _fmt_dev, _plan_base_deviation_days


def test_late_start_is_negative():
    # Как «ВЫКУП ЗУ» на скрине: факт 01.04.2027 позже базы 25.01.2027 → −66.
    days = _plan_base_deviation_days(
        pd.Timestamp("2027-04-01"),
        pd.Timestamp("2027-01-25"),
    )
    assert days == -66
    assert _fmt_dev(days) == "-66 дн."


def test_early_start_is_positive():
    # Как «КОВЕНАНТЫ»: факт 31.01.2025 раньше базы 31.03.2027 → +789.
    days = _plan_base_deviation_days(
        pd.Timestamp("2025-01-31"),
        pd.Timestamp("2027-03-31"),
    )
    assert days == 789
    assert _fmt_dev(days) == "+789 дн."


def test_on_time_is_zero():
    days = _plan_base_deviation_days(
        pd.Timestamp("2025-12-31"),
        pd.Timestamp("2025-12-31"),
    )
    assert days == 0
    assert _fmt_dev(days) == "0 дн."


def test_end_deviation_same_rule():
    late = _plan_base_deviation_days(
        pd.Timestamp("2026-06-10"),
        pd.Timestamp("2026-06-01"),
    )
    early = _plan_base_deviation_days(
        pd.Timestamp("2026-05-20"),
        pd.Timestamp("2026-06-01"),
    )
    assert late == -9
    assert early == 12


def test_missing_dates_return_none():
    assert _plan_base_deviation_days(None, pd.Timestamp("2026-01-01")) is None
    assert _plan_base_deviation_days(pd.Timestamp("2026-01-01"), None) is None
    assert _plan_base_deviation_days(pd.NaT, pd.Timestamp("2026-01-01")) is None
