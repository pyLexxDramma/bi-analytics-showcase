from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import AI_ENABLED
from app.services import assistant
from app.services.auth_context import require_report_user

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


def _require_report_user(authorization: str | None) -> str:
    return str(require_report_user(authorization)["username"])


def _ensure_ai_enabled() -> None:
    if not AI_ENABLED:
        raise HTTPException(status_code=404, detail="XCA AI отключён в этом окружении")


def _raise_service_error(exc: assistant.AssistantError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


class SessionBody(BaseModel):
    title: str = Field(default="Новый чат", max_length=80)


class MessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


class QuestionReplyBody(BaseModel):
    question_id: str = Field(min_length=1, max_length=200)
    answer: str = Field(min_length=1, max_length=2000)


@router.get("/health")
async def assistant_health(authorization: str | None = Header(default=None)):
    _require_report_user(authorization)
    if not AI_ENABLED:
        return {"ok": True, "enabled": False, "mode": "stub"}
    return await assistant.health()


@router.get("/sessions")
def sessions(authorization: str | None = Header(default=None)):
    username = _require_report_user(authorization)
    _ensure_ai_enabled()
    return {"items": assistant.list_sessions(username)}


@router.post("/sessions")
async def create_session(
    body: SessionBody,
    authorization: str | None = Header(default=None),
):
    username = _require_report_user(authorization)
    _ensure_ai_enabled()
    try:
        return await assistant.create_session(username, body.title.strip() or "Новый чат")
    except assistant.AssistantError as exc:
        _raise_service_error(exc)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    authorization: str | None = Header(default=None),
):
    username = _require_report_user(authorization)
    _ensure_ai_enabled()
    try:
        await assistant.delete_session(username, session_id)
    except assistant.AssistantError as exc:
        _raise_service_error(exc)


@router.get("/sessions/{session_id}/messages")
async def messages(
    session_id: str,
    authorization: str | None = Header(default=None),
):
    username = _require_report_user(authorization)
    _ensure_ai_enabled()
    try:
        return await assistant.get_messages(username, session_id)
    except assistant.AssistantError as exc:
        _raise_service_error(exc)


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    body: MessageBody,
    authorization: str | None = Header(default=None),
):
    username = _require_report_user(authorization)
    _ensure_ai_enabled()
    try:
        return await assistant.send_message(username, session_id, body.text)
    except assistant.AssistantError as exc:
        _raise_service_error(exc)


@router.post("/sessions/{session_id}/cancel")
async def cancel(
    session_id: str,
    authorization: str | None = Header(default=None),
):
    username = _require_report_user(authorization)
    _ensure_ai_enabled()
    try:
        return await assistant.cancel(username, session_id)
    except assistant.AssistantError as exc:
        _raise_service_error(exc)


@router.post("/sessions/{session_id}/question")
async def reply_question(
    session_id: str,
    body: QuestionReplyBody,
    authorization: str | None = Header(default=None),
):
    username = _require_report_user(authorization)
    _ensure_ai_enabled()
    try:
        return await assistant.reply_question(
            username,
            session_id,
            body.question_id,
            body.answer,
        )
    except assistant.AssistantError as exc:
        _raise_service_error(exc)


@router.get("/assets/{session_id}/{asset_id}")
def asset(
    session_id: str,
    asset_id: str,
    authorization: str | None = Header(default=None),
):
    username = _require_report_user(authorization)
    _ensure_ai_enabled()
    try:
        path = assistant.resolve_asset(username, session_id, asset_id)
    except assistant.AssistantError as exc:
        _raise_service_error(exc)
    return FileResponse(path)
