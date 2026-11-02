import hashlib
import logging
import os
import re
import secrets
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response as StarletteResponse
from starlette.requests import Request as StarletteRequest
from starlette.exceptions import HTTPException as StarletteHTTPException

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import db
from config import ALPHA_WORKER, WORKSPACE_COOKIE_SECURE
from i18n import t

from api.routes import attachments, cases, messages, meta

log = logging.getLogger(__name__)
WORKSPACE_COOKIE = "alpha_workspace"
WORKSPACE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365
WORKSPACE_TOKEN_RE = re.compile(r"^[a-f0-9]{64}$")


class WorkspaceIsolationMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        is_workspace_request = (
            path == "/api/cases" or path.startswith("/api/cases/")
            or path == "/api/chat/messages" or path.startswith("/api/messages/")
            or path.startswith("/api/attachments/")
        )
        if not is_workspace_request:
            await self.app(scope, receive, send)
            return

        request = StarletteRequest(scope, receive)
        workspace_token = request.cookies.get(WORKSPACE_COOKIE, "")
        new_cookie = not WORKSPACE_TOKEN_RE.fullmatch(workspace_token)
        if new_cookie:
            workspace_token = secrets.token_hex(32)
        workspace_id = hashlib.sha256(workspace_token.encode("ascii")).hexdigest()
        interrupted_error = f"{t('ar', 'interrupted')}\n{t('en', 'interrupted')}"

        with db.workspace(workspace_id):
            db.initialize_workspace(interrupted_error, ALPHA_WORKER)

            async def send_private_response(message):
                if message["type"] == "http.response.start":
                    headers = [(key, value) for key, value in message.get("headers", [])
                               if key.lower() != b"cache-control"]
                    headers.append((b"cache-control", b"private, no-store"))
                    if new_cookie:
                        cookie_response = StarletteResponse()
                        cookie_response.set_cookie(
                            WORKSPACE_COOKIE,
                            workspace_token,
                            max_age=WORKSPACE_COOKIE_MAX_AGE,
                            httponly=True,
                            secure=WORKSPACE_COOKIE_SECURE,
                            samesite="lax",
                            path="/api",
                        )
                        cookie_header = next((value for key, value in cookie_response.raw_headers
                                              if key.lower() == b"set-cookie"), b"")
                        headers.append((b"set-cookie", cookie_header))
                    message["headers"] = headers
                await send(message)

            await self.app(scope, receive, send_private_response)


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    db.fail_interrupted(f"{t('ar', 'interrupted')}\n{t('en', 'interrupted')}", ALPHA_WORKER)
    db.fail_interrupted_actions(f"{t('ar', 'act_interrupted')}\n{t('en', 'act_interrupted')}")
    yield


app = FastAPI(title="Alpha API", version="1.0.0", lifespan=lifespan)
app.include_router(meta.router, prefix="/api")
app.include_router(cases.router, prefix="/api")
app.include_router(attachments.router, prefix="/api")
app.include_router(messages.router, prefix="/api")
app.add_middleware(WorkspaceIsolationMiddleware)


@app.middleware("http")
async def request_timing(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["Server-Timing"] = f"app;dur={(time.perf_counter() - started) * 1000:.2f}"
    return response

if os.getenv("ALPHA_ENV") == "development":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _language(request):
    from api.deps import get_language

    return get_language(request)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    lang = _language(request)
    if isinstance(exc.detail, dict) and {"code", "message"} <= exc.detail.keys():
        payload = exc.detail
    else:
        if exc.status_code == 404:
            message = "المسار غير موجود." if lang == "ar" else "The requested path was not found."
        elif exc.status_code == 405:
            message = "الطريقة غير مسموحة لهذا المسار." if lang == "ar" else "Method not allowed for this path."
        else:
            message = str(exc.detail)
        payload = {"code": "http_error", "message": message}
    return JSONResponse(status_code=exc.status_code, content={"error": payload},
                        headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    lang = _language(request)
    message = "الطلب غير صالح." if lang == "ar" else "The request is invalid."
    return JSONResponse(status_code=422, content={
        "error": {
            "code": "invalid_request",
            "message": message,
            "details": [{"location": error["loc"], "message": error["msg"], "type": error["type"]}
                        for error in exc.errors()],
        }
    })


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    log.error("Unhandled API error", exc_info=(type(exc), exc, exc.__traceback__))
    lang = _language(request)
    message = "حدث خطأ غير متوقع." if lang == "ar" else "An unexpected error occurred."
    return JSONResponse(status_code=500, content={
        "error": {"code": "internal_error", "message": message}
    })
