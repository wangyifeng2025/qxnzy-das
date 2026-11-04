import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.api.routes.audit import router as audit_router
from app.api.routes.auth import router as auth_router
from app.api.routes.departments import router as departments_router
from app.api.routes.dicts import router as dicts_router
from app.api.routes.health import router as health_router
from app.api.routes.roles import router as roles_router
from app.api.routes.staff import router as staff_router
from app.api.routes.users import router as users_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.request_context import client_ip_var, request_id_var

app = FastAPI(
    title="黔西南职院数据采集系统 API",
    description="校内数据汇聚、审核、发布与共享服务",
    version="0.1.0",
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
    try:
        response = await call_next(request)
    finally:
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
app.include_router(staff_router)
app.include_router(audit_router)
