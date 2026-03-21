from __future__ import annotations
import hashlib
import re
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from app.config import settings


def is_manager_login(login: str) -> bool:
    """
    Визначає чи є логін числовим ID менеджера.
    Менеджерські логіни: тільки цифри (1001, 1002, ... 1050)
    Email логіни: містять @
    """
    return bool(re.match(r'^\d+$', login.strip()))


def hash_manager_password(password: str) -> str:
    """
    Подвійний md5 — формула панелі менеджера.
    md5(md5(password))
    """
    first = hashlib.md5(password.encode('utf-8')).hexdigest()
    second = hashlib.md5(first.encode('utf-8')).hexdigest()
    return second


def verify_manager_password(plain: str, stored_hash: str) -> bool:
    """Перевіряє пароль менеджера через подвійний md5."""
    return hash_manager_password(plain) == stored_hash


# ─── MySQL підключення ────────────────────────────────────────────────────────

_manager_engine = None
_manager_session_factory = None


def get_manager_engine():
    """Lazy initialization MySQL engine."""
    global _manager_engine, _manager_session_factory

    if not settings.manager_integration_enabled:
        return None, None

    if _manager_engine is None:
        _manager_engine = create_async_engine(
            settings.manager_db_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        _manager_session_factory = async_sessionmaker(
            bind=_manager_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _manager_engine, _manager_session_factory


async def get_manager_user(login: str) -> Optional[dict]:
    """
    Шукає користувача в MySQL таблиці users бази centerper.
    Повертає dict з даними або None якщо не знайдено.

    Структура таблиці:
        user_id       INT
        user_login    VARCHAR  (числовий логін: 1001, 1002...)
        user_password VARCHAR  (md5(md5(password)))
        user_hash     VARCHAR
        user_ip       VARCHAR
    """
    if not settings.manager_integration_enabled:
        return None

    _, session_factory = get_manager_engine()
    if session_factory is None:
        return None

    try:
        async with session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT user_id, user_login, user_password "
                    "FROM mansyst_users "
                    "WHERE user_login = :login "
                    "LIMIT 1"
                ),
                {"login": login.strip()}
            )
            row = result.fetchone()
            if row is None:
                return None

            user_data = {
                "user_id": row[0],
                "user_login": str(row[1]),
                "user_password": row[2],
                "name": None,
            }

            # Спробуємо отримати реальне ім'я з callcentreV2.managers
            try:
                number = int(login.strip()) - 1000
                name_result = await session.execute(
                    text(
                        "SELECT id, number, name "
                        "FROM callcentreV2.managers "
                        "WHERE number = :number "
                        "LIMIT 1"
                    ),
                    {"number": number}
                )
                name_row = name_result.fetchone()
                if name_row is not None:
                    user_data["name"] = name_row[2]
            except Exception as e:
                print(f"Warning: could not fetch manager name: {e}")

            return user_data
    except Exception as e:
        print(f"Warning: MySQL connection error: {e}")
        return None


async def authenticate_manager(login: str, password: str) -> Optional[dict]:
    """
    Автентифікує менеджера через MySQL панелі.
    Повертає dict з даними менеджера або None.
    """
    if not is_manager_login(login):
        return None

    manager = await get_manager_user(login)
    if manager is None:
        return None

    if not verify_manager_password(password, manager["user_password"]):
        return None

    return manager


async def close_manager_engine() -> None:
    """Закриває MySQL підключення при shutdown."""
    global _manager_engine
    if _manager_engine is not None:
        await _manager_engine.dispose()
        _manager_engine = None
