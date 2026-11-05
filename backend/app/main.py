import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.api.routes.audit import router as audit_router
from app.api.routes.auth import router as auth_router
from app.api.routes.departments import router as departments_router
from app.api.routes.dicts import router as dicts_router
from app.api.routes.health import router as health_router
from app.api.routes.ingestion import router as ingestion_router
from app.api.routes.records import router as records_router
from app.api.routes.roles import router as roles_router
from app.api.routes.users import router as users_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.request_context import client_ip_var, request_id_var

setup_logging("api")

logger = logging.getLogger("app.access")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # uvicorn 在加载配置后会重设自己的 logger，这里再应用一次才能把访问日志纳入文件
    setup_logging("api")
    yield


app = FastAPI(
    title="黔西南职院数据采集系统 API",
    description="校内数据汇聚、审核、发布与共享服务",
    version="0.1.0",
    lifespan=lifespan,
)

register_exception_handlers(app)


@app.middleware("http")
async def bind_request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    incoming = request.headers.get("x-request-id", "").strip()
    request_id = incoming[:64] if incoming else uuid.uuid4().hex
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    client_host = request.client.host if request.client is not None else None
    request_token = request_id_var.set(request_id)
    ip_token = client_ip_var.set(forwarded or client_host)
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
    finally:
        # 放在 reset 之前，日志才能带上本次请求的 ID
        logger.info(
            "%s %s %s %.0fms ip=%s",
            request.method,
            request.url.path,
            status,
            (time.perf_counter() - started) * 1000,
            forwarded or client_host or "-",
        )
        request_id_var.reset(request_token)
        client_ip_var.reset(ip_token)
    response.headers["X-Request-ID"] = request_id
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(roles_router)
app.include_router(departments_router)
app.include_router(dicts_router)
app.include_router(records_router)
app.include_router(ingestion_router)
app.include_router(audit_router)
