#!/usr/bin/env bash
# Inspect users.db under ~/apps and, if prod default_filters is empty,
# copy rows from the richest sibling DB (cloudpub / Streamlit / backup).
# Writes go through the prod API container: host user cannot write the volume.
set -euo pipefail

PROD_APP="${PROD_APP_DIR:-$HOME/apps/bi-analytics-webapp-prod}"
PROD_DB="${PROD_USERS_DB:-$PROD_APP/webapp/data/db/users.db}"
export PROD_USERS_DB="$PROD_DB"

SRC="$(
python3 - <<'PY'
import os
from pathlib import Path
import sqlite3

home = Path.home()
prod = Path(os.environ["PROD_USERS_DB"]).resolve()

candidates = []
apps = home / "apps"
if apps.is_dir():
    for p in apps.rglob("users.db"):
        if any(x in p.parts for x in ("node_modules", ".git", "__pycache__")):
            continue
        candidates.append(p.resolve())

uniq = []
seen = set()
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
        n = 0
        if "default_filters" in tables:
            n = int(cur.execute("SELECT COUNT(*) FROM default_filters").fetchone()[0])
        con.close()
        return n
    except sqlite3.Error as e:
        print(f"ERR {path}: {e}", flush=True)
        return None

print("== users.db scan ==", flush=True)
rows = []
for p in sorted(uniq, key=lambda x: str(x)):
    n = count_filters(p)
    if n is None:
        continue
    mark = " PROD" if p == prod else ""
    print(f"{n:5d}  {p}{mark}", flush=True)
    rows.append((p, n))

prod_n = count_filters(prod)
if prod_n is None:
    print(f"PROD missing: {prod}", flush=True)
    raise SystemExit(2)

print(f"PROD default_filters={prod_n} path={prod}", flush=True)
if prod_n > 0:
    print("OK: prod already has filters; no copy", flush=True)
    print("SOURCE_PATH=", flush=True)
    raise SystemExit(0)

sources = [(p, n) for p, n in rows if p != prod and n and n > 0]
if not sources:
    print("NO_SOURCE: no other users.db with default_filters on this host", flush=True)
    raise SystemExit(3)

sources.sort(key=lambda t: t[1], reverse=True)
src, src_n = sources[0]
print(f"RESTORE from {src} ({src_n} rows)", flush=True)
print(f"SOURCE_PATH={src}", flush=True)
PY
)"

echo "$SRC"
SRC_PATH="$(printf '%s\n' "$SRC" | sed -n 's/^SOURCE_PATH=//p' | tail -n 1)"
if [[ -z "${SRC_PATH}" ]]; then
  exit 0
fi
echo "Copy via api container: $SRC_PATH -> /data/db/users.db"

cd "$PROD_APP/webapp"
COMPOSE=(docker compose -p webapp-prod -f docker-compose.yml -f docker-compose.prod.yml)
CID="$("${COMPOSE[@]}" ps -q api)"
if [[ -z "$CID" ]]; then
  echo "ERROR: prod api container not running"
  exit 4
fi
docker cp "$SRC_PATH" "$CID:/data/db/_restore_src.db"
if [[ -f "${SRC_PATH}-wal" ]]; then
  docker cp "${SRC_PATH}-wal" "$CID:/data/db/_restore_src.db-wal"
fi
if [[ -f "${SRC_PATH}-shm" ]]; then
  docker cp "${SRC_PATH}-shm" "$CID:/data/db/_restore_src.db-shm"
fi

"${COMPOSE[@]}" exec -T api python - <<'PY'
import sqlite3
from pathlib import Path

src = Path("/data/db/_restore_src.db")
dst = Path("/data/db/users.db")
src_con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
src_con.row_factory = sqlite3.Row
filters = src_con.execute(
    """
    SELECT role, report_name, filter_key, filter_value, filter_type,
           updated_at, updated_by
    FROM default_filters
    """
).fetchall()
roles = []
try:
    roles = src_con.execute(
        "SELECT code, label, is_system, can_admin FROM roles"
    ).fetchall()
except sqlite3.Error:
    roles = []
src_con.close()

con = sqlite3.connect(str(dst))
cur = con.cursor()
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
con.commit()
after = int(cur.execute("SELECT COUNT(*) FROM default_filters").fetchone()[0])
con.close()
print(f"DONE: prod default_filters={after}")
PY

"${COMPOSE[@]}" exec -T api rm -f /data/db/_restore_src.db /data/db/_restore_src.db-wal /data/db/_restore_src.db-shm
echo "Restore finished"
