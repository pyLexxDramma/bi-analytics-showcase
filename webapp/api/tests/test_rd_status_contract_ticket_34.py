# -*- coding: utf-8 -*-
"""Ticket 34: номер договора из плана (casefold) и статус РД при подписи ГИП."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from streamlit_stub import ensure_streamlit_stub

ensure_streamlit_stub()

CORE = Path(__file__).resolve().parents[3] / "bi-analytics-v-5-main"
sys.path.insert(0, str(CORE))

from dashboards import _renderers as R  # noqa: E402
from dashboards._renderers import (  # noqa: E402
    _RD_TESSA_STATUS_PRODUCTION,
    _RD_TESSA_STATUS_REVIEW,
    _build_rd_work_doc_detail_table,
    _build_tessa_rd_detail_table,
    _rd_plan_csv_pick_columns,
)


def test_rd_plan_csv_pick_columns_contract_casefold() -> None:
    lower = pd.DataFrame(
        {
            "Шифр": ["КМ1"],
            "№ договора": ["65-ХСА-1/24"],
        }
    )
    titled = pd.DataFrame(
        {
            "Шифр": ["КМ1"],
            "№ Договора": ["65-ХСА-1/24"],
        }
    )
    assert _rd_plan_csv_pick_columns(lower)["contract"] == "№ договора"
    assert _rd_plan_csv_pick_columns(titled)["contract"] == "№ Договора"


def test_tessa_detail_review_with_production_becomes_issued() -> None:
    doc_id = "99c8424a-a852-4e92-aa46-40882ed1a36f"
    R.st.session_state["tessa_data"] = pd.DataFrame(
        [
            {
                "ObjectProjectName": "Ленинский",
                "DivisionCipher": "КМ1",
                "DivisionName": "Конструкции металлические",
                "InternalID": "65-ХСА-1/24-КМ1-A",
                "Status": "На рассмотрении у ГИП",
                "DocID": doc_id,
                "DocNumber": "1",
                "SubDivisionVersionName": "Первая версия",
            }
        ]
    )
    dates = {
        doc_id: {
            "designer": None,
            "production": pd.Timestamp("2025-06-09"),
            "contractor": None,
            "rework": None,
        }
    }
    with patch.object(R, "_rd_task_dates_by_card", return_value=dates):
        tbl = _build_tessa_rd_detail_table(selected_projects=["Ленинский"])
    assert not tbl.empty
    assert tbl.iloc[0]["Статус"] == _RD_TESSA_STATUS_PRODUCTION


def test_tessa_detail_review_without_production_stays_review() -> None:
    doc_id = "card-review-only"
    R.st.session_state["tessa_data"] = pd.DataFrame(
        [
            {
                "ObjectProjectName": "Ленинский",
                "DivisionCipher": "КМ1",
                "DivisionName": "Конструкции металлические",
                "InternalID": "65-ХСА-1/24-КМ1-A",
                "Status": "На рассмотрении у ГИП",
                "DocID": doc_id,
                "DocNumber": "2",
                "SubDivisionVersionName": "Первая версия",
            }
        ]
    )
    dates = {
        doc_id: {
            "designer": pd.Timestamp("2025-05-01"),
            "production": None,
            "contractor": None,
            "rework": None,
        }
    }
    with patch.object(R, "_rd_task_dates_by_card", return_value=dates):
        tbl = _build_tessa_rd_detail_table(selected_projects=["Ленинский"])
    assert not tbl.empty
    assert tbl.iloc[0]["Статус"] == _RD_TESSA_STATUS_REVIEW


def test_tessa_detail_review_stays_when_gip_sign_followed_by_rework() -> None:
    doc_id = "card-gip-then-rework"
    R.st.session_state["tessa_data"] = pd.DataFrame(
        [
            {
                "ObjectProjectName": "Ленинский",
                "DivisionCipher": "КМ1",
                "DivisionName": "Конструкции металлические",
                "InternalID": "65-ХСА-1/24-КМ1-A",
                "Status": "На рассмотрении у ГИП",
                "DocID": doc_id,
                "DocNumber": "3",
                "SubDivisionVersionName": "Первая версия",
            }
        ]
    )
    R.st.session_state["tessa_tasks_data"] = pd.DataFrame(
        [
            {
                "CardID": doc_id,
                "OptionCaption": "Подписан",
                "RoleName": "ГИП ХСА",
                "Completed": "09.06.2025",
            },
            {
                "CardID": doc_id,
                "OptionCaption": "Вернуть документ на доработку",
                "RoleName": "ГИП ХСА",
                "Completed": "15.06.2025",
            },
        ]
    )
    dates = R._rd_task_dates_by_card()
    assert dates.get(doc_id, {}).get("production") is None
    tbl = _build_tessa_rd_detail_table(selected_projects=["Ленинский"])
    assert not tbl.empty
    assert tbl.iloc[0]["Статус"] == _RD_TESSA_STATUS_REVIEW
    assert tbl.iloc[0]["Статус"] != _RD_TESSA_STATUS_PRODUCTION


def test_work_doc_detail_fills_contract_from_plan_when_tessa_empty() -> None:
    plan = pd.DataFrame(
        [
            {
                "Проект": "Ленинский",
                "Шифр": "КМ1",
                "Наименование раздела": "Конструкции металлические",
                "Шифр полный": "65-ХСА-1/24-КМ1-А",
                "№ договора": "65-ХСА-1/24",
                "_plan_dt": pd.Timestamp("2025-01-15"),
                "_fact_dt": pd.NaT,
            }
        ]
    )
    tessa = pd.DataFrame(
        [
            {
                "Проект": "Ленинский",
                "Наименование разделов работ": "Конструкции металлические",
                "Номер договора": "",
                "Шифр": "КМ1",
                "Шифр полный": "65-ХСА-1/24-КМ1-A",
                "Версия": "Первая версия",
                "Статус": _RD_TESSA_STATUS_PRODUCTION,
                "Дата выдачи разделов по Договору": "15.01.2025",
                "Прогнозная дата выдачи разделов": "",
                "Дата загрузки раздела генпроектировщиком": "",
                "Дата выдачи в производство работ": "09.06.2025",
                "Подрядчик": "",
                "ID документа в Тессе": "1",
            }
        ]
    )
    with (
        patch.object(R, "_rd_plan_csv_sections_df", return_value=plan),
        patch.object(R, "_build_tessa_rd_detail_table", return_value=tessa),
    ):
        out = _build_rd_work_doc_detail_table(selected_projects=["Ленинский"])
    assert not out.empty
    assert out.iloc[0]["Номер договора"] == "65-ХСА-1/24"


def test_work_doc_detail_keeps_tessa_contract_when_present() -> None:
    plan = pd.DataFrame(
        [
            {
                "Проект": "Ленинский",
                "Шифр": "АС",
                "Наименование раздела": "Архитектурные решения",
                "Шифр полный": "65-ХСА-1/24-АС-А",
                "№ договора": "65-ХСА-1/24",
                "_plan_dt": pd.Timestamp("2025-01-15"),
                "_fact_dt": pd.NaT,
            }
        ]
    )
    tessa = pd.DataFrame(
        [
            {
                "Проект": "Ленинский",
                "Наименование разделов работ": "Архитектурные решения",
                "Номер договора": "52-СКА/25",
                "Шифр": "АС",
                "Шифр полный": "65-ХСА-1/24-АС-A",
                "Версия": "Первая версия",
                "Статус": _RD_TESSA_STATUS_PRODUCTION,
                "Дата выдачи разделов по Договору": "15.01.2025",
                "Прогнозная дата выдачи разделов": "",
                "Дата загрузки раздела генпроектировщиком": "",
                "Дата выдачи в производство работ": "09.06.2025",
                "Подрядчик": "",
                "ID документа в Тессе": "31",
            }
        ]
    )
    with (
        patch.object(R, "_rd_plan_csv_sections_df", return_value=plan),
        patch.object(R, "_build_tessa_rd_detail_table", return_value=tessa),
    ):
        out = _build_rd_work_doc_detail_table(selected_projects=["Ленинский"])
    assert not out.empty
    assert out.iloc[0]["Номер договора"] == "52-СКА/25"
