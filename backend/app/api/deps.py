from collections.abc import Callable, Coroutine
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db import get_db_session
from app.models.system import User, UserStatus

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(
    session: DbSession, token: Annotated[str, Depends(oauth2_scheme)]
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录状态无效或已过期，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise credentials_error from exc
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdigit():
        raise credentials_error
    user = await session.scalar(select(User).where(User.id == int(subject)))
    if user is None:
        raise credentials_error
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="账号已停用，请联系信息中心")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permissions(
    *codes: str,
) -> Callable[..., Coroutine[Any, Any, User]]:
    """要求当前用户拥有全部给定权限；超级管理员直接放行。"""

    async def dependency(user: CurrentUser) -> User:
        if user.is_superuser:
            return user
        missing = set(codes) - user.permission_codes
        if missing:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"缺少权限：{', '.join(sorted(missing))}",
            )
        return user

    return dependency
