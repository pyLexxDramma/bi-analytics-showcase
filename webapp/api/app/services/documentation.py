"""Документация ПД/РД — тонкий слой: данные только из web_data.db через project_documentation."""
from __future__ import annotations

from typing import Any

from app.services.project_documentation import (
    build_project_documentation_payload,
    build_working_documentation_payload,
)

__all__ = [
    "build_project_documentation_payload",
    "build_working_documentation_payload",
    "build_documentation_payload",
]


def build_documentation_payload(*, doc_kind: str = "pd", **kwargs: Any) -> dict[str, Any]:
    if doc_kind == "rd":
        return build_working_documentation_payload(**kwargs)
    return build_project_documentation_payload(**kwargs)
