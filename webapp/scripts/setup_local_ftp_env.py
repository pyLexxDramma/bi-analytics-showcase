"""Create local webapp/api/.env for FTP mode from Streamlit secrets.toml (never commit)."""
from __future__ import annotations

from pathlib import Path

SECRETS = Path(
    r"d:\AI_codding\Analitics\bi-analytics-v-5-main\bi-analytics-v-5-main\.streamlit\secrets.toml"
)
OUT = Path(r"d:\AI_codding\Analitics\bi-analytics-showcase\webapp\api\.env")
DATA_WEB = Path(r"d:\AI_codding\Analitics\bi-analytics-showcase\webapp\data\web")


def parse_toml_ftp(text: str) -> dict[str, str]:
    in_ftp = False
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_ftp = line.lower() == "[ftp]"
            continue
        if not in_ftp or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


ftp = parse_toml_ftp(SECRETS.read_text(encoding="utf-8"))
for k in ("host", "user", "password", "remote_dir"):
    if not ftp.get(k):
        raise SystemExit(f"missing ftp.{k} in secrets.toml")

DATA_WEB.mkdir(parents=True, exist_ok=True)
body = "\n".join(
    [
        "WEBAPP_DATA_MODE=ftp",
        f"SHOWCASE_WEB_DIR={DATA_WEB.as_posix()}",
        "WEBAPP_ADMIN_TOKEN=local-dev-sync",
        "WEBAPP_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000",
        f"BI_FTP_HOST={ftp['host']}",
        f"BI_FTP_USER={ftp['user']}",
        f"BI_FTP_PASSWORD={ftp['password']}",
        f"BI_FTP_REMOTE_DIR={ftp['remote_dir']}",
        "BI_FTP_PORT=21",
        "BI_FTP_TLS=0",
        "",
    ]
)
OUT.write_text(body, encoding="utf-8")
print(f"wrote {OUT}")
print(f"data dir {DATA_WEB}")
print("mode=ftp (secrets not printed)")
