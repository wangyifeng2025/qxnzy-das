from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.models.system import User
from app.schemas.common import Message
from app.schemas.system import CurrentUser as CurrentUserSchema
from app.schemas.system import LoginRequest, PasswordChange, Token
from app.services.audit import write_audit
from app.services.system import authenticate, set_password, user_to_current

router = APIRouter(prefix="/api/auth", tags=["认证"])


def _issue_token(user: User) -> Token:
    token = create_access_token(str(user.id), {"account": user.account})
    return Token(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=user_to_current(user),
    )


@router.post("/login", response_model=Token, summary="账号密码登录")
async def login(payload: LoginRequest, session: DbSession) -> Token:
    user = await authenticate(session, payload.account, payload.password)
    return _issue_token(user)


@router.post("/token", response_model=Token, summary="OAuth2 表单登录（供 Swagger 使用）")
async def login_form(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], session: DbSession
) -> Token:
    user = await authenticate(session, form.username, form.password)
    return _issue_token(user)


@router.get("/me", response_model=CurrentUserSchema, summary="当前登录用户")
async def read_me(user: CurrentUser) -> CurrentUserSchema:
    return user_to_current(user)


@router.post("/change-password", response_model=Message, summary="修改本人密码")
async def change_password(
    payload: PasswordChange, user: CurrentUser, session: DbSession
) -> Message:
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="原密码不正确")
    set_password(user, payload.new_password)
    await write_audit(
        session,
        action="auth.change_password",
        resource_type="user",
        resource_id=str(user.id),
        summary=f"修改本人密码：{user.account}",
        actor=user,
    )
    await session.commit()
    return Message(detail="密码已更新")
