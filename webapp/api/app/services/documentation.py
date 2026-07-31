"""Документация ПД/РД — тонкий слой диспетчеризации."""
from __future__ import annotations

from typing import Any

from app.services.project_documentation import build_project_documentation_payload
from app.services.working_documentation import build_working_documentation_payload

__all__ = [
    "build_project_documentation_payload",
    "build_working_documentation_payload",
    "build_documentation_payload",
]


def build_documentation_payload(*, doc_kind: str = "pd", **kwargs: Any) -> dict[str, Any]:
    if doc_kind == "rd":
        return build_working_documentation_payload(**kwargs)
    return build_project_documentation_payload(**kwargs)
