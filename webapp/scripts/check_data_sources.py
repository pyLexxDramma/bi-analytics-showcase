"""Guard: UI-сервисы должны читать web_data.db, а не каталог web/.

Правило (`.cursor/rules/dashboard-data-architecture.mdc`): FTP и `web/` — это ETL,
источник для экранов — только БД. Пока часть сервисов ещё читает диск, поэтому
здесь baseline-список известного техдолга: скрипт падает на **новом** нарушении
и напоминает вычистить запись, когда сервис переведён на БД.

Запуск: python webapp/scripts/check_data_sources.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SERVICES = Path(__file__).resolve().parents[1] / "api" / "app" / "services"

# Чтение диска здесь легально: это и есть ETL/пути.
ETL_FILES = {"db_ingest.py", "ftp_ingest.py", "data_paths.py"}

# Техдолг на 2026-07-30: переводим на web_data.db по мере прохождения экранов.
KNOWN_DEBT = {
    # #2 БДДС переведён на web_data.db (services/finance_1c.py); остались #3 БДР и #5 план/факт
    "finance_period.py": "#3 БДР и #5 план/факт: latest_web_file('_dannye.json') → фазы 2.3/2.5",
    "baseline_deviation.py": "#9 отклонение от БП → фаза 4",
    "documentation.py": "#10–#11 документация → фаза 4",
    "gdrs.py": "#12–#13 ГДРС (нужен отдельный perf-план) → фаза 4",
    "prescriptions.py": "#14 предписания → фаза 4",
    "executive_docs.py": "#15 исполнительная документация → фаза 4",
    "debit_credit.py": "#16 ДЗ/КЗ → фаза 4",
}

PATTERN = re.compile(r"latest_web_file|WEB_DATA_DIR")


def main() -> int:
    if not SERVICES.is_dir():
        print(f"Нет каталога сервисов: {SERVICES}", file=sys.stderr)
        return 2

    offenders: dict[str, int] = {}
    for path in sorted(SERVICES.glob("*.py")):
        if path.name in ETL_FILES:
            continue
        hits = len(PATTERN.findall(path.read_text(encoding="utf-8")))
        if hits:
            offenders[path.name] = hits

    new = {name: hits for name, hits in offenders.items() if name not in KNOWN_DEBT}
    fixed = [name for name in KNOWN_DEBT if name not in offenders]

    for name, hits in sorted(offenders.items()):
        if name in KNOWN_DEBT:
            print(f"  DEBT {name} ({hits}) — {KNOWN_DEBT[name]}")
    for name, hits in sorted(new.items()):
        print(f"  NEW  {name} ({hits}) — сервис читает web/ вместо web_data.db")
    for name in sorted(fixed):
        print(f"  DONE {name} — переведён на БД, удалите запись из KNOWN_DEBT")

    if new:
        print(f"\nRESULT: новых нарушений {len(new)}")
        return 1
    print(
        f"\nRESULT: новых нарушений нет (техдолг: {len(offenders)} файлов)"
        + (f", устарели записи: {len(fixed)}" if fixed else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
