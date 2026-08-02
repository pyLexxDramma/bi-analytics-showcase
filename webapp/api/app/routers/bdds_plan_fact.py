from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.bdds_plan_fact import (
    apply_bdds_plan_fact_edits,
    build_bdds_plan_fact_payload,
    build_editor_payload,
    preview_bdds_plan_fact,
)

router = APIRouter(prefix="/api/bdds-plan-fact", tags=["bdds-plan-fact"])


class BddsPlanFactEditRow(BaseModel):
    section: str = Field("", alias="Раздел")
    lot: str = Field("", alias="Лот")
    distribution: str = Field("Равномерно", alias="Условие распределения")
    plan_start: str = Field("", alias="План. начало")
    plan_end: str = Field("", alias="План. окончание")
    plan_mln: float = Field(0.0, alias="БДДС план (утверждённый), млн руб.")
    fact_mln: float = Field(0.0, alias="БДДС факт, млн руб.")
    a_pct: float = Field(34.0, alias="A, %")
    b_pct: float = Field(33.0, alias="B, %")
    c_pct: float = Field(33.0, alias="C, %")

    model_config = {"populate_by_name": True}


class BddsPlanFactEditBody(BaseModel):
    project: str
    rows: list[dict[str, Any]] = Field(default_factory=list)
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    group: str = "month"
    view: str = "monthly"
    dev_base: str = "plan"
    hide_deviation: bool = False
    hide_zero: Optional[bool] = None
    lot_recalc_period: Optional[str] = None


def _username(x_auth_user: str | None) -> str | None:
    name = (x_auth_user or "").strip()
    return name or None


@router.get("")
def bdds_plan_fact_report(
    project: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    group: str = Query("month", pattern="^(month|quarter|year)$"),
    view: str = Query("monthly", pattern="^(monthly|cumulative)$"),
    dev_base: str = Query("plan", pattern="^(plan|fact)$"),
    hide_deviation: bool = Query(False),
    hide_zero: Optional[bool] = Query(None),
    lot_recalc_period: Optional[str] = Query(None),
    x_auth_user: str | None = Header(default=None),
):
    return build_bdds_plan_fact_payload(
        project=project,
        date_from=date_from,
        date_to=date_to,
        group=group,
        view=view,
        dev_base=dev_base,
        hide_deviation=hide_deviation,
        hide_zero=hide_zero,
        username=_username(x_auth_user),
        lot_recalc_period=lot_recalc_period,
    )


@router.get("/editor")
def bdds_plan_fact_editor(
    project: str = Query(..., min_length=1),
    show_struct: bool = Query(False),
    x_auth_user: str | None = Header(default=None),
):
    payload = build_editor_payload(
        project=project,
        username=_username(x_auth_user),
        show_struct=show_struct,
    )
    if payload.get("error"):
        raise HTTPException(status_code=400, detail=str(payload["error"]))
    return payload


@router.post("/preview")
def bdds_plan_fact_preview(
    body: BddsPlanFactEditBody,
    x_auth_user: str | None = Header(default=None),
):
    return preview_bdds_plan_fact(
        project=body.project,
        edit_rows=body.rows,
        date_from=body.date_from,
        date_to=body.date_to,
        group=body.group,
        view=body.view,
        dev_base=body.dev_base,
        hide_deviation=body.hide_deviation,
        hide_zero=body.hide_zero,
        lot_recalc_period=body.lot_recalc_period,
        username=_username(x_auth_user),
    )


@router.post("/apply")
def bdds_plan_fact_apply(
    body: BddsPlanFactEditBody,
    x_auth_user: str | None = Header(default=None),
):
    username = _username(x_auth_user)
    if not username:
        raise HTTPException(status_code=401, detail="Требуется вход (X-Auth-User).")
    result = apply_bdds_plan_fact_edits(
        project=body.project,
        edit_rows=body.rows,
        username=username,
        date_from=body.date_from,
        date_to=body.date_to,
        group=body.group,
        view=body.view,
        dev_base=body.dev_base,
        hide_deviation=body.hide_deviation,
        hide_zero=body.hide_zero,
        lot_recalc_period=body.lot_recalc_period,
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=str(result.get("error") or "Не удалось применить правки"),
        )
    return result
