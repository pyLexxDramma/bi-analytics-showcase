from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import USERS_DB_PATH
from app.services.users_bridge import ensure_users_db, import_auth

ensure_users_db()
auth = import_auth()
print("users_db:", USERS_DB_PATH, "exists:", USERS_DB_PATH.is_file())
username = os.environ.get("BI_SMOKE_USERNAME", "").strip()
password = os.environ.get("BI_SMOKE_PASSWORD", "")
if username and password:
    ok, user = auth.authenticate(username, password)
    print("login:", ok, user.get("username") if user else None)
else:
    print("login: skipped")
print("roles:", len(auth.ROLES))
