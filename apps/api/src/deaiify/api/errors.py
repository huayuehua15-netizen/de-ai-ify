"""统一错误模型与处理器：{"error": {"code", "message", "request_id"}}（docs §7.4）。"""

import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from deaiify.providers.base import ProviderError

HTTP_CODE_MAP = {
    "invalid_text": 400,
    "invalid_style": 400,
    "unauthorized": 401,
    "validation_error": 422,
    "rate_limited": 429,
    "provider_timeout": 504,
    "provider_error": 502,
    "model_unavailable": 503,
}


class ApiError(Exception):
    """业务错误：由 error handler 统一转成错误体。"""

    def __init__(self, code: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status or HTTP_CODE_MAP.get(code, 400)


def request_id_of(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    if not rid:
        rid = uuid.uuid4().hex
        request.state.request_id = rid
    return rid


def error_body(request: Request, code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "request_id": request_id_of(request)}}


def error_response(request: Request, code: str, message: str, status: int | None = None):
    return JSONResponse(
        status_code=status or HTTP_CODE_MAP.get(code, 400),
        content=error_body(request, code, message),
        headers={"X-Request-ID": request_id_of(request)},
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return error_response(request, exc.code, exc.message, exc.status)

    @app.exception_handler(ProviderError)
    async def _provider_error(request: Request, exc: ProviderError):
        return error_response(request, exc.code, exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", ()))
        msg = f"{loc}: {first.get('msg', '参数不合法')}" if loc else "参数不合法"
        return error_response(request, "validation_error", msg, 422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = "rate_limited" if exc.status_code == 429 else "http_error"
        detail = str(exc.detail)
        return error_response(request, code, detail, exc.status_code)

    @app.exception_handler(ValueError)
    async def _value(request: Request, exc: ValueError):
        # 引擎对空文本抛 ValueError（路由已预校验，此处兜底）
        return error_response(request, "invalid_text", str(exc) or "文本不合法", 400)
