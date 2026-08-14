# -*- coding: utf-8 -*-
"""Regression: thin latest MSP snapshot must not wipe full older snapshot."""
from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pandas as pd

# web_loader imports streamlit at module level — stub for unit tests.
if "streamlit" not in sys.modules:
    _st = ModuleType("streamlit")
    _st.cache_data = lambda **_kw: (lambda f: f)  # type: ignore[attr-defined]
    sys.modules["streamlit"] = _st

CORE = Path(__file__).resolve().parents[3] / "bi-analytics-v-5-main"
sys.path.insert(0, str(CORE))

from web_loader import _deduplicate_project_snapshots  # noqa: E402


def test_thin_latest_does_not_replace_full_msp():
    rows = []
    # Full older snapshot with ЗОС
    for i in range(200):
        rows.append(
            {
                "project name": "Дмитровский-1",
                "task name": "ЗОС" if i == 0 else f"task-{i}",
                "snapshot_date": "2026-07-01",
                "__source_file": "msp_dmitrovsky1_01-07-2026.csv",
            }
        )
    # Thin newer snapshot without ЗОС
    for i in range(20):
        rows.append(
            {
                "project name": "Дмитровский-1",
                "task name": f"thin-{i}",
                "snapshot_date": "2026-08-01",
                "__source_file": "msp_dmitrovsky1_01-08-2026.csv",
            }
        )
    out = _deduplicate_project_snapshots(pd.DataFrame(rows))
    assert len(out) == 200, len(out)
    names = set(out["task name"].astype(str))
    assert "ЗОС" in names
    assert not any(str(x).startswith("thin-") for x in names)


def test_budget_does_not_wipe_msp():
    rows = []
    for i in range(100):
        rows.append(
            {
                "project name": "Есипово-5",
                "task name": "ЗОС" if i == 0 else f"t{i}",
                "snapshot_date": "2026-07-15",
                "__source_file": "msp_esipovo5_15-07-2026.csv",
            }
        )
    for i in range(5):
        rows.append(
            {
                "project name": "Есипово-5",
                "task name": f"budget-{i}",
                "snapshot_date": "2026-08-10",
                "__source_file": "budget_esipovo_10-08-2026.csv",
            }
        )
    out = _deduplicate_project_snapshots(pd.DataFrame(rows))
    assert len(out) == 100, len(out)
    assert "ЗОС" in set(out["task name"].astype(str))
    assert not any(str(x).startswith("budget-") for x in out["task name"])


if __name__ == "__main__":
    test_thin_latest_does_not_replace_full_msp()
    test_budget_does_not_wipe_msp()
    print("ok")
