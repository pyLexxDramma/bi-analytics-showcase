"""Конфигурация баг-репорта из env / st.secrets."""

from __future__ import annotations

from dataclasses import dataclass

from config import _env_truthy, _read_env_or_secret


@dataclass(frozen=True)
class BugReportSettings:
    enabled: bool
    ai_url: str
    ai_token: str
    ai_timeout_sec: float
    ai_min_confidence: float
    dry_run: bool
    trello_api_key: str
    trello_token: str
    trello_board_id: str
    trello_list_urgent: str
    trello_list_bug: str
    trello_list_ui: str
    trello_list_feature: str
    trello_list_question: str
    trello_list_triage: str
    trello_label_urgent: str
    trello_label_bug: str
    trello_label_ui: str
    trello_label_feature: str
    trello_label_question: str
    trello_label_triage: str
    public_base_url: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_starttls: bool
    smtp_use_ssl: bool
    telegram_bot_token: str

    @property
    def ai_configured(self) -> bool:
        return bool(self.ai_url.strip())

    @property
    def trello_configured(self) -> bool:
        # list_id колонки «Анализ» резолвится по имени на доске; triage в env — запасной.
        return bool(
            self.trello_api_key.strip()
            and self.trello_token.strip()
            and self.trello_board_id.strip()
        )

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host.strip())


def _clean_secret(value: str) -> str:
    """Trim whitespace and UTF-8 BOM (paste into secrets often adds \\ufeff)."""
    return (value or "").replace("\ufeff", "").strip()


def _float_env(name: str, default: float) -> float:
    raw = _read_env_or_secret(name).strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    raw = _read_env_or_secret(name).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_bug_report_settings() -> BugReportSettings:
    return BugReportSettings(
        enabled=not _env_truthy("BUG_REPORT_DISABLED"),
        ai_url=_read_env_or_secret("BUG_REPORT_AI_URL").strip().rstrip("/"),
        ai_token=_read_env_or_secret("BUG_REPORT_AI_TOKEN").strip(),
        ai_timeout_sec=_float_env("BUG_REPORT_AI_TIMEOUT_SEC", 10.0),
        ai_min_confidence=_float_env("BUG_REPORT_AI_MIN_CONFIDENCE", 0.7),
        dry_run=_env_truthy("BUG_REPORT_DRY_RUN"),
        trello_api_key=_read_env_or_secret("TRELLO_API_KEY").strip(),
        trello_token=_read_env_or_secret("TRELLO_TOKEN").strip(),
        trello_board_id=_read_env_or_secret("TRELLO_BOARD_ID").strip(),
        trello_list_urgent=_read_env_or_secret("TRELLO_LIST_URGENT").strip(),
        trello_list_bug=_read_env_or_secret("TRELLO_LIST_BUG").strip(),
        trello_list_ui=_read_env_or_secret("TRELLO_LIST_UI").strip(),
        trello_list_feature=_read_env_or_secret("TRELLO_LIST_FEATURE").strip(),
        trello_list_question=_read_env_or_secret("TRELLO_LIST_QUESTION").strip(),
        trello_list_triage=_read_env_or_secret("TRELLO_LIST_TRIAGE").strip(),
        trello_label_urgent=_read_env_or_secret("TRELLO_LABEL_URGENT").strip(),
        trello_label_bug=_read_env_or_secret("TRELLO_LABEL_BUG").strip(),
        trello_label_ui=_read_env_or_secret("TRELLO_LABEL_UI").strip(),
        trello_label_feature=_read_env_or_secret("TRELLO_LABEL_FEATURE").strip(),
        trello_label_question=_read_env_or_secret("TRELLO_LABEL_QUESTION").strip(),
        trello_label_triage=_read_env_or_secret("TRELLO_LABEL_TRIAGE").strip(),
        public_base_url=(
            _read_env_or_secret("BUG_STATUS_PUBLIC_BASE").strip()
            or _read_env_or_secret("PUBLIC_BASE_URL").strip()
            or "https://ai.conall.ru"
        ),
        smtp_host=_clean_secret(_read_env_or_secret("BUG_REPORT_SMTP_HOST"))
        or _clean_secret(_read_env_or_secret("SMTP_HOST")),
        smtp_port=_int_env("BUG_REPORT_SMTP_PORT", 0) or _int_env("SMTP_PORT", 587),
        smtp_user=_clean_secret(_read_env_or_secret("BUG_REPORT_SMTP_USER"))
        or _clean_secret(_read_env_or_secret("SMTP_USER")),
        smtp_password=_clean_secret(_read_env_or_secret("BUG_REPORT_SMTP_PASSWORD"))
        or _clean_secret(_read_env_or_secret("SMTP_PASSWORD")),
        smtp_from=_clean_secret(_read_env_or_secret("BUG_REPORT_SMTP_FROM"))
        or _clean_secret(_read_env_or_secret("SMTP_FROM")),
        smtp_starttls=not _env_truthy("BUG_REPORT_SMTP_NO_STARTTLS"),
        smtp_use_ssl=_env_truthy("BUG_REPORT_SMTP_SSL"),
        telegram_bot_token=_read_env_or_secret("BUG_REPORT_TELEGRAM_BOT_TOKEN").strip()
        or _read_env_or_secret("TELEGRAM_BOT_TOKEN").strip(),
    )
