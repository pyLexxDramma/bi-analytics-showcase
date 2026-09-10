# -*- coding: utf-8 -*-
"""Порядок задач baseline-deviation = порядок строк MSP (заявка #16)."""
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from app.services import baseline_deviation as bd


def _msp_frame() -> pd.DataFrame:
    """Три задачи: в CSV-порядке A→B→C, по отклонению C хуже всех (должен был быть сверху)."""
    return pd.DataFrame(
        [
            {
                "project name": "Дмитровский",
                "task name": "Капельный полив В3",
                "block": "СМР",
                "level": 5.0,
                "level structure": 5.0,
                "base start": pd.Timestamp("2026-01-01"),
                "base end": pd.Timestamp("2026-04-30"),
                "plan start": pd.Timestamp("2026-01-01"),
                "plan end": pd.Timestamp("2026-08-31"),  # dev -123
                "reason of deviation": "Прочее",
                "notes": "",
                "pct complete": 10.0,
                "__source_file": "msp_dmitrovsky1_28-07-2026.csv",
                "task id seq": 1,
            },
            {
                "project name": "Дмитровский",
                "task name": "Канализация хозяйственно-бытовых стоков К1",
                "block": "СМР",
                "level": 5.0,
                "level structure": 5.0,
                "base start": pd.Timestamp("2026-01-01"),
                "base end": pd.Timestamp("2026-04-30"),
                "plan start": pd.Timestamp("2026-01-01"),
                "plan end": pd.Timestamp("2026-08-31"),  # dev -123
                "reason of deviation": "Прочее",
                "notes": "",
                "pct complete": 10.0,
                "__source_file": "msp_dmitrovsky1_28-07-2026.csv",
                "task id seq": 2,
            },
            {
                "project name": "Дмитровский",
                "task name": "Котельная Блок Завод",
                "block": "СМР",
                "level": 5.0,
                "level structure": 5.0,
                "base start": pd.Timestamp("2026-01-01"),
                "base end": pd.Timestamp("2026-04-30"),
                "plan start": pd.Timestamp("2026-01-01"),
                "plan end": pd.Timestamp("2026-10-12"),  # dev -165 — худшее
                "reason of deviation": "Прочее",
                "notes": "",
                "pct complete": 10.0,
                "__source_file": "msp_dmitrovsky1_28-07-2026.csv",
                "task id seq": 3,
            },
        ]
    )


class _Labels:
    @staticmethod
    def apply_unified_project_column(df: pd.DataFrame, col: str) -> pd.DataFrame:
        out = df.copy()
        if col != "project name":
            out["project name"] = out[col]
        return out

    @staticmethod
    def project_labels_for_filter(series: pd.Series) -> list[str]:
        return sorted({str(x).strip() for x in series.dropna().tolist() if str(x).strip()})

    @staticmethod
    def filter_dataframe_by_project_labels(
        df: pd.DataFrame, projects: list[str], col: str = "project name"
    ) -> pd.DataFrame:
        if not projects:
            return df
        keys = {str(p).casefold() for p in projects}
        mask = df[col].astype(str).str.strip().str.casefold().isin(keys)
        return df.loc[mask].copy()


def test_sort_msp_uses_ord_column() -> None:
    df = pd.DataFrame(
        [
            {"task name": "C", "_msp_ord": 2, "plan_end_diff": -200},
            {"task name": "A", "_msp_ord": 0, "plan_end_diff": -10},
            {"task name": "B", "_msp_ord": 1, "plan_end_diff": -100},
        ]
    )
    ordered = bd._sort_msp(df)
    assert ordered["task name"].tolist() == ["A", "B", "C"]


def test_maket_prepare_preserves_msp_order_not_deviation() -> None:
    frame = _msp_frame()
    frame["_msp_ord"] = [0, 1, 2]
    maket = bd._maket_prepare(frame)
    assert not maket.empty
    assert maket["task name"].tolist() == [
        "Капельный полив В3",
        "Канализация хозяйственно-бытовых стоков К1",
        "Котельная Блок Завод",
    ]
    # Не порядок по отклонению (Завод был бы первым).
    assert maket["task name"].tolist()[0] != "Котельная Блок Завод"


def test_payload_chart_and_table_follow_msp_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    db_path = tmp_path / "web_data.db"
    db_path.write_bytes(b"")

    monkeypatch.setattr(bd, "WEB_DB_PATH", db_path)
    monkeypatch.setattr(bd, "prepare_web_db", lambda: None)
    monkeypatch.setattr(bd, "cache_get", lambda *a, **k: None)
    monkeypatch.setattr(bd, "cache_set", lambda *a, **k: None)
    monkeypatch.setattr(
        bd, "db_status", lambda: {"ok": True, "mtime": 1, "web_db_exists": True}
    )
    monkeypatch.setattr(bd, "load_msp_frame", lambda _vid: _msp_frame())
    monkeypatch.setattr(bd, "import_dashboard_module", lambda _name: _Labels())

    fake_schema = SimpleNamespace(get_active_version_id=lambda: 22)
    monkeypatch.setitem(__import__("sys").modules, "web_schema", fake_schema)

    payload = bd.build_baseline_deviation_payload(
        project="Дмитровский",
        block="СМР",
        building="Все",
        level="5",
        show_reasons=False,
        label_mode="name",
    )
    assert payload["meta"].get("error") in (None, "")
    assert payload["chart"]["kind"] == "end_bars"
    chart_tasks = [r["task"] for r in payload["chart"]["rows"]]
    table_tasks = [r["task"] for r in payload["rows"]]
    expected = [
        "Капельный полив В3",
        "Канализация хозяйственно-бытовых стоков К1",
        "Котельная Блок Завод",
    ]
    assert chart_tasks == expected
    assert table_tasks == expected
    assert "наибольшее отклонение" not in (payload["chart"].get("caption") or "").casefold()
