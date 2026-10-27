import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import db
from config import ALPHA_WORKER
from i18n import t

from api.routes import attachments, cases, messages, meta

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    db.fail_interrupted(f"{t('ar', 'interrupted')}\n{t('en', 'interrupted')}", ALPHA_WORKER)
    yield


app = FastAPI(title="Alpha API", version="1.0.0", lifespan=lifespan)
app.include_router(meta.router, prefix="/api")
app.include_router(cases.router, prefix="/api")
app.include_router(attachments.router, prefix="/api")
app.include_router(messages.router, prefix="/api")

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
