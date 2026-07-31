from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import USERS_DB_PATH
from app.services.users_bridge import ensure_users_db, import_auth

ensure_users_db()
auth = import_auth()
print("users_db:", USERS_DB_PATH, "exists:", USERS_DB_PATH.is_file())
ok, user = auth.authenticate("admin", "admin")
print("login admin/admin:", ok, user)
print("roles:", len(auth.ROLES))
