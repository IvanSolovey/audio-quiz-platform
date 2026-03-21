# Агент 9 — Granular Permissions System

> Прочитай CLAUDE.md перед виконанням.
> Залежить від: Агенти 1-5 (моделі User, auth, dependencies вже існують).
> ВАЖЛИВО: цей агент розширює існуючу систему — не замінює її.

---

## Огляд

Впроваджуємо гранулярну систему прав для адміністраторів:

- `superadmin` — повний доступ, не потребує перевірки прав
- `admin` — доступ тільки до розділів де є відповідний permission
- Superadmin та довірені адміни (`manage_admins`) можуть призначати права
- Адмін не може надати права вищі за свої власні

### Permissions:
| Permission | Що дає доступ |
|------------|--------------|
| `manage_quizzes` | Створення та редагування квізів |
| `manage_knowledge` | База знань — статті та категорії |
| `view_results` | Перегляд результатів стажерів |
| `manage_users` | Додавання та редагування стажерів |
| `manage_admins` | Призначення прав іншим адмінам |

---

## Завдання 1 — Оновити app/models/user.py

Додай поле `role` з новим значенням `superadmin` та модель `AdminPermission`:

```python
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Enum, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

# Оновлений Enum — додаємо superadmin
USER_ROLES = Enum("trainee", "admin", "superadmin", name="user_role")

# Enum для прав
PERMISSION_TYPES = Enum(
    "manage_quizzes",
    "manage_knowledge",
    "view_results",
    "manage_users",
    "manage_admins",
    name="permission_type",
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        USER_ROLES, nullable=False, default="trainee"
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    quizzes_created: Mapped[list] = relationship(
        "Quiz", back_populates="creator"
    )
    attempts: Mapped[list] = relationship(
        "QuizAttempt", back_populates="user"
    )
    permissions: Mapped[list[AdminPermission]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # ─── Зручні методи перевірки прав ────────────────────────────────────────

    @property
    def is_superadmin(self) -> bool:
        return self.role == "superadmin"

    @property
    def is_admin_or_above(self) -> bool:
        return self.role in ("admin", "superadmin")

    def has_permission(self, permission: str) -> bool:
        """Перевіряє чи є у користувача конкретний дозвіл."""
        if self.is_superadmin:
            return True  # superadmin має все
        if self.role != "admin":
            return False
        return any(p.permission == permission for p in self.permissions)

    def can_manage_admin(self, target_user: User) -> bool:
        """Чи може цей юзер керувати правами target_user."""
        if self.is_superadmin:
            return True
        if not self.has_permission("manage_admins"):
            return False
        # Адмін не може керувати superadmin
        if target_user.is_superadmin:
            return False
        return True

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"


class AdminPermission(Base):
    __tablename__ = "admin_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "permission", name="uq_user_permission"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission: Mapped[str] = mapped_column(
        PERMISSION_TYPES, nullable=False
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped[User] = relationship(
        back_populates="permissions", foreign_keys=[user_id]
    )

    def __repr__(self) -> str:
        return f"<AdminPermission {self.user_id} → {self.permission}>"
```

---

## Завдання 2 — app/dependencies.py

Повністю заміни вміст на розширену версію з перевіркою прав:

```python
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
        request.state.user = None
        return None

    payload = decode_token(token)
    if not payload:
        request.state.user = None
        return None

    user_id = payload.get("sub")
    if not user_id:
        request.state.user = None
        return None

    result = await db.execute(
        select(User)
        .where(User.id == uuid.UUID(user_id))
        .options(selectinload(User.permissions))  # завжди eager load permissions
    )
    user = result.scalar_one_or_none()
    request.state.user = user
    return user


async def require_user(
    request: Request,
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
    """Дозволяє доступ адміну або superadmin (без перевірки конкретних прав)."""
    if not user.is_admin_or_above:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ заборонено",
        )
    return user


async def require_superadmin(
    user: User = Depends(require_user),
) -> User:
    """Тільки для superadmin."""
    if not user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Тільки для супер-адміністратора",
        )
    return user


def require_permission(permission: str):
    """
    Фабрика dependency для перевірки конкретного права.

    Використання:
        admin: User = Depends(require_permission("manage_quizzes"))
    """
    async def _check(user: User = Depends(require_admin)) -> User:
        if not user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Недостатньо прав: {permission}",
            )
        return user
    return _check
```

