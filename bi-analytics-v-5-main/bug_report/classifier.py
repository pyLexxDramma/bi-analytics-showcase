"""Классификация баг-репорта: remote AI или локальный fallback."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import requests

from bug_report.categories import (
    normalize_category,
    normalize_priority,
    VALID_CATEGORIES,
    VALID_PRIORITIES,
)
from bug_report.settings import BugReportSettings, get_bug_report_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClassificationResult:
    category: str
    priority: str
    title: str
    summary: str
    confidence: float
    source: str  # remote | fallback
    raw_response: str = ""


def _trim_title(text: str, limit: int = 80) -> str:
    one_line = re.sub(r"\s+", " ", (text or "").strip())
    if len(one_line) <= limit:
        return one_line
    return one_line[: limit - 1].rstrip() + "…"


def classify_fallback(text: str) -> ClassificationResult:
    t = (text or "").lower()
    category = "other"
    priority = "medium"

    if any(k in t for k in ("срочно", "блокер", "критич", "не работает", "упало", "авар", "недоступ")):
        category = "urgent"
        priority = "critical"
    elif any(k in t for k in ("ошибк", "баг", "некоррект", "не сход", "расхож", "сломал", "падает")):
        category = "bug"
        priority = "high"
    elif any(k in t for k in ("интерфейс", "кнопк", "цвет", "шрифт", "верст", "ui", "ux", "таблиц", "график")):
        category = "ui_improvement"
    elif any(k in t for k in ("добав", "новая", "функц", "фич", "хочу", "нужен фильтр", "реализ")):
        category = "new_feature"
    elif any(k in t for k in ("почему", "откуда", "как счита", "цифр", "данн", "источник")):
        category = "data_question"

    title = _trim_title(text.split("\n", 1)[0] if text else "Обращение с дашборда")
    summary = _trim_title(text, 240) or title
    return ClassificationResult(
        category=category,
        priority=priority,
        title=title,
        summary=summary,
        confidence=0.55,
        source="fallback",
    )


def _parse_ai_payload(data: Any) -> ClassificationResult | None:
    if not isinstance(data, dict):
        return None
    category = normalize_category(str(data.get("category", "")))
    priority = normalize_priority(str(data.get("priority", "")))
    title = _trim_title(str(data.get("title", "")))
    summary = str(data.get("summary", "")).strip() or title
    if not title:
        return None
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    if category not in VALID_CATEGORIES:
        category = "other"
    if priority not in VALID_PRIORITIES:
        priority = "medium"
    return ClassificationResult(
        category=category,
        priority=priority,
        title=title,
        summary=summary,
        confidence=confidence,
        source="remote",
        raw_response=json.dumps(data, ensure_ascii=False),
    )


def classify_remote(text: str, context: dict[str, Any], settings: BugReportSettings) -> ClassificationResult | None:
    url = settings.ai_url.strip()
    if not url:
        return None
    endpoint = url if url.endswith("/classify-bug-report") else f"{url}/classify-bug-report"
    headers = {"Content-Type": "application/json"}
    token = settings.ai_token.strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = {"text": text, "context": context}
    try:
        resp = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=(2.0, settings.ai_timeout_sec),
        )
        resp.raise_for_status()
        parsed = _parse_ai_payload(resp.json())
        if parsed is not None:
            return parsed
        logger.warning("bug_report AI: invalid JSON schema from %s", endpoint)
    except requests.RequestException as exc:
        logger.warning("bug_report AI request failed: %s", exc)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("bug_report AI parse failed: %s", exc)
    return None


def classify_bug_report(text: str, context: dict[str, Any] | None = None) -> ClassificationResult:
    settings = get_bug_report_settings()
    ctx = dict(context or {})
    remote = classify_remote(text, ctx, settings) if settings.ai_configured else None
    if remote is not None:
        if remote.confidence < settings.ai_min_confidence and remote.category == "urgent":
            return ClassificationResult(
                category="other",
                priority=remote.priority,
                title=remote.title,
                summary=remote.summary,
                confidence=remote.confidence,
                source="remote",
                raw_response=remote.raw_response,
            )
        return remote
    return classify_fallback(text)
