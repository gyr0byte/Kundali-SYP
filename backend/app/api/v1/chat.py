"""Authenticated, locally selected and template-rendered chart chat."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect
from starlette.types import Message

from app.ai.rendering import FallbackCode, PassageApproval
from app.ai.validator import ResponseDecodeError, decode_response
from app.api.schemas.chat import (
    MAX_CHAT_BODY_BYTES,
    MAX_CHAT_RESPONSE_BYTES,
    ChatRequest,
    ChatResponse,
)
from app.core.clock import Clock
from app.core.config import Settings
from app.core.dependencies import get_clock, get_db, get_rate_limiter, get_settings
from app.core.permissions import Permission, require_permission
from app.core.rate_limit import InMemoryRateLimiter
from app.db.models import User
from app.services.chat_service import chat_fallback, get_chat_passage_approvals, respond_to_chat

CHAT_PATH = "/api/v1/chat"


def _error(status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code, "detail": detail},
        headers={"Cache-Control": "no-store"},
    )


class _BoundedChatRoute(APIRoute):
    """Bound incoming bytes before FastAPI buffers or validates JSON."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def bounded(request: Request) -> Response:
            declared = request.headers.get("content-length")
            if declared is not None:
                if not declared.isascii() or not declared.isdecimal():
                    return _error(400, "invalid_request", "Invalid chat request")
                significant = declared.lstrip("0") or "0"
                if len(significant) > len(str(MAX_CHAT_BODY_BYTES)) or (
                    int(significant) > MAX_CHAT_BODY_BYTES
                ):
                    return _error(413, "request_too_large", "Chat request is too large")
            body = bytearray()
            try:
                async for chunk in request.stream():
                    if len(chunk) + len(body) > MAX_CHAT_BODY_BYTES:
                        return _error(413, "request_too_large", "Chat request is too large")
                    body.extend(chunk)
            except ClientDisconnect:
                return _error(400, "invalid_request", "Incomplete chat request")
            try:
                raw, _ = decode_response(bytes(body))
            except ResponseDecodeError:
                return _error(422, "invalid_request", "Invalid chat request")

            delivered = False

            async def receive() -> Message:
                nonlocal delivered
                if delivered:
                    return await request.receive()
                delivered = True
                return {"type": "http.request", "body": raw, "more_body": False}

            try:
                return await handler(Request(request.scope, receive))
            except (StarletteHTTPException, RequestValidationError):
                raise
            except Exception:
                # Includes failures in dependencies. Keep internal values out of responses and logs.
                return _error(503, "chat_unavailable", "Chat is temporarily unavailable")

        return bounded


router = APIRouter(tags=["chat"], route_class=_BoundedChatRoute)


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    current_user: User = Depends(require_permission(Permission.CHAT_USE)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    clock: Clock = Depends(get_clock),
    limiter: InMemoryRateLimiter = Depends(get_rate_limiter),
    approvals: frozenset[PassageApproval] = Depends(get_chat_passage_approvals),
) -> ChatResponse | Response:
    owner_id = current_user.id
    allowed, retry_after = limiter.check_rate_limit(f"chat:{owner_id}", 10, 60)
    if not allowed:
        raise HTTPException(
            429, "Too many chat requests", headers={"Retry-After": str(retry_after)}
        )
    try:
        result = respond_to_chat(
            db,
            request,
            owner_id=owner_id,
            settings=settings,
            clock=clock,
            approvals=approvals,
        )
        if result is not None and len(result.model_dump_json().encode("utf-8")) > (
            MAX_CHAT_RESPONSE_BYTES
        ):
            return chat_fallback(request.language, FallbackCode.GROUNDING_FAILED)
    finally:
        db.rollback()
    if result is None:
        raise HTTPException(404, "Item not found")
    return result