---

## Завдання 3 — Оновити app/services/auth_service.py

Додай `ensure_admin_exists` з роллю `superadmin` та функції управління правами:

```python
# Знайди функцію ensure_admin_exists і заміни на:
async def ensure_admin_exists(db: AsyncSession) -> None:
    """Створює першого superadmin якщо його немає."""
    existing = await get_user_by_email(db, settings.admin_email)
    if existing:
        # Якщо існує але не superadmin — підвищуємо
        if existing.role != "superadmin":
            existing.role = "superadmin"
            await db.flush()
        return

    user = User(
        email=settings.admin_email,
        name="Супер-адміністратор",
        password_hash=hash_password(settings.admin_password),
        role="superadmin",
    )
    db.add(user)
    await db.flush()
    print(f"✅ Супер-адмін створений: {settings.admin_email}")


# Додай нові функції в кінець файлу:

async def get_all_admins(db: AsyncSession) -> list[User]:
    """Отримати всіх адмінів та superadmin з їх правами."""
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(User)
        .where(User.role.in_(["admin", "superadmin"]))
        .options(selectinload(User.permissions))
        .order_by(User.role.desc(), User.name)
    )
    return list(result.scalars().all())


async def set_user_permissions(
    db: AsyncSession,
    target_user: User,
    permissions: list[str],
    granted_by_id: uuid.UUID,
) -> User:
    """
    Замінює всі права користувача на новий список.
    Якщо permissions порожній — всі права видаляються.
    """
    from app.models.user import AdminPermission

    # Видаляємо старі права
    for perm in list(target_user.permissions):
        await db.delete(perm)
    await db.flush()

    # Додаємо нові
    for perm_name in permissions:
        perm = AdminPermission(
            user_id=target_user.id,
            permission=perm_name,
            granted_by=granted_by_id,
        )
        db.add(perm)

    await db.flush()
    await db.refresh(target_user)
    return target_user


async def promote_to_admin(
    db: AsyncSession,
    user: User,
    permissions: list[str],
    granted_by_id: uuid.UUID,
) -> User:
    """Підвищує trainee до admin з вказаними правами."""
    user.role = "admin"
    await db.flush()
    return await set_user_permissions(db, user, permissions, granted_by_id)


async def demote_to_trainee(db: AsyncSession, user: User) -> User:
    """Знижує admin до trainee, видаляє всі права."""
    user.role = "trainee"
    for perm in list(user.permissions):
        await db.delete(perm)
    await db.flush()
    return user
```

---

## Завдання 4 — Оновити роутери з новими dependencies

### app/routers/admin.py
Заміни `require_admin` на `require_permission` для кожного розділу:

```python
from app.dependencies import require_admin, require_permission, require_superadmin

# Дашборд — базовий доступ для будь-якого адміна
@router.get("", ...)
async def admin_dashboard(..., admin: User = Depends(require_admin)):

# Квізи — потрібен manage_quizzes
@router.get("/quiz/new", ...)
async def new_quiz_page(..., admin: User = Depends(require_permission("manage_quizzes"))):

@router.post("/quiz/new", ...)
async def create_quiz(..., admin: User = Depends(require_permission("manage_quizzes"))):

@router.get("/quiz/{quiz_id}", ...)
async def edit_quiz_page(..., admin: User = Depends(require_permission("manage_quizzes"))):

@router.post("/quiz/{quiz_id}/update", ...)
async def update_quiz(..., admin: User = Depends(require_permission("manage_quizzes"))):

@router.post("/quiz/{quiz_id}/delete", ...)
async def delete_quiz(..., admin: User = Depends(require_permission("manage_quizzes"))):

@router.post("/quiz/{quiz_id}/question/add", ...)
async def add_question(..., admin: User = Depends(require_permission("manage_quizzes"))):

@router.post("/quiz/{quiz_id}/question/{question_id}/delete", ...)
async def delete_question(..., admin: User = Depends(require_permission("manage_quizzes"))):

# Результати — потрібен view_results
@router.get("/results", ...)
async def results_page(..., admin: User = Depends(require_permission("view_results"))):

# Користувачі — потрібен manage_users
@router.get("/users", ...)
async def users_page(..., admin: User = Depends(require_permission("manage_users"))):

@router.post("/users/add", ...)
async def add_user(..., admin: User = Depends(require_permission("manage_users"))):
```

