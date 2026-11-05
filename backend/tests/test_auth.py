from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.system import User, UserStatus


async def test_login_success_and_failure(client: AsyncClient) -> None:
    wrong = await client.post(
        "/api/auth/login",
        json={"account": "admin", "password": "wrong-password"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "账号或密码不正确"

    ok = await client.post(
        "/api/auth/login",
        json={"account": "admin", "password": settings.initial_admin_password},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["account"] == "admin"
    assert "fill:submit" in body["user"]["permissions"]


async def test_disabled_account_cannot_login(client: AsyncClient, db_session: AsyncSession) -> None:
    db_session.add(
        User(
            account="disabled01",
            name="停用账号",
            password_hash=hash_password("123456"),
            status=UserStatus.DISABLED,
        )
    )
    await db_session.commit()

    response = await client.post(
        "/api/auth/login",
        json={"account": "disabled01", "password": "123456"},
    )
    assert response.status_code == 403

    me = await client.get("/api/auth/me")
    assert me.status_code == 401


async def test_auditor_outside_personnel_cannot_submit_staff(client: AsyncClient) -> None:
    login = await client.post(
        "/api/auth/login",
        json={"account": "kyc01", "password": "123456"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    meta = await client.get(
        "/api/datasets/ODS_JZGJBSJ/meta",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert meta.status_code == 200
    assert meta.json()["can_fill"] is False
    assert meta.json()["departments"] == []


async def test_current_user_requires_token(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await db_session.scalar(select(User).where(User.account == "admin"))
    assert user is not None
    response = await client.get("/api/auth/me")
    assert response.status_code == 401
