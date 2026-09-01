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

    @property
    def ai_configured(self) -> bool:
        return bool(self.ai_url.strip())

    @property
    def trello_configured(self) -> bool:
        return bool(
            self.trello_api_key.strip()
            and self.trello_token.strip()
            and self.trello_board_id.strip()
            and self.trello_list_triage.strip()
        )


def _float_env(name: str, default: float) -> float:
    raw = _read_env_or_secret(name).strip()
    if not raw:
        return default
    try:
        return float(raw)
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
    )
