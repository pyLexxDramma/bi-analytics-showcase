"""Страж скорости фильтров отчётов.

Ловит возврат поломки сентября 2026: смена проекта или периода снова
обходит все JSON в web/ или заново проходит всё дерево MSP построчно.

  python tools/check_report_filter_speed.py --static
  python tools/check_report_filter_speed.py --live

Без флагов: статическая проверка и, если задан REPORT_PASSWORD, замер прода.

Живой замер читает только окружение, пароль в файл не писать:
  REPORT_PASSWORD, REPORT_USER (admin), REPORT_BASE_URL (https://ai.conall.ru)
  REPORT_SLOW_SEC (10)

Кэш API держит ответ около часа. Скрипт каждый день берёт другой квартал,
чтобы холодный путь измерялся хотя бы раз в сутки. Повтор того же запроса
быстрее секунды — это кэш, не доказательство, что код снова быстрый.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
SLOW_SEC = float(os.environ.get("REPORT_SLOW_SEC", "10"))
TIMEOUT = 120

QUARTERS = (
    ("2026-01-01", "2026-03-31"),
    ("2026-04-01", "2026-06-30"),
    ("2026-07-01", "2026-09-30"),
    ("2026-10-01", "2026-12-31"),
)


def _roots() -> list[Path]:
    candidates = [
        ROOT / "bi-analytics-v-5-main",
        ROOT.parent / "bi-analytics-showcase" / "bi-analytics-v-5-main",
        ROOT.parent / "bi-analytics-v-5-main" / "bi-analytics-v-5-main",
    ]
    found: list[Path] = []
    for path in candidates:
        if not path.is_dir():
            continue
        resolved = path.resolve()
        if resolved not in found:
            found.append(resolved)
    return found


def _function_body(text: str, name: str) -> str | None:
    match = re.search(rf"^([ \t]*)def {re.escape(name)}\b[^\n]*\n", text, re.M)
    if not match:
        return None
    indent = match.group(1)
    rest = text[match.end() :]
    nxt = re.search(rf"^{indent}def ", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def _fail(problems: list[str], message: str) -> None:
    problems.append(message)
    print(f"FAIL  {message}")


def check_static() -> int:
    problems: list[str] = []
    for app in _roots():
        label = app.parent.name
        dashboards = app / "dashboards"
        if not dashboards.is_dir():
            _fail(problems, f"{label}: нет каталога dashboards")
            continue
        for path in dashboards.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "scan_web_files(" in text:
                _fail(problems, f"{label}: {path.name} снова вызывает scan_web_files")

        finance = (dashboards / "finance_from_1c.py").read_text(encoding="utf-8", errors="replace")
        ref = _function_body(finance, "resolve_reference_1c_dannye")
        if ref is None:
            _fail(problems, f"{label}: нет resolve_reference_1c_dannye")
        elif "scan_web_files" in ref:
            _fail(problems, f"{label}: справочник 1С снова ищет файлы в web/")

        renderers = (dashboards / "_renderers.py").read_text(encoding="utf-8", errors="replace")
        annotate = _function_body(renderers, "_annotate_msp_stage_and_lot")
        if annotate is None:
            _fail(problems, f"{label}: нет _annotate_msp_stage_and_lot")
        elif ".iterrows(" in annotate:
            _fail(problems, f"{label}: дерево MSP снова обходится через iterrows")
        memo = _function_body(renderers, "_memo_msp_stage_lot")
        if memo is None or "_MSP_STAGE_LOT_CACHE" not in renderers:
            _fail(problems, f"{label}: нет кэша дерева MSP на смену фильтра")
        bdds = _function_body(renderers, "dashboard_budget_by_period")
        if bdds is None or "_memo_msp_stage_lot(" not in bdds[:4000]:
            _fail(problems, f"{label}: БДДС не берёт дерево MSP из кэша")
        bdr = _function_body(renderers, "_derive_bdr_dimensions")
        if bdr is None:
            _fail(problems, f"{label}: нет _derive_bdr_dimensions")
        else:
            first_return = next((line.strip() for line in bdr.splitlines() if line.strip()), "")
            if "_memo_msp_stage_lot" not in first_return:
                _fail(problems, f"{label}: БДР снова считает дерево MSP на каждый фильтр")

        labels = (dashboards / "project_labels.py").read_text(encoding="utf-8", errors="replace")
        filt = _function_body(labels, "filter_dataframe_by_project_labels")
        if filt is None or "_series_project_norm_keys(" not in filt:
            _fail(problems, f"{label}: фильтр проекта снова идёт по каждой строке")

        if not any(item.startswith(f"{label}:") for item in problems):
            print(f"OK    код {label}")
    return 1 if problems else 0


def _call(method: str, url: str, headers: dict | None = None, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            return resp.status, time.perf_counter() - started, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, time.perf_counter() - started, raw
    except Exception as exc:
        return 0, time.perf_counter() - started, str(exc).encode("utf-8", "replace")


def check_live(*, required: bool) -> int:
    password = os.environ.get("REPORT_PASSWORD", "").strip()
    if not password:
        if required:
            print("FAIL  живой замер: нет REPORT_PASSWORD")
            return 2
        print("SKIP  живой замер: нет REPORT_PASSWORD")
        return 0
    base = os.environ.get("REPORT_BASE_URL", "https://ai.conall.ru").rstrip("/")
    user = os.environ.get("REPORT_USER", "admin")
    code, seconds, raw = 0, 0.0, b""
    for attempt in range(6):
        code, seconds, raw = _call(
            "POST",
            base + "/api/auth/login",
            {"Content-Type": "application/json"},
            {"username": user, "password": password},
        )
        if code == 200 or code not in (0, 502, 503, 504) or attempt == 5:
            break
        print(f"      вход {code}, сайт ещё поднимается ({attempt + 1}/6)")
        time.sleep(15)
    print(f"      вход {code} за {seconds:.2f} с")
    if code != 200:
        print("FAIL  прод не пустил на замер отчётов")
        return 2
    token = json.loads(raw.decode("utf-8")).get("token")
    headers = {"Authorization": f"Bearer {token}"}
    code, seconds, raw = _call("GET", base + "/api/bdds", headers)
    if code != 200:
        print(f"FAIL  БДДС {code} за {seconds:.2f} с")
        return 2
    payload = json.loads(raw.decode("utf-8"))
    names = [
        str(item)
        for item in ((payload.get("filters") or {}).get("projects") or [])
        if str(item).strip() and str(item).strip() != "Все"
    ]
    project = names[0] if names else "Дмитровский"
    date_from, date_to = QUARTERS[date.today().toordinal() % len(QUARTERS)]
    query = urllib.parse.urlencode(
        {"projects": project, "date_from": date_from, "date_to": date_to}
    )
    targets = [
        ("БДДС все проекты", "/api/bdds", seconds),
        ("БДДС проект и период", f"/api/bdds?{query}", None),
        ("БДР проект и период", f"/api/bdr?{query}", None),
    ]
    slow = False
    for title, path, known in targets:
        if known is None:
            code, seconds, raw = _call("GET", base + path, headers)
        note = ""
        if code == 200 and seconds < 1:
            note = ", ответ из кэша"
        elif code != 200:
            note = " " + raw[:120].decode("utf-8", "replace").replace("\n", " ")
        status = "OK   " if code == 200 and seconds <= SLOW_SEC else "FAIL "
        print(f"{status} {title}: {seconds:.2f} с{note}")
        if code != 200 or seconds > SLOW_SEC:
            slow = True
    if slow:
        print(
            f"FAIL  фильтр дольше {SLOW_SEC:.0f} с. "
            "Это та же поломка: выкладку не принимать, пока замер не вернётся к нескольким секундам."
        )
        return 2
    return 0


def main() -> int:
    args = set(sys.argv[1:])
    unknown = args - {"--static", "--live"}
    if unknown:
        print("Нужен флаг --static, --live или оба. Без флагов выполняются оба.")
        return 1
    run_static = "--static" in args or not args
    run_live = "--live" in args or not args
    code = check_static() if run_static else 0
    if run_live and code == 0:
        code = check_live(required="--live" in args)
    return code


if __name__ == "__main__":
    sys.exit(main())
