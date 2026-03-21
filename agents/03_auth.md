# Агент 3 — Authentication

> Прочитай CLAUDE.md перед виконанням завдань.
> Залежить від: Агент 1 (конфіг), Агент 2 (User модель).

---

## Твоє завдання

Реалізувати повну систему автентифікації:
- JWT токен у httpOnly cookie
- Логін / логаут
- Dependencies для захисту роутів
- Створення першого адміна при старті

---

## Завдання 1 — app/services/auth_service.py

```python
from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models.user import User

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
    """Створює першого адміна якщо його немає. Викликається при старті."""
    existing = await get_user_by_email(db, settings.admin_email)
    if existing:
        return
    await create_user(
        db=db,
        email=settings.admin_email,
        name="Адміністратор",
        password=settings.admin_password,
        role="admin",
    )
    print(f"✅ Адмін створений: {settings.admin_email}")
```

---

## Завдання 2 — app/dependencies.py

```python
from __future__ import annotations
import uuid
from fastapi import Request, HTTPException, Depends, status
from sqlalchemy import select
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

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
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
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ заборонено",
        )
    return user
```

---

## Завдання 3 — app/routers/auth.py

```python
from __future__ import annotations
from fastapi import APIRouter, Request, Depends, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.auth_service import authenticate_user, create_access_token

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, email, password)

    if not user:
        request.session["flash"] = {
            "type": "error",
            "message": "Невірний email або пароль",
        }
        return RedirectResponse("/login", status_code=303)

    token = create_access_token(user.id, user.role)

    redirect_url = "/admin" if user.role == "admin" else "/dashboard"
    response = RedirectResponse(redirect_url, status_code=303)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=60 * 60 * 8,  # 8 годин
        samesite="lax",
    )
    return response


@router.post("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("access_token")
    return response
```

---

## Завдання 4 — app/templates/auth/login.html

```html
{% extends "base.html" %}

{% block title %}Вхід{% endblock %}

{% block content %}
<div class="min-h-[60vh] flex items-center justify-center">
    <div class="w-full max-w-md">
        <div class="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
            <h1 class="text-2xl font-bold text-center mb-2">🎧 Audio Quiz</h1>
            <p class="text-gray-500 text-center text-sm mb-8">Навчальна платформа для стажистів</p>

            <form action="/login" method="post" class="space-y-4">
                <div>
                    <label for="email" class="block text-sm font-medium text-gray-700 mb-1">
                        Email
                    </label>
                    <input
                        type="email"
                        id="email"
                        name="email"
                        required
                        autofocus
                        class="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        placeholder="you@company.com"
                    >
                </div>

                <div>
                    <label for="password" class="block text-sm font-medium text-gray-700 mb-1">
                        Пароль
                    </label>
                    <input
                        type="password"
                        id="password"
                        name="password"
                        required
                        class="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        placeholder="••••••••"
                    >
                </div>

                <button
                    type="submit"
                    class="w-full bg-blue-600 text-white py-2.5 px-4 rounded-lg font-medium hover:bg-blue-700 transition-colors mt-2"
                >
                    Увійти
                </button>
            </form>
        </div>
    </div>
</div>
{% endblock %}
```

---

## Завдання 5 — Оновити app/main.py

Додати реєстрацію роутера і startup подію:

```python
from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from app.config import settings
from app.database import SessionLocal
from app.services.auth_service import ensure_admin_exists
from app.routers import auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: створити адміна якщо немає
    async with SessionLocal() as db:
        await ensure_admin_exists(db)
        await db.commit()
    yield
    # Shutdown (нічого не потрібно)


app = FastAPI(title="Audio Quiz Platform", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="app/templates")

# Роутери
app.include_router(auth.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

---

## Перевірка після виконання

```bash
uvicorn app.main:app --reload
```

Потім:
1. Відкрий http://localhost:8000/login
2. Введи дані з `.env` (ADMIN_EMAIL / ADMIN_PASSWORD)
3. Повинен перенаправити на `/admin` (сторінка ще не існує — 404 це нормально)
4. Перевір cookie: DevTools → Application → Cookies → `access_token` існує і `HttpOnly: true`

---

## Що НЕ робить цей агент

- Не створює сторінки дашборду (→ Агент 4)
- Не створює адмін панель (→ Агент 5)
- Не реєструє нових користувачів через UI (адмін робить це вручну або через адмін панель)
