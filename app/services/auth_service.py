from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models.user import User, AdminPermission

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        return None


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> User | None:
    user = await get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def create_user(
    db: AsyncSession,
    email: str,
    name: str,
    password: str,
    role: str = "trainee",
) -> User:
    user = User(
        email=email,
        name=name,
        password_hash=hash_password(password),
        role=role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def ensure_admin_exists(db: AsyncSession) -> None:
    """Створює першого superadmin якщо його немає. Викликається при старті."""
    existing = await get_user_by_email(db, settings.admin_email)
    if existing:
        return
    await create_user(
        db=db,
        email=settings.admin_email,
        name="Адміністратор",
        password=settings.admin_password,
        role="superadmin",
    )
    print(f"✅ Супер-адмін створений: {settings.admin_email}")


async def get_all_admins(db: AsyncSession) -> list[User]:
    """Повертає всіх адмінів і superadmins з їхніми правами."""
    result = await db.execute(
        select(User)
        .where(User.role.in_(["admin", "superadmin"]))
        .options(selectinload(User.permissions))
        .order_by(User.role.desc(), User.name)
    )
    return list(result.scalars().all())


async def set_user_permissions(
    db: AsyncSession,
    user: User,
    permissions: list[str],
    granted_by: uuid.UUID,
) -> None:
    """Замінити всі права адміна на новий список."""
    await db.execute(
        delete(AdminPermission).where(AdminPermission.user_id == user.id)
    )
    for perm in set(permissions):
        db.add(AdminPermission(
            user_id=user.id,
            permission=perm,
            granted_by=granted_by,
        ))
    await db.flush()


async def promote_to_admin(
    db: AsyncSession,
    user: User,
    permissions: list[str],
    granted_by: uuid.UUID,
) -> None:
    """Підвищити стажиста до адміна з заданими правами."""
    user.role = "admin"
    await db.flush()
    await set_user_permissions(db, user, permissions, granted_by)


async def get_or_create_manager_user(
    db: AsyncSession,
    manager_login: str,
    manager_id: int,
    manager_name: str | None = None,
) -> User:
    """
    Знаходить або створює запис менеджера в PostgreSQL академії.
    Викликається після успішної автентифікації через MySQL.
    """
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(User)
        .where(User.manager_login_id == manager_login)
        .options(selectinload(User.permissions))
    )
    user = result.scalar_one_or_none()

    display_name = manager_name or f"Менеджер {manager_login}"

    if user:
        # Оновити ім'я якщо воно було заглушкою, а тепер є реальне
        if manager_name and user.name.startswith("Менеджер "):
            user.name = manager_name
            await db.flush()
        return user

    user = User(
        email=f"manager_{manager_login}@internal.osd24.com",
        name=display_name,
        password_hash="__EXTERNAL_AUTH__",
        role="trainee",
        manager_login_id=manager_login,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def demote_to_trainee(db: AsyncSession, user: User) -> None:
    """Зняти права адміна — повернути до стажиста."""
    await db.execute(
        delete(AdminPermission).where(AdminPermission.user_id == user.id)
    )
    user.role = "trainee"
    await db.flush()