### app/routers/admin_docs.py
```python
# Всі роути бази знань
admin: User = Depends(require_permission("manage_knowledge"))
```

---

## Завдання 5 — Новий роутер app/routers/admin_permissions.py

```python
from __future__ import annotations
import uuid
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_permission, require_superadmin
from app.models.user import User, AdminPermission
from app.services.auth_service import (
    get_all_admins,
    get_user_by_email,
    create_user,
    promote_to_admin,
    demote_to_trainee,
    set_user_permissions,
)

router = APIRouter(prefix="/admin/permissions", tags=["admin-permissions"])
templates = Jinja2Templates(directory="app/templates")

ALL_PERMISSIONS = [
    ("manage_quizzes", "Управління квізами", "📝"),
    ("manage_knowledge", "База знань", "📚"),
    ("view_results", "Результати стажерів", "📊"),
    ("manage_users", "Управління стажерами", "👥"),
    ("manage_admins", "Призначення прав адмінам", "🔑"),
]


@router.get("", response_class=HTMLResponse)
async def permissions_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_admins")),
):
    admins = await get_all_admins(db)

    # Всі стажери для форми підвищення
    result = await db.execute(
        select(User)
        .where(User.role == "trainee")
        .order_by(User.name)
    )
    trainees = list(result.scalars().all())

    return templates.TemplateResponse("admin/permissions.html", {
        "request": request,
        "admins": admins,
        "trainees": trainees,
        "all_permissions": ALL_PERMISSIONS,
        "user": admin,
    })


@router.post("/promote")
async def promote_user(
    request: Request,
    user_id: str = Form(...),
    permissions: list[str] = Form(default=[]),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_admins")),
):
    """Підвищити стажиста до адміна з вибраними правами."""
    result = await db.execute(
        select(User)
        .where(User.id == uuid.UUID(user_id))
        .options(selectinload(User.permissions))
    )
    target = result.scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404)

    # Перевірка: адмін без superadmin не може давати manage_admins
    # якщо сам його не має
    if not admin.is_superadmin and "manage_admins" in permissions:
        if not admin.has_permission("manage_admins"):
            request.session["flash"] = {
                "type": "error",
                "message": "Ти не можеш надати право manage_admins без власного права",
            }
            return RedirectResponse("/admin/permissions", status_code=303)

    await promote_to_admin(db, target, permissions, admin.id)
    await db.commit()

    request.session["flash"] = {
        "type": "success",
        "message": f"{target.name} тепер адміністратор!",
    }
    return RedirectResponse("/admin/permissions", status_code=303)


@router.post("/{user_id}/update")
async def update_permissions(
    request: Request,
    user_id: uuid.UUID,
    permissions: list[str] = Form(default=[]),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_admins")),
):
    """Оновити права існуючого адміна."""
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.permissions))
    )
    target = result.scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404)

    # Не можна змінювати superadmin
    if not admin.can_manage_admin(target):
        raise HTTPException(
            status_code=403,
            detail="Недостатньо прав для керування цим адміністратором",
        )

    await set_user_permissions(db, target, permissions, admin.id)
    await db.commit()

    request.session["flash"] = {
        "type": "success",
        "message": f"Права {target.name} оновлено!",
    }
    return RedirectResponse("/admin/permissions", status_code=303)


@router.post("/{user_id}/demote")
async def demote_admin(
    request: Request,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_admins")),
):
    """Зняти права адміна — повернути до стажиста."""
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.permissions))
    )
    target = result.scalar_one_or_none()

    if not target or not admin.can_manage_admin(target):
        raise HTTPException(status_code=403)

    await demote_to_trainee(db, target)
    await db.commit()

    request.session["flash"] = {
        "type": "success",
        "message": f"{target.name} повернуто до стажиста",
    }
    return RedirectResponse("/admin/permissions", status_code=303)
```

---

## Завдання 6 — app/templates/admin/permissions.html

