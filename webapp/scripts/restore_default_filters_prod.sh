#!/usr/bin/env bash
# Inspect users.db under ~/apps and, if prod default_filters is empty,
# copy rows from the richest sibling DB (cloudpub / Streamlit / backup).
set -euo pipefail

PROD_DB="${PROD_USERS_DB:-$HOME/apps/bi-analytics-webapp-prod/webapp/data/db/users.db}"

python3 - <<'PY'
import os
import sqlite3
from pathlib import Path

home = Path.home()
prod = Path(os.environ.get(
    "PROD_USERS_DB",
    str(home / "apps/bi-analytics-webapp-prod/webapp/data/db/users.db"),
)).resolve()

candidates: list[Path] = []
apps = home / "apps"
if apps.is_dir():
    for p in apps.rglob("users.db"):
        # skip docker overlay / huge trees
        if any(x in p.parts for x in ("node_modules", ".git", "__pycache__")):
            continue
        candidates.append(p.resolve())

# de-dupe
seen: set[str] = set()
uniq: list[Path] = []
for p in candidates:
    key = str(p)
    if key in seen:
        continue
    seen.add(key)
    uniq.append(p)

def count_filters(path: Path):
    if not path.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        cur = con.cursor()
        tables = {
            r[0]
            for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "default_filters" not in tables:
            con.close()
            return 0
        n = int(cur.execute("SELECT COUNT(*) FROM default_filters").fetchone()[0])
        con.close()
        return n
    except sqlite3.Error as e:
        print(f"ERR {path}: {e}")
        return None

print("== users.db scan ==")
rows: list[tuple[Path, int]] = []
for p in sorted(uniq, key=lambda x: str(x)):
    n = count_filters(p)
    if n is None:
        continue
    mark = " PROD" if p == prod else ""
    print(f"{n:5d}  {p}{mark}")
    rows.append((p, n))

prod_n = count_filters(prod)
if prod_n is None:
    print(f"PROD missing: {prod}")
    raise SystemExit(2)

print(f"PROD default_filters={prod_n} path={prod}")

if prod_n > 0:
    print("OK: prod already has filters; no copy")
    raise SystemExit(0)

sources = [(p, n) for p, n in rows if p != prod and n and n > 0]
if not sources:
    print("NO_SOURCE: no other users.db with default_filters on this host")
    raise SystemExit(3)

sources.sort(key=lambda t: t[1], reverse=True)
src, src_n = sources[0]
print(f"RESTORE from {src} ({src_n} rows) -> {prod}")

src_con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
src_con.row_factory = sqlite3.Row
filters = src_con.execute(
    """
    SELECT role, report_name, filter_key, filter_value, filter_type,
           updated_at, updated_by
    FROM default_filters
    """
).fetchall()

# optional role rows for FK-ish integrity
roles = []
try:
    roles = src_con.execute(
        "SELECT code, label, is_system, can_admin FROM roles"
    ).fetchall()
except sqlite3.Error:
    roles = []
src_con.close()

dst = sqlite3.connect(str(prod))
cur = dst.cursor()
cur.execute(
    """
    CREATE TABLE IF NOT EXISTS default_filters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL,
        report_name TEXT NOT NULL,
        filter_key TEXT NOT NULL,
        filter_value TEXT,
        filter_type TEXT DEFAULT 'string',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_by TEXT,
        UNIQUE(role, report_name, filter_key)
    )
    """
)
# ensure roles table exists if we have role defs
if roles:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS roles (
            code TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            is_system INTEGER DEFAULT 0,
            can_admin INTEGER DEFAULT 0
        )
        """
    )
    for r in roles:
        cur.execute(
            """
            INSERT OR IGNORE INTO roles (code, label, is_system, can_admin)
            VALUES (?, ?, ?, ?)
            """,
            (r["code"], r["label"], r["is_system"], r["can_admin"]),
        )

for f in filters:
    cur.execute(
        """
        INSERT INTO default_filters
            (role, report_name, filter_key, filter_value, filter_type, updated_at, updated_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(role, report_name, filter_key) DO UPDATE SET
            filter_value=excluded.filter_value,
            filter_type=excluded.filter_type,
            updated_at=excluded.updated_at,
            updated_by=excluded.updated_by
        """,
        (
            f["role"],
            f["report_name"],
            f["filter_key"],
            f["filter_value"],
            f["filter_type"],
            f["updated_at"],
            f["updated_by"],
        ),
    )
dst.commit()
after = int(cur.execute("SELECT COUNT(*) FROM default_filters").fetchone()[0])
dst.close()
print(f"DONE: prod default_filters={after}")
PY
