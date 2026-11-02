import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.request_context import request_id_var

logger = logging.getLogger("app.errors")


def _request_id() -> str:
    return request_id_var.get()


def _http_detail(detail: object) -> str:
    if isinstance(detail, str):
        return detail
    return "请求无法完成"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        headers = dict(exc.headers or {})
        headers["X-Request-ID"] = _request_id()
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": _http_detail(exc.detail), "request_id": _request_id()},
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        parts: list[str] = []
        for error in exc.errors():
            location = ".".join(str(item) for item in error.get("loc", []) if item != "body")
            message = str(error.get("msg", "参数不正确"))
            parts.append(f"{location}：{message}" if location else message)
        return JSONResponse(
            status_code=422,
            content={
                "detail": "；".join(parts) or "请求参数不正确",
                "request_id": _request_id(),
            },
            headers={"X-Request-ID": _request_id()},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常 %s %s", request.method, request.url.path, exc_info=exc)
        request_id = _request_id()
        detail = f"服务器内部错误（请求 ID：{request_id}）"
        return JSONResponse(
            status_code=500,
            content={"detail": detail, "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )
