# -*- coding: utf-8 -*-
"""Regression: «Завершение СМР» в КТ — summary-веха, не «по блоку … до ЗОС»."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from streamlit_stub import ensure_streamlit_stub

ensure_streamlit_stub()

CORE = Path(__file__).resolve().parents[3] / "bi-analytics-v-5-main"
sys.path.insert(0, str(CORE))

from dashboards import dev_projects_tz_matrix as matrix  # noqa: E402


def _smr_kw() -> dict:
    for _title, slug, kw in matrix.CONTROL_POINT_MILESTONES:
        if slug == "smr_finish":
            return kw
    raise AssertionError("smr_finish not in CONTROL_POINT_MILESTONES")


def _novorizh_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "project name": "Новорижский",
                "task name": "СМР (окончание)",
                "block": "Ковенанты",
                "level": 5.0,
                "base end": pd.Timestamp("2028-09-30"),
                "plan end": pd.Timestamp("2028-09-30"),
                "pct complete": 0.0,
            },
            {
                "project name": "Новорижский",
                "task name": "Завершение СМР по блоку А до ЗОС",
                "block": "Ковенанты",
                "level": 5.0,
                "base end": pd.NaT,
                "plan end": pd.Timestamp("2026-05-30"),
                "pct complete": 0.0,
            },
        ]
    )


def test_smr_finish_matches_covenant_summary_not_block_milestone():
    kw = _smr_kw()
    assert "names_any" not in kw
    assert "names_exact_any" in kw

    sub = _novorizh_frame()
    hit = matrix._match_milestone_tasks(sub, kw)
    assert len(hit) == 1
    assert hit.iloc[0]["task name"] == "СМР (окончание)"

    plan, fact, *_rest = matrix._one_milestone_cell(hit, pct_scale_ref=sub)
    assert plan == "30.09.2028"
    assert fact == "30.09.2028"


def test_smr_finish_exact_name_still_works():
    kw = _smr_kw()
    sub = pd.DataFrame(
        [
            {
                "project name": "Есипово-5",
                "task name": "Завершение СМР",
                "block": "Ковенанты",
                "level": 5.0,
                "base end": pd.Timestamp("2027-01-31"),
                "plan end": pd.Timestamp("2027-02-26"),
                "pct complete": 0.0,
            },
            {
                "project name": "Есипово-5",
                "task name": "Завершение СМР по блоку А до ЗОС",
                "block": "Ковенанты",
                "level": 5.0,
                "base end": pd.NaT,
                "plan end": pd.Timestamp("2026-05-30"),
                "pct complete": 0.0,
            },
        ]
    )
    hit = matrix._match_milestone_tasks(sub, kw)
    assert len(hit) == 1
    assert hit.iloc[0]["task name"] == "Завершение СМР"


if __name__ == "__main__":
    test_smr_finish_matches_covenant_summary_not_block_milestone()
    test_smr_finish_exact_name_still_works()
    print("ok")
