"""Регрессия jobs: состояние job'а видно из другого процесса (несколько uvicorn-воркеров).

Запуск: python webapp/scripts/check_jobs_store.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(API_DIR))

from app.services.jobs import get_job, list_jobs, start_job  # noqa: E402

job_id = start_job("selftest", lambda: {"ok": True, "note": "cross-process check"})
for _ in range(50):
    job = get_job(job_id)
    if job and job.get("status") in ("ok", "error"):
        break
    time.sleep(0.1)

job = get_job(job_id)
print(f"in-process: status={job and job.get('status')} pid={job and job.get('pid')}")

reader = (
    "import sys; sys.path.insert(0, r'%s');"
    "from app.services.jobs import get_job;"
    "j = get_job('%s');"
    "print('other-process:', j and j.get('status'), 'kind=', j and j.get('kind'),"
    " 'result=', j and j.get('result'))" % (API_DIR, job_id)
)
out = subprocess.run(
    [sys.executable, "-c", reader], capture_output=True, text=True, encoding="utf-8"
)
print(out.stdout.strip() or out.stderr.strip())

ok = (
    job is not None
    and job.get("status") == "ok"
    and "other-process: ok" in (out.stdout or "")
)
print(f"jobs в списке: {len(list_jobs())}")
print("RESULT:", "ALL OK" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
