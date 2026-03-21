# Агент 12 — MySQL Manager Panel Integration

> Прочитай CLAUDE.md перед виконанням.
> Залежить від: Агенти 1-5 (auth система вже існує).
> Цей агент РОЗШИРЮЄ існуючу автентифікацію — не замінює її.

---

## Огляд

Інтеграція з панеллю менеджера через пряме підключення до MySQL.

**Як працює:**
- Користувач вводить числовий ID (1001) замість email
- Академія визначає тип логіну і шукає в потрібній БД
- MySQL: перевіряє `md5(md5(password))` проти `user_password`
- Якщо ок → створює або оновлює запис в PostgreSQL академії
- Видає JWT і пускає в систему з роллю `trainee`

**Формула паролю панелі менеджера:**
```python
md5(md5(password)) == user_password
```

---

## Завдання 1 — Додати MySQL змінні в .env.example

```dotenv
# MySQL — Панель менеджера (інтеграція)
MANAGER_DB_HOST=localhost
MANAGER_DB_PORT=3306
MANAGER_DB_USER=your_mysql_user
MANAGER_DB_PASSWORD=your_mysql_password
MANAGER_DB_NAME=centerper
MANAGER_INTEGRATION_ENABLED=true
```

---

## Завдання 2 — Оновити app/config.py

Додай нові поля в клас `Settings`:

```python
# MySQL — Панель менеджера
manager_db_host: str = "localhost"
manager_db_port: int = 3306
manager_db_user: str = ""
manager_db_password: str = ""
manager_db_name: str = "centerper"
manager_integration_enabled: bool = False

@property
def manager_db_url(self) -> str:
    return (
        f"mysql+aiomysql://{self.manager_db_user}:"
        f"{self.manager_db_password}@{self.manager_db_host}:"
        f"{self.manager_db_port}/{self.manager_db_name}"
        f"?charset=utf8mb4"
    )
```

---

## Завдання 3 — Встанови залежності

Додай до `requirements.txt`:
```
aiomysql==0.2.0
PyMySQL==1.1.0
```

Встанови:
```bash
pip install aiomysql==0.2.0 PyMySQL==1.1.0
```

---

## Завдання 4 — app/services/manager_auth_service.py

```python
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
                    "FROM users "
                    "WHERE user_login = :login "
                    "LIMIT 1"
                ),
                {"login": login.strip()}
            )
            row = result.fetchone()
            if row is None:
                return None
            return {
                "user_id": row[0],
                "user_login": str(row[1]),
                "user_password": row[2],
            }
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
```

---

## Завдання 5 — Оновити app/models/user.py

Додай поле `manager_login_id` для зв'язку з панеллю менеджера:

```python
# Додай це поле в клас User після поля password_hash:
manager_login_id: Mapped[str | None] = mapped_column(
    String(20),
    unique=True,
    nullable=True,
    index=True,
    comment="Числовий ID з панелі менеджера (1001, 1002...)"
)
```

Після цього зроби міграцію:
```bash
alembic revision --autogenerate -m "add_manager_login_id_to_users"
alembic upgrade head
```

---

## Завдання 6 — Оновити app/services/auth_service.py

Додай функцію для створення/оновлення менеджера в PostgreSQL:

```python
async def get_or_create_manager_user(
    db: AsyncSession,
    manager_login: str,
    manager_id: int,
) -> User:
    """
    Знаходить або створює запис менеджера в PostgreSQL академії.
    Викликається після успішної автентифікації через MySQL.
    """
    from sqlalchemy.orm import selectinload

    # Шукаємо по manager_login_id
    result = await db.execute(
        select(User)
        .where(User.manager_login_id == manager_login)
        .options(selectinload(User.permissions))
    )
    user = result.scalar_one_or_none()

    if user:
        return user  # вже існує — повертаємо

    # Створюємо нового
    user = User(
        email=f"manager_{manager_login}@internal.osd24.com",  # технічний email
        name=f"Менеджер {manager_login}",
        password_hash="__EXTERNAL_AUTH__",  # не використовується для входу
        role="trainee",
        manager_login_id=manager_login,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user
```

