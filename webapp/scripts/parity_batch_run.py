#!/usr/bin/env python3
"""Batch parity: walk screens 3-16, API compare, summary JSON."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CMP = Path(__file__).resolve().parent / "_parity_api_cmp.py"

SCREENS = [
    ("bdr", "/api/bdr"),
    ("approved-budget", "/api/approved-budget"),
    ("bdds-plan-fact", "/api/bdds-plan-fact"),
    ("control-points", "/api/control-points"),
    ("project-schedule", "/api/project-schedule"),
    ("deviation-reasons", "/api/deviation-reasons"),
    ("baseline-deviation", "/api/baseline-deviation"),
    ("project-documentation", "/api/project-documentation"),
    ("working-documentation", "/api/working-documentation"),
    ("gdrs-people", "/api/gdrs-people"),
    ("gdrs-equipment", "/api/gdrs-equipment"),
    ("prescriptions", "/api/prescriptions"),
    ("executive-docs", "/api/executive-docs"),
    ("debit-credit", "/api/debit-credit"),
]

if __name__ == "__main__":
    start = sys.argv[1] if len(sys.argv) > 1 else None
    rows = []
    started = start is None
    for sid, api in SCREENS:
        if not started:
            if sid == start:
                started = True
            else:
                continue
        print(f"\n=== {sid} ===", flush=True)
        env = {
            **dict(__import__("os").environ),
            "ONLY": sid,
            "SIMPLE_SHOTS": "1",
            "NAV_MS": "120000",
            "SETTLE_MS": "5000",
            "OPEN_COMPARE": "0",
        }
        p = subprocess.run(
            ["node", "scripts/visual_walk_parity.mjs"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        out_dir = None
        for line in (p.stdout or "").splitlines():
            if line.startswith("OUT "):
                out_dir = line[4:].strip()
        api_out = subprocess.run(
            [sys.executable, str(CMP), api],
            capture_output=True,
            text=True,
        )
        api_equal = "equal True" in (api_out.stdout or "")
        report = {}
        if out_dir:
            rp = Path(out_dir) / "report.json"
            if rp.is_file():
                report = json.loads(rp.read_text(encoding="utf-8"))
        diffs = report.get("summary", {}).get("visualDiffs", [])
        rows.append(
            {
                "id": sid,
                "out": out_dir,
                "api_equal": api_equal,
                "api_log": (api_out.stdout or "").strip(),
                "visual_diffs": diffs,
                "exit": p.returncode,
            }
        )
        print(api_out.stdout or api_out.stderr, flush=True)
        if p.returncode != 0:
            print(p.stderr, flush=True)

    summary_path = ROOT / "parity_out" / "batch_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {summary_path}")
