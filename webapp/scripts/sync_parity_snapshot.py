#!/usr/bin/env python3
"""Синхронизация данных parity: cloudpub web/ → local ingest → одинаковый снимок по содержимому.

Числовой version_id совпадает только при одном файле web_data.db на обоих стендах.
После sync здесь: local получает новую версию с тем же web/, что на cloudpub active.
"""
from __future__ import annotations

import json
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

LOCAL_API = "http://127.0.0.1:8000"
CLOUD = "https://insipidly-carefree-husky.cloudpub.ru"
USER, PASS = "admin", "admin"
WEBAPP_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = WEBAPP_ROOT / "data" / "web"


def req(
    method: str,
    url: str,
    token: str | None = None,
    body: dict | None = None,
    raw: bool = False,
) -> dict | bytes:
    headers: dict[str, str] = {}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=300) as resp:
        payload = resp.read()
        return payload if raw else json.loads(payload)


def login(base: str) -> str:
    out = req("POST", f"{base}/api/auth/login", body={"username": USER, "password": PASS})
    assert isinstance(out, dict)
    return str(out["token"])


def versions(base: str, token: str) -> dict:
    out = req("GET", f"{base}/api/versions", token=token)
    assert isinstance(out, dict)
    return out


def health(base: str) -> dict:
    out = req("GET", f"{base}/api/health")
    assert isinstance(out, dict)
    return out


def active_row(v: dict) -> dict | None:
    aid = v.get("active_version_id")
    return next((x for x in v.get("items", []) if x.get("id") == aid), None)


def fingerprint(row: dict | None) -> tuple | None:
    if not row:
        return None
    return (
        str(row.get("created_at", ""))[:16],
        int(row.get("files_count") or 0),
        int(row.get("rows_count") or 0),
        str(row.get("status") or ""),
    )


def download_cloud_snapshot(token: str, dest: Path) -> Path:
    raw = req(
        "GET",
        f"{CLOUD}/api/admin/snapshot-export/download?rebuild=0",
        token=token,
        raw=True,
    )
    assert isinstance(raw, bytes)
    dest.write_bytes(raw)
    return dest


def extract_snapshot(archive: Path, web_dir: Path) -> int:
    web_dir.mkdir(parents=True, exist_ok=True)
    staging = web_dir.parent / "_parity_web_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as tf:
        tf.extractall(staging)
    files = [p for p in staging.rglob("*") if p.is_file()]
    if not files:
        raise RuntimeError("empty snapshot archive")
    # flat or nested
    root = staging
    if len(list(staging.iterdir())) == 1 and next(staging.iterdir()).is_dir():
        root = next(staging.iterdir())
    backup = web_dir.parent / f"web_backup_{int(time.time())}"
    if web_dir.exists():
        shutil.move(str(web_dir), str(backup))
        print(f"backup web -> {backup}")
    shutil.move(str(root), str(web_dir))
    shutil.rmtree(staging, ignore_errors=True)
    return len(list(web_dir.rglob("*")))


def ingest_local(token: str) -> dict:
    out = req("POST", f"{LOCAL_API}/api/admin/ingest?background=true", token=token, body={})
    assert isinstance(out, dict)
    if out.get("async") and out.get("job_id"):
        job_id = out["job_id"]
        for _ in range(600):
            time.sleep(2)
            job = req("GET", f"{LOCAL_API}/api/admin/jobs/{job_id}", token=token)
            assert isinstance(job, dict)
            st = job.get("status")
            if st in ("done", "failed", "error"):
                return job
        raise TimeoutError(f"ingest job {job_id} timeout")
    return out


def main() -> int:
    if "--list" in sys.argv:
        lt, ct = login(LOCAL_API), login(CLOUD)
        lv, cv = versions(LOCAL_API, lt), versions(CLOUD, ct)
        for name, v in [("local", lv), ("cloud", cv)]:
            row = active_row(v)
            print(f"{name}: active={v.get('active_version_id')} fp={fingerprint(row)}")
        return 0

    if "--skip-download" not in sys.argv:
        print("download cloud snapshot…")
        ct = login(CLOUD)
        with tempfile.TemporaryDirectory() as td:
            arc = Path(td) / "cloud_snapshot.tar.gz"
            download_cloud_snapshot(ct, arc)
            n = extract_snapshot(arc, WEB_DIR)
            print(f"extracted {n} paths into {WEB_DIR}")

    print("local ingest…")
    lt = login(LOCAL_API)
    job = ingest_local(lt)
    print("ingest result:", json.dumps(job, ensure_ascii=False)[:500])

    lt = login(LOCAL_API)
    ct = login(CLOUD)
    lv, cv = versions(LOCAL_API, lt), versions(CLOUD, ct)
    lr, cr = active_row(lv), active_row(cv)
    lfp, cfp = fingerprint(lr), fingerprint(cr)
    print(f"local active={lv.get('active_version_id')} fp={lfp}")
    print(f"cloud active={cv.get('active_version_id')} fp={cfp}")
    if lfp == cfp:
        print("OK: active snapshots match by fingerprint (files/rows/time)")
    else:
        print("WARN: fingerprints differ — check web/ or re-run FTP on cloud")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
