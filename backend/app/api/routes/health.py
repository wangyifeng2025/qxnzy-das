from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["系统"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="qxnzy-das-backend",
        version="0.1.0",
    )
