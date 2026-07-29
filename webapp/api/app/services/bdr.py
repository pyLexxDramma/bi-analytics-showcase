from __future__ import annotations

from datetime import date

from app.services.finance_period import build_finance_period_payload


def build_bdr_payload(
    *,
    project: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    view: str = "monthly",
):
    return build_finance_period_payload(
        tip_needle="бдр",
        project=project,
        date_from=date_from,
        date_to=date_to,
        view=view,
    )
