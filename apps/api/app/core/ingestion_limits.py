from __future__ import annotations

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_payload


class IngestionBodyLimitMiddleware:
    """Bound ingestion request bodies before FastAPI parses JSON."""

    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"] not in {"/api/v1/ingest/events", "/api/v1/ingest/events/batch"}
        ):
            await self.app(scope, receive, send)
            return

        async def too_large() -> None:
            response = JSONResponse(
                status_code=413,
                content=error_payload("request_too_large", "Ingestion request body is too large"),
            )
            await response(scope, receive, send)

        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None and content_length.isdecimal():
            if int(content_length) > self.max_body_bytes:
                await too_large()
                return

        messages: list[Message] = []
        total = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                return
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_body_bytes:
                    await too_large()
                    return
                if not message.get("more_body", False):
                    break

        pending = iter(messages)

        async def replay_receive() -> Message:
            try:
                return next(pending)
            except StopIteration:
                return await receive()

        await self.app(scope, replay_receive, send)
