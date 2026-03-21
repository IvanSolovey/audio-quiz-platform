from __future__ import annotations
import uuid
from fastapi import Request, HTTPException, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.services.auth_service import decode_token


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    token = request.cookies.get("access_token")
    if not token:
        return None

    payload = decode_token(token)
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    result = await db.execute(
        select(User)
        .where(User.id == uuid.UUID(user_id))
        .options(selectinload(User.permissions))
    )
    user = result.scalar_one_or_none()

    # Зберігаємо у request.state для шаблонів
    request.state.user = user
    return user


async def require_user(
    user: User | None = Depends(get_current_user),
) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    return user


async def require_admin(
    user: User = Depends(require_user),
) -> User:
    if not user.is_admin_or_above:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ заборонено",
        )
    return user


async def require_superadmin(
    user: User = Depends(require_user),
) -> User:
    if not user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Тільки супер-адмін має доступ",
        )
    return user


def require_permission(permission: str):
    """Dependency factory — перевіряє конкретне право адміна."""
    async def _check(user: User = Depends(require_admin)) -> User:
        if not user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Потрібне право: {permission}",
            )
        return user
    return _check
