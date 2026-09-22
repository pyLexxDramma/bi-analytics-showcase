from datetime import date, timedelta

from app.services.top_dashboard import (
    COVENANTS_TZ,
    MILESTONES_TZ,
    _best_key,
    _cell_to_sched,
    _column_score,
    _current_month_bounds,
    _days_between,
    _delta_from_days,
    _gdrs_day_minus_one,
    _is_rv_task,
    _matrix_covenants,
    _stable_id,
    mock_payload,
)


def test_mock_payload_proto_projects():
    payload = mock_payload()
    assert payload["meta"]["source"] == "mock"
    names = [p["name"] for p in payload["projects"]]
    assert names == [
        "Дмитровский 1",
        "Есипово 5",
        "Жуковский 1",
        "Ленинский",
        "Новорижский",
    ]
    first = payload["projects"][0]
    assert first["id"] == "dmitr"
    assert len(first["milestones"]) == len(MILESTONES_TZ)
    assert len(first["covenants"]) == len(COVENANTS_TZ)
    assert {c["name"] for c in first["covenants"]} >= {"ЗОС", "Право 1", "ВЫКУП ЗУ", "Право 2", "РВ"}


def test_mock_payload_single_project():
    payload = mock_payload(project="len")
    assert len(payload["projects"]) == 1
    assert payload["projects"][0]["name"] == "Ленинский"


def test_best_key_does_not_leak_other_projects():
    keys = ["Дмитровский", "Есипово-5", "Жуковский 1", "Ленинский", "Новорижский"]
    assert _best_key(keys, "Жуковский") == "Жуковский 1"
    assert _best_key(keys, "Есипово 5") == "Есипово-5"
    assert _best_key(keys, "Новорижский") == "Новорижский"
    assert _best_key(keys, "Дмитровский") == "Дмитровский"
    assert _best_key(["Дмитровский"], "Жуковский") is None


def test_stable_id_keeps_proto_slugs():
    assert _stable_id("Дмитровский", 0) == "dmitr"
    assert _stable_id("Жуковский 1", 2) == "zhuk"
    assert _stable_id("Новорижский", 4) == "novo"


def test_delta_sign_fact_after_plan_is_delay():
    days = _days_between("15.11.2026", "11.12.2026")
    assert days == 26
    label, klass = _delta_from_days(days)
    assert label == "-26д"
    assert klass == "delta-negative"


def test_cell_to_sched_prefers_dates_over_matrix_otkl():
    row = _cell_to_sched(
        "РВ",
        {"plan": "15.11.2026", "fact": "11.12.2026", "otkl": "-26"},
    )
    assert row["delta"] == "-26д"
    assert row["statusClass"] == "delta-negative"


def test_cell_to_sched_matrix_negative_otkl_is_delay():
    row = _cell_to_sched("РВ", {"plan": "—", "fact": "—", "otkl": "-12"})
    assert row["delta"] == "-12д"
    assert row["statusClass"] == "delta-negative"


def test_gdrs_day_is_yesterday_in_that_month():
    month, day_iso, _ = _gdrs_day_minus_one()
    yesterday = date.today() - timedelta(days=1)
    assert day_iso == yesterday.isoformat()
    assert str(yesterday.year) in month


def test_current_month_bounds():
    start, end = _current_month_bounds()
    today = date.today()
    assert start.day == 1
    assert start.month == today.month
    assert end.month == today.month
    assert start <= today <= end


def test_pravo2_prefers_developer_column():
    assert _column_score("Право 2", "Право 2 на Застройщика") > _column_score("Право 2", "Право 2")
    columns = [
        {"key": "p2", "label": "Право 2"},
        {"key": "p2z", "label": "Право 2 на Застройщика"},
    ]
    row = {
        "project": "Дмитровский",
        "cells": {
            "p2": {"plan": "01.01.2026", "fact": "02.01.2026"},
            "p2z": {"plan": "03.03.2026", "fact": "04.03.2026"},
        },
    }
    covenants = _matrix_covenants(row, columns)
    pravo2 = next(item for item in covenants if item["name"] == "Право 2")
    assert pravo2["plan"] == "03.03.2026"
    assert pravo2["fact"] == "04.03.2026"


def test_is_rv_task():
    assert _is_rv_task("РВ")
    assert _is_rv_task("Разрешение на ввод в эксплуатацию")
    assert not _is_rv_task("Право 1")
    assert not _is_rv_task("ЗОС")
