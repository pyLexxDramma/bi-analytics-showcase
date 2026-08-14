#!/usr/bin/env bash
# Set admin password in prod users.db (inside compose api).
# Usage: BI_NEW_ADMIN_PASSWORD='...' bash webapp/scripts/set_admin_password_prod.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WEBAPP="$ROOT/webapp"
cd "$WEBAPP"

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-webapp-prod}"
COMPOSE=(docker compose -p "$COMPOSE_PROJECT_NAME" -f docker-compose.yml -f docker-compose.prod.yml)

PASS="${BI_NEW_ADMIN_PASSWORD:-}"
if [[ ${#PASS} -lt 6 ]]; then
  echo "ERROR: set BI_NEW_ADMIN_PASSWORD (>=6)"
  exit 1
fi

"${COMPOSE[@]}" exec -T -e BI_NEW_ADMIN_PASSWORD="$PASS" api python -c '
import os
from app.services.users_bridge import import_auth, ensure_users_db
ensure_users_db(seed=False)
auth = import_auth()
pw = os.environ["BI_NEW_ADMIN_PASSWORD"]
user = auth.get_user_by_username("admin")
if not user:
    auth.create_user("admin", pw, "superadmin", None, "system")
    print("created admin")
else:
    uid = user["id"] if isinstance(user, dict) else user[0]
    # change_password(user_id, old, new) needs old — use direct hash update
    import sqlite3
    from app.config import USERS_DB_PATH
    h = auth.hash_password(pw)
    with sqlite3.connect(str(USERS_DB_PATH)) as c:
        c.execute("UPDATE users SET password_hash=? WHERE username=?", (h, "admin"))
        c.commit()
    print("updated admin password")
'
echo "OK"
