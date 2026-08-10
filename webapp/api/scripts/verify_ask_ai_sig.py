"""Verify XCA Ask AI signature test vector from ASK_AI_XCA_REQUEST.md §1.3."""
from __future__ import annotations

import base64
import hashlib
import hmac
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.ask_ai import sign_params  # noqa: E402

PARAMS = {
    "ctx": "Отчёт «БДДС (расходы)». БДДС расходы по периодам.",
    "period": "2026-08",
    "project": "Ленинский",
    "q": "Объясни дашборд «БДДС (расходы)»",
    "report": "screen_bdds",
    "role": "financier",
    "src": "finance/bdds",
    "ts": "1786000000",
    "uid": "u_1042",
    "v": "1",
}
EXPECTED = "Vzku4zNdQ0pAfCq0PfjIdHRGtQkwV9g17SGJvHE3wKo"


def main() -> None:
    got = sign_params(PARAMS, b"test-secret")
    print("got     ", got)
    print("expected", EXPECTED)
    print("match   ", got == EXPECTED)
    raise SystemExit(0 if got == EXPECTED else 1)


if __name__ == "__main__":
    main()
