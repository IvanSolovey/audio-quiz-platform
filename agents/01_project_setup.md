# Агент 1 — Project Setup

> Прочитай CLAUDE.md перед виконанням завдань.
> Твоя зона відповідальності: скелет проєкту, залежності, конфігурація.

---

## Твоє завдання

Створити повну структуру папок проєкту і всі конфігураційні файли.
Ти НЕ пишеш бізнес-логіку — тільки scaffolding.

---

## Завдання 1 — Створи структуру папок

```bash
mkdir -p app/models app/schemas app/routers app/services
mkdir -p app/templates/auth app/templates/trainee app/templates/admin app/templates/partials
mkdir -p alembic/versions static
```

---

## Завдання 2 — requirements.txt

Створи файл `requirements.txt` з точними версіями:

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
jinja2==3.1.4
python-multipart==0.0.9
sqlalchemy[asyncio]==2.0.30
asyncpg==0.29.0
alembic==1.13.1
pydantic==2.7.1
pydantic-settings==2.2.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
boto3==1.34.100
ffmpeg-python==0.2.0
itsdangerous==2.2.0
starlette==0.37.2
```

---

## Завдання 3 — .env.example

Створи файл `.env.example`:

```
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/audioquiz

# JWT
SECRET_KEY=your-super-secret-jwt-key-minimum-32-characters-long
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480

# Cloudflare R2
R2_ACCOUNT_ID=your-cloudflare-account-id
R2_ACCESS_KEY_ID=your-r2-access-key-id
R2_SECRET_ACCESS_KEY=your-r2-secret-access-key
R2_BUCKET_NAME=audio-quiz-files
R2_PUBLIC_URL=https://pub-xxxx.r2.dev

# First admin user (created on startup)
ADMIN_EMAIL=admin@company.com
ADMIN_PASSWORD=changeme123
```

---

## Завдання 4 — app/config.py

```python
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str

    # JWT
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "audio-quiz-files"
    r2_public_url: str = ""

    # First admin
    admin_email: str = "admin@company.com"
    admin_password: str = "changeme123"


settings = Settings()
```

---

## Завдання 5 — app/database.py

```python
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

---

## Завдання 6 — app/main.py (базовий скелет)

```python
from __future__ import annotations
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from app.config import settings

app = FastAPI(title="Audio Quiz Platform", docs_url="/docs")

# Middleware
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates (доступні глобально через request.app.state)
templates = Jinja2Templates(directory="app/templates")


@app.get("/health")
async def health_check():
    return {"status": "ok"}


# TODO: Роутери будуть додані агентами 3, 4, 5
# from app.routers import auth, trainee, admin
# app.include_router(auth.router)
# app.include_router(trainee.router)
# app.include_router(admin.router)
```

---

## Завдання 7 — app/templates/base.html

Створи базовий шаблон з Tailwind і HTMX через CDN:

```html
<!DOCTYPE html>
<html lang="uk" class="h-full">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Audio Quiz{% endblock %} — Навчальна платформа</title>

    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>

    <!-- HTMX CDN -->
    <script src="https://unpkg.com/htmx.org@2.0.0" defer></script>

    {% block extra_head %}{% endblock %}
</head>
<body class="h-full bg-gray-50 text-gray-900">

    <!-- Навігація -->
    <nav class="bg-white border-b border-gray-200 px-6 py-4">
        <div class="max-w-5xl mx-auto flex items-center justify-between">
            <a href="/" class="text-lg font-semibold text-blue-600">🎧 Audio Quiz</a>

            <div class="flex items-center gap-4 text-sm">
                {% if request.state.user %}
                    <span class="text-gray-600">{{ request.state.user.name }}</span>
                    {% if request.state.user.role == 'admin' %}
                        <a href="/admin" class="text-purple-600 hover:underline">Адмін панель</a>
                    {% endif %}
                    <a href="/progress" class="hover:underline">Мій прогрес</a>
                    <form action="/logout" method="post" class="inline">
                        <button type="submit" class="text-red-500 hover:underline">Вийти</button>
                    </form>
                {% else %}
                    <a href="/login" class="text-blue-600 hover:underline">Увійти</a>
                {% endif %}
            </div>
        </div>
    </nav>

    <!-- Flash повідомлення -->
    {% if request.session.get('flash') %}
    <div class="max-w-5xl mx-auto mt-4 px-6">
        <div class="p-4 rounded-lg
            {% if request.session.flash.type == 'error' %}bg-red-50 text-red-700 border border-red-200
            {% else %}bg-green-50 text-green-700 border border-green-200{% endif %}">
            {{ request.session.pop('flash').message }}
        </div>
    </div>
    {% endif %}

    <!-- Основний контент -->
    <main class="max-w-5xl mx-auto px-6 py-8">
        {% block content %}{% endblock %}
    </main>

    {% block extra_scripts %}{% endblock %}
</body>
</html>
```

---

## Завдання 8 — .gitignore

```
__pycache__/
*.pyc
*.pyo
.env
.venv/
venv/
*.egg-info/
dist/
.DS_Store
alembic/versions/*.py
!alembic/versions/.gitkeep
static/uploads/
```

---

## Завдання 9 — README.md (базовий)

```markdown
# Audio Quiz Platform

Внутрішня платформа аудіо-квізів для стажистів.

## Технології
- FastAPI + Jinja2 + HTMX + TailwindCSS
- PostgreSQL + SQLAlchemy (async) + Alembic
- Cloudflare R2 для аудіо файлів

## Запуск локально

1. Скопіюй змінні середовища:
   cp .env.example .env
   # Відредагуй .env

2. Встанови залежності:
   pip install -r requirements.txt

3. Застосуй міграції:
   alembic upgrade head

4. Запусти:
   uvicorn app.main:app --reload

5. Відкрий http://localhost:8000
```

---

## Перевірка після виконання

Запусти і переконайся що немає помилок:

```bash
pip install -r requirements.txt
python -c "from app.config import settings; print('Config OK:', settings.algorithm)"
python -c "from app.main import app; print('App OK')"
```

Очікуваний результат:
```
Config OK: HS256
App OK
```

---

## Що НЕ робить цей агент

- Не створює моделі БД (→ Агент 2)
- Не пише автентифікацію (→ Агент 3)
- Не створює шаблони сторінок (→ Агенти 4, 5)
- Не налаштовує R2 (→ Агент 6)