---

## Завдання 7 — Оновити app/routers/auth.py

Розшир логіку POST /login щоб підтримувати обидва типи входу:

```python
from app.services.manager_auth_service import (
    is_manager_login,
    authenticate_manager,
)
from app.services.auth_service import get_or_create_manager_user


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    email: str = Form(...),   # поле називається email але приймає і числовий логін
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = None

    # ─── Визначаємо тип логіну ────────────────────────────────────────────────
    if is_manager_login(email):
        # Числовий логін → перевіряємо в MySQL панелі менеджера
        manager_data = await authenticate_manager(email, password)

        if manager_data is None:
            request.session["flash"] = {
                "type": "error",
                "message": "Невірний ID або пароль",
            }
            return RedirectResponse("/login", status_code=303)

        # Знайти або створити запис в PostgreSQL
        user = await get_or_create_manager_user(
            db=db,
            manager_login=email,
            manager_id=manager_data["user_id"],
        )
        await db.commit()

    else:
        # Email логін → стандартна автентифікація через PostgreSQL
        user = await authenticate_user(db, email, password)

        if not user:
            request.session["flash"] = {
                "type": "error",
                "message": "Невірний email або пароль. Спробуй ще раз або зверніться до керівника",
            }
            return RedirectResponse("/login", status_code=303)

    # ─── Видати JWT ───────────────────────────────────────────────────────────
    token = create_access_token(user.id, user.role)
    redirect_url = "/admin" if user.is_admin_or_above else "/dashboard"

    response = RedirectResponse(redirect_url, status_code=303)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=60 * 60 * 8,
        samesite="lax",
    )
    return response
```

---

## Завдання 8 — Оновити app/templates/auth/login.html

Зміни підпис поля email та підказку:

```html
<!-- Замінити label і placeholder поля email на: -->
<label for="email" class="block text-sm font-medium mb-1.5"
       style="color: var(--color-text);">
  Email або ID менеджера
</label>
<input
  type="text"
  id="email"
  name="email"
  required
  autofocus
  placeholder="your.name@osd24.com або 1001"
  ...existing styles...>

<!-- Під кнопкою входу додати підказку: -->
<p class="text-center text-xs mt-4" style="color: var(--color-text-muted);">
  Менеджери входять за своїм числовим ID
</p>
```

---

## Завдання 9 — Оновити app/main.py (shutdown)

Додай закриття MySQL при shutdown:

```python
from app.services.manager_auth_service import close_manager_engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with SessionLocal() as db:
        await ensure_admin_exists(db)
        await db.commit()
    yield
    # Shutdown
    await close_manager_engine()
```

---

## Завдання 10 — Оновити .env

Додай реальні дані підключення до MySQL:

```dotenv
# MySQL — Панель менеджера
MANAGER_DB_HOST=localhost
MANAGER_DB_PORT=3306
MANAGER_DB_USER=твій_mysql_користувач
MANAGER_DB_PASSWORD=твій_mysql_пароль
MANAGER_DB_NAME=centerper
MANAGER_INTEGRATION_ENABLED=true
```

**ВАЖЛИВО:** Вставляй реальні credentials тільки в `.env` файл — не в код і не в чат.

---

## Перевірка після виконання

```bash
# 1. Міграція
alembic upgrade head

# 2. Запуск
uvicorn app.main:app --reload

# 3. Тест підключення до MySQL
python3 -c "
import asyncio
from app.services.manager_auth_service import get_manager_user
async def test():
    user = await get_manager_user('1001')
    print('MySQL user:', user)
asyncio.run(test())
"
```

Чекліст:
- [ ] MySQL підключення працює без помилок
- [ ] `get_manager_user('1001')` повертає дані користувача
- [ ] Вхід через `1001` + пароль → редирект на `/dashboard`
- [ ] Вхід через `admin@company.com` + пароль → редирект на `/admin` (старий логін не зламався)
- [ ] Повторний вхід менеджера не створює дублікат в PostgreSQL
- [ ] JWT видається коректно для обох типів користувачів