```html
{% extends "base.html" %}
{% block title %}Управління правами{% endblock %}

{% block content %}
<div class="flex items-center gap-3 mb-8">
  <a href="/admin" class="text-sm hover:underline"
     style="color: var(--color-text-muted);">← Адмін панель</a>
  <h1 class="text-2xl font-bold" style="font-family: var(--font-display);">
    🔑 Управління адміністраторами
  </h1>
</div>

<div class="grid grid-cols-3 gap-6">

  <!-- Список адмінів -->
  <div class="col-span-2 space-y-4">
    <h2 class="font-bold text-sm uppercase tracking-wide"
        style="color: var(--color-text-muted);">
      Поточні адміністратори
    </h2>

    {% for admin_user in admins %}
    <div class="rounded-2xl overflow-hidden"
         style="background: var(--color-surface);
                border: 1px solid var(--color-border);
                box-shadow: var(--shadow-sm);">

      <!-- Header -->
      <div class="flex items-center justify-between px-6 py-4"
           style="border-bottom: 1px solid var(--color-border);">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-full flex items-center justify-center
                      text-white text-sm font-bold"
               style="background: {% if admin_user.is_superadmin %}var(--color-accent)
                      {% else %}var(--color-primary){% endif %};">
            {{ admin_user.name[0] | upper }}
          </div>
          <div>
            <p class="font-bold text-sm"
               style="font-family: var(--font-display);">
              {{ admin_user.name }}
            </p>
            <p class="text-xs" style="color: var(--color-text-muted);">
              {{ admin_user.email }}
            </p>
          </div>
          {% if admin_user.is_superadmin %}
          <span class="px-2.5 py-1 rounded-lg text-xs font-bold"
                style="background: #FFF7ED; color: var(--color-accent);">
            ⭐ Супер-адмін
          </span>
          {% endif %}
        </div>

        {% if not admin_user.is_superadmin and user.can_manage_admin(admin_user) %}
        <form action="/admin/permissions/{{ admin_user.id }}/demote" method="post"
              onsubmit="return confirm('Зняти права адміна у {{ admin_user.name }}?')">
          <button type="submit" class="text-xs px-3 py-1.5 rounded-lg"
                  style="color: var(--color-error); border: 1px solid #FECACA;">
            Зняти права
          </button>
        </form>
        {% endif %}
      </div>

      <!-- Permissions -->
      {% if not admin_user.is_superadmin %}
      <div class="px-6 py-4">
        <form action="/admin/permissions/{{ admin_user.id }}/update" method="post">
          <div class="grid grid-cols-2 gap-2 mb-4">
            {% for perm_key, perm_label, perm_icon in all_permissions %}
            <label class="flex items-center gap-2.5 p-3 rounded-xl cursor-pointer
                          transition-all"
                   style="border: 1.5px solid
                     {% if admin_user.has_permission(perm_key) %}var(--color-primary){% else %}var(--color-border){% endif %};
                     background:
                     {% if admin_user.has_permission(perm_key) %}#EEF4FF{% else %}transparent{% endif %};">
              <input type="checkbox" name="permissions" value="{{ perm_key }}"
                     {% if admin_user.has_permission(perm_key) %}checked{% endif %}
                     {% if perm_key == 'manage_admins' and not user.is_superadmin and not user.has_permission('manage_admins') %}
                     disabled{% endif %}
                     class="w-4 h-4">
              <span class="text-sm">{{ perm_icon }} {{ perm_label }}</span>
            </label>
            {% endfor %}
          </div>
          {% if user.can_manage_admin(admin_user) %}
          <button type="submit"
                  class="px-4 py-2 rounded-lg text-white text-sm font-semibold"
                  style="background: var(--color-primary);">
            Зберегти права
          </button>
          {% endif %}
        </form>
      </div>
      {% else %}
      <div class="px-6 py-3">
        <p class="text-sm" style="color: var(--color-text-muted);">
          Супер-адмін має повний доступ до всього
        </p>
      </div>
      {% endif %}

    </div>
    {% endfor %}

    {% if not admins %}
    <div class="text-center py-8" style="color: var(--color-text-muted);">
      <p>Адміністраторів ще немає</p>
    </div>
    {% endif %}
  </div>

  <!-- Sidebar: підвищити стажиста -->
  <div>
    <div class="rounded-2xl p-6 sticky top-6"
         style="background: var(--color-surface);
                border: 1px solid var(--color-border);
                box-shadow: var(--shadow-sm);">
      <h2 class="font-bold text-sm mb-4" style="font-family: var(--font-display);">
        Призначити адміністратора
      </h2>

      <form action="/admin/permissions/promote" method="post" class="space-y-4">

        <div>
          <label class="text-xs font-medium block mb-1"
                 style="color: var(--color-text-muted);">
            Стажист
          </label>
          <select name="user_id" required
                  class="w-full px-3 py-2.5 rounded-xl text-sm outline-none"
                  style="border: 1.5px solid var(--color-border);">
            <option value="">Обери стажиста...</option>
            {% for trainee in trainees %}
            <option value="{{ trainee.id }}">
              {{ trainee.name }} ({{ trainee.email }})
            </option>
            {% endfor %}
          </select>
        </div>

        <div>
          <label class="text-xs font-medium block mb-2"
                 style="color: var(--color-text-muted);">
            Права доступу
          </label>
          <div class="space-y-2">
            {% for perm_key, perm_label, perm_icon in all_permissions %}
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" name="permissions" value="{{ perm_key }}"
                     {% if perm_key == 'manage_admins' and not user.is_superadmin
                        and not user.has_permission('manage_admins') %}
                     disabled{% endif %}
                     class="w-4 h-4">
              <span class="text-sm">{{ perm_icon }} {{ perm_label }}</span>
            </label>
            {% endfor %}
          </div>
        </div>

        <button type="submit"
                class="w-full py-2.5 rounded-xl text-white text-sm font-semibold"
                style="background: var(--color-accent);">
          Призначити адміністратором
        </button>
      </form>
    </div>
  </div>

</div>
{% endblock %}
```

