# -*- coding: utf-8 -*-
"""KPI review_gip / returned_rework согласованы с pie (_fit_pie_to_total)."""
from __future__ import annotations

from app.services.working_documentation import (
    _empty_payload,
    _fit_pie_to_total,
    _tessa_status_keys,
)


class _KeysMod:
    _RD_TESSA_STATUS_PRODUCTION = "Выдано в производство работ"
    _RD_TESSA_STATUS_REVIEW = "На рассмотрении у ГИП"
    _RD_TESSA_STATUS_REWORK = "Возвращено на доработку"
    _RD_TESSA_STATUS_NOT_ISSUED = "Не выдано"


def test_empty_payload_has_status_kpi_zeros() -> None:
    empty = _empty_payload()
    assert empty["kpis"]["review_gip"] == 0
    assert empty["kpis"]["returned_rework"] == 0
    assert empty["kpis"]["issued_production"] == 0
    assert empty["kpis"]["not_issued"] == 0


def test_fit_pie_status_counts_match_kpi_fields() -> None:
    keys = _tessa_status_keys(_KeysMod())
    total = 198
    raw = {
        keys["production"]: 166,
        keys["review"]: 12,
        keys["rework"]: 5,
        keys["not_issued"]: 15,
    }
    pie = _fit_pie_to_total(raw, total, keys, keys["not_issued"])

    review_gip = int(pie.get(keys["review"], 0) or 0)
    returned_rework = int(pie.get(keys["rework"], 0) or 0)
    issued = int(pie.get(keys["production"], 0) or 0)
    not_issued = max(0, total - issued)

    assert review_gip == 12
    assert returned_rework == 5
    assert issued == 166
    assert not_issued == 32
    # ГИП + доработка + «просто не выдано» = карточка «Не выдано»
    plain = int(pie.get(keys["not_issued"], 0) or 0)
    assert review_gip + returned_rework + plain == not_issued


def test_fit_pie_missing_statuses_are_zero() -> None:
    keys = _tessa_status_keys(_KeysMod())
    pie = _fit_pie_to_total(
        {keys["production"]: 10},
        10,
        keys,
        keys["not_issued"],
    )
    assert int(pie.get(keys["review"], 0) or 0) == 0
    assert int(pie.get(keys["rework"], 0) or 0) == 0