---

## Завдання 7 — Оновити адмін дашборд (admin/dashboard.html)

Додай блок навігації з перевіркою прав — адмін бачить тільки доступні розділи:

```html
<!-- Замінити секцію навігації на: -->
<div class="flex gap-2 mb-6 text-sm flex-wrap">
  {% if user.has_permission('view_results') %}
  <a href="/admin/results"
     class="px-4 py-2 rounded-lg hover:opacity-80 transition-all"
     style="background: var(--color-bg); border: 1px solid var(--color-border);">
    📊 Результати
  </a>
  {% endif %}

  {% if user.has_permission('manage_users') %}
  <a href="/admin/users"
     class="px-4 py-2 rounded-lg hover:opacity-80 transition-all"
     style="background: var(--color-bg); border: 1px solid var(--color-border);">
    👥 Команда
  </a>
  {% endif %}

  {% if user.has_permission('manage_knowledge') %}
  <a href="/admin/docs"
     class="px-4 py-2 rounded-lg hover:opacity-80 transition-all"
     style="background: var(--color-bg); border: 1px solid var(--color-border);">
    📚 База знань
  </a>
  {% endif %}

  {% if user.has_permission('manage_admins') %}
  <a href="/admin/permissions"
     class="px-4 py-2 rounded-lg hover:opacity-80 transition-all"
     style="background: #FFF7ED; border: 1px solid #FED7AA; color: var(--color-accent);">
    🔑 Права доступу
  </a>
  {% endif %}
</div>

<!-- Кнопка "Новий квіз" показується тільки при наявності права -->
{% if user.has_permission('manage_quizzes') %}
<a href="/admin/quiz/new" ...>+ Створити тест</a>
{% endif %}
```

---

## Завдання 8 — Додати роутер у app/main.py

```python
from app.routers import auth, trainee, admin, docs, admin_docs, admin_permissions

app.include_router(admin_permissions.router)
```

---

## Завдання 9 — Alembic міграція

```bash
alembic revision --autogenerate -m "add_permissions_and_superadmin"
alembic upgrade head
```

Перевір що створилась таблиця `admin_permissions` і оновився enum `user_role` з `superadmin`.

---

## Перевірка після виконання

```bash
uvicorn app.main:app --reload
```

Чекліст:
- [ ] `/admin/permissions` доступний для superadmin
- [ ] Можна підвищити стажиста до адміна з вибраними правами
- [ ] Адмін без `manage_quizzes` отримує 403 на `/admin/quiz/new`
- [ ] Адмін без `manage_admins` не бачить розділ "Права доступу"
- [ ] Superadmin бачить і має доступ до всього
- [ ] `user.has_permission()` в шаблонах правильно приховує/показує елементи
