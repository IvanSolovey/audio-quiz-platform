# Агент 11 — Announcements System (Система оповіщень)

> Прочитай CLAUDE.md перед виконанням.
> Залежить від: Агенти 1-5, Агент 9 (permissions).

---

## Огляд

Система модальних оповіщень які адмін створює і призначає аудиторії.

**Ключові правила:**
- Оповіщення показується при першому вході після його публікації
- Кожен юзер бачить оповіщення рівно один раз (після закриття — записується як прочитане)
- Якщо є кілька непрочитаних — показуємо по одному після закриття попереднього
- HTMX керує показом без перезавантаження сторінки
- Адмін може мати право `manage_announcements` (додати в permissions)

---

## Завдання 1 — app/models/announcement.py

```python
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import (
    String, Boolean, Text, DateTime,
    ForeignKey, Enum, func, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

AUDIENCE_TYPES = Enum(
    "all",        # всі користувачі платформи
    "trainees",   # тільки стажери
    "admins",     # тільки адміни
    name="announcement_audience",
)


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # CTA (необов'язково)
    cta_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cta_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Налаштування
    audience: Mapped[str] = mapped_column(
        AUDIENCE_TYPES, nullable=False, default="all"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Мета
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    reads: Mapped[list[AnnouncementRead]] = relationship(
        back_populates="announcement",
        cascade="all, delete-orphan",
    )
    author: Mapped[User | None] = relationship(foreign_keys=[created_by])

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        from datetime import timezone
        return datetime.now(timezone.utc) > self.expires_at

    def __repr__(self) -> str:
        return f"<Announcement '{self.title}' → {self.audience}>"


class AnnouncementRead(Base):
    __tablename__ = "announcement_reads"
    __table_args__ = (
        UniqueConstraint(
            "announcement_id", "user_id",
            name="uq_announcement_user"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    announcement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    announcement: Mapped[Announcement] = relationship(back_populates="reads")
    user: Mapped[User] = relationship()
```

---

## Завдання 2 — Оновити app/models/__init__.py

```python
from app.models.announcement import Announcement, AnnouncementRead

__all__ = [
    ...,  # існуючі
    "Announcement", "AnnouncementRead",
]
```

---

## Завдання 3 — Alembic міграція

```bash
alembic revision --autogenerate -m "add_announcements"
alembic upgrade head
```

Перевір що створились таблиці `announcements` та `announcement_reads`.

---

## Завдання 4 — app/services/announcement_service.py

```python
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, and_, or_, not_, exists
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.announcement import Announcement, AnnouncementRead
from app.models.user import User


async def get_pending_announcements(
    db: AsyncSession,
    user: User,
) -> list[Announcement]:
    """
    Повертає список активних непрочитаних оповіщень для конкретного юзера.
    Відфільтровані за аудиторією, активністю та датою закінчення.
    Відсортовані від найстаріших до найновіших (показуємо в порядку створення).
    """
    now = datetime.now(timezone.utc)

    # Підзапит: чи вже прочитав цей юзер
    already_read = (
        select(AnnouncementRead.announcement_id)
        .where(AnnouncementRead.user_id == user.id)
        .scalar_subquery()
    )

    # Аудиторія яка підходить цьому юзеру
    if user.role == "trainee":
        audience_filter = Announcement.audience.in_(["all", "trainees"])
    elif user.is_admin_or_above:
        audience_filter = Announcement.audience.in_(["all", "admins"])
    else:
        audience_filter = Announcement.audience == "all"

    stmt = (
        select(Announcement)
        .where(
            and_(
                Announcement.is_active == True,
                audience_filter,
                Announcement.id.not_in(already_read),
                or_(
                    Announcement.expires_at == None,
                    Announcement.expires_at > now,
                ),
            )
        )
        .order_by(Announcement.created_at.asc())
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def mark_as_read(
    db: AsyncSession,
    announcement_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Позначити оповіщення як прочитане. Ігнорує якщо вже прочитане."""
    # Перевірити чи вже є запис
    existing = await db.execute(
        select(AnnouncementRead).where(
            AnnouncementRead.announcement_id == announcement_id,
            AnnouncementRead.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        return  # вже прочитано — нічого не робимо

    read = AnnouncementRead(
        announcement_id=announcement_id,
        user_id=user_id,
    )
    db.add(read)
    await db.flush()


async def get_all_announcements(
    db: AsyncSession,
) -> list[Announcement]:
    """Всі оповіщення для адмін панелі."""
    result = await db.execute(
        select(Announcement)
        .options(selectinload(Announcement.reads))
        .order_by(Announcement.created_at.desc())
    )
    return list(result.scalars().all())


async def get_announcement_by_id(
    db: AsyncSession,
    announcement_id: uuid.UUID,
) -> Announcement | None:
    result = await db.execute(
        select(Announcement)
        .where(Announcement.id == announcement_id)
        .options(selectinload(Announcement.reads))
    )
    return result.scalar_one_or_none()


async def create_announcement(
    db: AsyncSession,
    title: str,
    body: str,
    audience: str,
    created_by: uuid.UUID,
    cta_text: str | None = None,
    cta_url: str | None = None,
    expires_at: datetime | None = None,
) -> Announcement:
    announcement = Announcement(
        title=title.strip(),
        body=body.strip(),
        audience=audience,
        created_by=created_by,
        cta_text=cta_text.strip() if cta_text else None,
        cta_url=cta_url.strip() if cta_url else None,
        expires_at=expires_at,
        is_active=True,
    )
    db.add(announcement)
    await db.flush()
    await db.refresh(announcement)
    return announcement


async def toggle_announcement(
    db: AsyncSession,
    announcement: Announcement,
) -> Announcement:
    """Вмикає/вимикає оповіщення."""
    announcement.is_active = not announcement.is_active
    await db.flush()
    return announcement


async def delete_announcement(
    db: AsyncSession,
    announcement: Announcement,
) -> None:
    await db.delete(announcement)
    await db.flush()
```

---

## Завдання 5 — app/routers/announcements.py (для стажистів)

```python
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_user
from app.models.user import User
from app.services.announcement_service import (
    get_pending_announcements,
    mark_as_read,
)

router = APIRouter(prefix="/announcements", tags=["announcements"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/check", response_class=HTMLResponse)
async def check_announcements(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """
    HTMX ендпоінт — перевіряє чи є непрочитані оповіщення.
    Повертає HTML модаль або порожній рядок.
    Викликається автоматично при завантаженні dashboard.
    """
    pending = await get_pending_announcements(db, current_user)

    if not pending:
        return HTMLResponse("")  # нічого показувати

    # Показуємо перше непрочитане
    announcement = pending[0]
    remaining = len(pending) - 1  # скільки ще залишилось після цього

    return templates.TemplateResponse(
        "partials/announcement_modal.html",
        {
            "request": request,
            "announcement": announcement,
            "remaining": remaining,
        },
    )


@router.post("/{announcement_id}/read", response_class=HTMLResponse)
async def mark_read(
    request: Request,
    announcement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """
    HTMX ендпоінт — позначає оповіщення як прочитане.
    Після цього перевіряє чи є ще непрочитані і повертає наступне або порожній рядок.
    """
    await mark_as_read(db, announcement_id, current_user.id)
    await db.commit()

    # Перевірити чи є ще непрочитані
    pending = await get_pending_announcements(db, current_user)

    if not pending:
        return HTMLResponse("")  # більше немає — закриваємо

    # Є ще — показати наступне
    next_announcement = pending[0]
    remaining = len(pending) - 1

    return templates.TemplateResponse(
        "partials/announcement_modal.html",
        {
            "request": request,
            "announcement": next_announcement,
            "remaining": remaining,
        },
    )
```

---

## Завдання 6 — app/routers/admin_announcements.py

```python
from __future__ import annotations
import uuid
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_permission
from app.models.user import User
from app.services.announcement_service import (
    get_all_announcements,
    get_announcement_by_id,
    create_announcement,
    toggle_announcement,
    delete_announcement,
)

router = APIRouter(prefix="/admin/announcements", tags=["admin-announcements"])
templates = Jinja2Templates(directory="app/templates")

AUDIENCE_LABELS = {
    "all": ("🌐 Всі користувачі", "all"),
    "trainees": ("👥 Всі стажери", "trainees"),
    "admins": ("🔑 Всі адміни", "admins"),
}


@router.get("", response_class=HTMLResponse)
async def announcements_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_announcements")),
):
    announcements = await get_all_announcements(db)
    return templates.TemplateResponse("admin/announcements.html", {
        "request": request,
        "announcements": announcements,
        "audience_labels": AUDIENCE_LABELS,
        "user": admin,
    })


@router.post("/new")
async def create_new(
    request: Request,
    title: str = Form(...),
    body: str = Form(...),
    audience: str = Form(...),
    cta_text: str = Form(""),
    cta_url: str = Form(""),
    expires_at: str = Form(""),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_announcements")),
):
    # Парсинг дати закінчення
    parsed_expires = None
    if expires_at.strip():
        try:
            from datetime import timezone
            parsed_expires = datetime.fromisoformat(expires_at).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            pass

    await create_announcement(
        db=db,
        title=title,
        body=body,
        audience=audience,
        created_by=admin.id,
        cta_text=cta_text or None,
        cta_url=cta_url or None,
        expires_at=parsed_expires,
    )
    await db.commit()

    request.session["flash"] = {
        "type": "success",
        "message": "Оповіщення створено і буде показане користувачам при вході!",
    }
    return RedirectResponse("/admin/announcements", status_code=303)


@router.post("/{announcement_id}/toggle")
async def toggle(
    announcement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_announcements")),
):
    announcement = await get_announcement_by_id(db, announcement_id)
    if announcement:
        await toggle_announcement(db, announcement)
        await db.commit()
    return RedirectResponse("/admin/announcements", status_code=303)


@router.post("/{announcement_id}/delete")
async def delete(
    request: Request,
    announcement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_announcements")),
):
    announcement = await get_announcement_by_id(db, announcement_id)
    if announcement:
        await delete_announcement(db, announcement)
        await db.commit()

    request.session["flash"] = {
        "type": "success",
        "message": "Оповіщення видалено",
    }
    return RedirectResponse("/admin/announcements", status_code=303)
```

---

## Завдання 7 — Додати manage_announcements до permissions

В `app/routers/admin_permissions.py` оновити `ALL_PERMISSIONS`:

```python
ALL_PERMISSIONS = [
    ("manage_quizzes", "Управління квізами", "📝"),
    ("manage_knowledge", "База знань", "📚"),
    ("view_results", "Результати стажерів", "📊"),
    ("manage_users", "Управління стажерами", "👥"),
    ("manage_announcements", "Оповіщення", "📣"),  # ← нове
    ("manage_admins", "Призначення прав адмінам", "🔑"),
]
```

В `app/models/user.py` оновити `PERMISSION_TYPES` enum:

```python
PERMISSION_TYPES = Enum(
    "manage_quizzes",
    "manage_knowledge",
    "view_results",
    "manage_users",
    "manage_announcements",  # ← нове
    "manage_admins",
    name="permission_type",
)
```

Після цього зроби нову міграцію:

```bash
alembic revision --autogenerate -m "add_manage_announcements_permission"
alembic upgrade head
```

---

## Завдання 8 — app/templates/partials/announcement_modal.html

```html
<!-- HTMX модаль оповіщення -->
<!-- Цей фрагмент вставляється в #announcement-container на dashboard -->

<div id="announcement-overlay"
     class="fixed inset-0 z-50 flex items-center justify-center p-4"
     style="background: rgba(26, 35, 50, 0.6); backdrop-filter: blur(4px);">

  <div id="announcement-modal"
       class="w-full max-w-lg rounded-2xl overflow-hidden"
       style="background: var(--color-surface);
              box-shadow: var(--shadow-lg);
              animation: modalIn 0.25s ease;">

    <!-- Header -->
    <div class="px-7 pt-7 pb-4">
      <!-- Бейдж -->
      <div class="flex items-center gap-2 mb-4">
        <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold"
              style="background: #FFF7ED; color: var(--color-accent);">
          📣 Оновлення від OSD
        </span>
        {% if remaining > 0 %}
        <span class="text-xs" style="color: var(--color-text-muted);">
          +{{ remaining }} ще
        </span>
        {% endif %}
      </div>

      <!-- Заголовок -->
      <h2 style="font-family: var(--font-display); font-size: 1.35rem;
                 font-weight: 800; color: var(--color-text); line-height: 1.25;">
        {{ announcement.title }}
      </h2>
    </div>

    <!-- Body -->
    <div class="px-7 pb-6">
      <p class="text-sm leading-relaxed" style="color: var(--color-text-muted);">
        {{ announcement.body }}
      </p>
    </div>

    <!-- Footer з кнопками -->
    <div class="px-7 pb-7 flex items-center gap-3">

      {% if announcement.cta_text and announcement.cta_url %}
      <!-- CTA кнопка + кнопка закрити -->
      <a href="{{ announcement.cta_url }}"
         hx-post="/announcements/{{ announcement.id }}/read"
         hx-target="#announcement-container"
         hx-swap="innerHTML"
         class="flex-1 text-center py-3 px-5 rounded-xl text-white text-sm font-semibold transition-all"
         style="background: var(--color-accent);"
         onmouseover="this.style.background='var(--color-accent-dark)'"
         onmouseout="this.style.background='var(--color-accent)'">
        {{ announcement.cta_text }}
      </a>

      <button
        hx-post="/announcements/{{ announcement.id }}/read"
        hx-target="#announcement-container"
        hx-swap="innerHTML"
        class="py-3 px-5 rounded-xl text-sm font-medium transition-all"
        style="background: var(--color-bg);
               color: var(--color-text-muted);
               border: 1px solid var(--color-border);">
        Закрити
      </button>

      {% else %}
      <!-- Тільки кнопка прочитав -->
      <button
        hx-post="/announcements/{{ announcement.id }}/read"
        hx-target="#announcement-container"
        hx-swap="innerHTML"
        class="flex-1 py-3 px-5 rounded-xl text-white text-sm font-semibold"
        style="background: var(--color-primary);">
        Зрозумів ✓
      </button>
      {% endif %}

    </div>

  </div>
</div>

<style>
@keyframes modalIn {
  from { opacity: 0; transform: scale(0.95) translateY(8px); }
  to   { opacity: 1; transform: scale(1) translateY(0); }
}
</style>
```

---

## Завдання 9 — Оновити trainee/dashboard.html

Додай контейнер для модалі і HTMX тригер в кінці `{% block content %}`:

```html
{% block content %}
  {# ... існуючий контент дашборду ... #}

  <!-- Контейнер для модальних оповіщень -->
  <!-- hx-trigger="load" — HTMX автоматично перевіряє при завантаженні сторінки -->
  <div id="announcement-container"
       hx-get="/announcements/check"
       hx-trigger="load"
       hx-swap="innerHTML">
  </div>

{% endblock %}
```

---

## Завдання 10 — app/templates/admin/announcements.html

```html
{% extends "base.html" %}
{% block title %}Оповіщення{% endblock %}

{% block content %}
<div class="flex items-center gap-3 mb-8">
  <a href="/admin" class="text-sm hover:underline"
     style="color: var(--color-text-muted);">← Адмін панель</a>
  <h1 class="text-2xl font-bold" style="font-family: var(--font-display);">
    📣 Оповіщення
  </h1>
</div>

<div class="grid grid-cols-3 gap-6">

  <!-- Список оповіщень -->
  <div class="col-span-2 space-y-4">

    {% if announcements %}
    {% for ann in announcements %}
    <div class="rounded-2xl overflow-hidden"
         style="background: var(--color-surface);
                border: 1px solid {% if ann.is_active %}var(--color-border){% else %}#F1F5F9{% endif %};
                box-shadow: var(--shadow-sm);
                opacity: {% if ann.is_active %}1{% else %}0.6{% endif %};">

      <!-- Header -->
      <div class="flex items-start justify-between px-6 py-4"
           style="border-bottom: 1px solid var(--color-border);">
        <div class="flex-1">
          <div class="flex items-center gap-2 mb-1">
            <span class="font-bold text-sm"
                  style="font-family: var(--font-display);">
              {{ ann.title }}
            </span>
            <!-- Статус -->
            <span class="px-2 py-0.5 rounded text-xs font-semibold"
                  style="{% if ann.is_active and not ann.is_expired %}
                    background: var(--color-success-bg); color: var(--color-success);
                  {% elif ann.is_expired %}
                    background: #F1F5F9; color: var(--color-text-muted);
                  {% else %}
                    background: #F1F5F9; color: var(--color-text-muted);
                  {% endif %}">
              {% if ann.is_expired %}Закінчилось
              {% elif ann.is_active %}Активне
              {% else %}Вимкнено{% endif %}
            </span>
            <!-- Аудиторія -->
            <span class="px-2 py-0.5 rounded text-xs"
                  style="background: #EEF4FF; color: var(--color-primary);">
              {{ audience_labels[ann.audience][0] }}
            </span>
          </div>
          <p class="text-sm" style="color: var(--color-text-muted);">
            {{ ann.body[:120] }}{% if ann.body | length > 120 %}...{% endif %}
          </p>
          {% if ann.cta_text %}
          <p class="text-xs mt-1" style="color: var(--color-accent);">
            🔗 {{ ann.cta_text }} → {{ ann.cta_url }}
          </p>
          {% endif %}
        </div>

        <!-- Дії -->
        <div class="flex items-center gap-2 ml-4 flex-shrink-0">
          <form action="/admin/announcements/{{ ann.id }}/toggle" method="post">
            <button type="submit"
                    class="text-xs px-3 py-1.5 rounded-lg transition-all"
                    style="border: 1px solid var(--color-border);
                           color: var(--color-text-muted);">
              {% if ann.is_active %}Вимкнути{% else %}Увімкнути{% endif %}
            </button>
          </form>
          <form action="/admin/announcements/{{ ann.id }}/delete" method="post"
                onsubmit="return confirm('Видалити оповіщення?')">
            <button type="submit" class="text-xs px-3 py-1.5 rounded-lg"
                    style="color: var(--color-error); border: 1px solid #FECACA;">
              Видалити
            </button>
          </form>
        </div>
      </div>

      <!-- Статистика прочитань -->
      <div class="px-6 py-3 flex items-center gap-4 text-xs"
           style="color: var(--color-text-muted); background: var(--color-bg);">
        <span>
          👁 Прочитали: <strong>{{ ann.reads | length }}</strong>
        </span>
        <span>
          📅 Створено: {{ ann.created_at.strftime('%d.%m.%Y о %H:%M') }}
        </span>
        {% if ann.expires_at %}
        <span>
          ⏰ Діє до: {{ ann.expires_at.strftime('%d.%m.%Y') }}
        </span>
        {% endif %}
      </div>

    </div>
    {% endfor %}

    {% else %}
    <div class="text-center py-16 rounded-2xl"
         style="background: var(--color-surface);
                border: 1px solid var(--color-border);">
      <p class="text-4xl mb-4">📭</p>
      <p class="font-medium" style="color: var(--color-text-muted);">
        Оповіщень ще немає
      </p>
      <p class="text-sm mt-1" style="color: var(--color-text-muted);">
        Створи перше — воно з'явиться у користувачів при вході
      </p>
    </div>
    {% endif %}

  </div>

  <!-- Sidebar: форма створення -->
  <div>
    <div class="rounded-2xl p-6 sticky top-6"
         style="background: var(--color-surface);
                border: 1px solid var(--color-border);
                box-shadow: var(--shadow-sm);">

      <h2 class="font-bold text-sm mb-5" style="font-family: var(--font-display);">
        Нове оповіщення
      </h2>

      <form action="/admin/announcements/new" method="post" class="space-y-4">

        <div>
          <label class="text-xs font-medium block mb-1"
                 style="color: var(--color-text-muted);">
            Заголовок *
          </label>
          <input type="text" name="title" required
                 placeholder="Нові матеріали для навчання"
                 class="w-full px-3 py-2.5 rounded-xl text-sm outline-none"
                 style="border: 1.5px solid var(--color-border);"
                 onfocus="this.style.borderColor='var(--color-primary)'"
                 onblur="this.style.borderColor='var(--color-border)'">
        </div>

        <div>
          <label class="text-xs font-medium block mb-1"
                 style="color: var(--color-text-muted);">
            Текст *
          </label>
          <textarea name="body" required rows="4"
                    placeholder="Описи що нового або важливого..."
                    class="w-full px-3 py-2.5 rounded-xl text-sm outline-none resize-none"
                    style="border: 1.5px solid var(--color-border);"
                    onfocus="this.style.borderColor='var(--color-primary)'"
                    onblur="this.style.borderColor='var(--color-border)'"></textarea>
        </div>

        <div>
          <label class="text-xs font-medium block mb-1"
                 style="color: var(--color-text-muted);">
            Аудиторія *
          </label>
          <select name="audience" required
                  class="w-full px-3 py-2.5 rounded-xl text-sm outline-none"
                  style="border: 1.5px solid var(--color-border);">
            <option value="all">🌐 Всі користувачі</option>
            <option value="trainees">👥 Тільки стажери</option>
            <option value="admins">🔑 Тільки адміни</option>
          </select>
        </div>

        <!-- CTA блок -->
        <div class="p-4 rounded-xl" style="background: var(--color-bg);">
          <p class="text-xs font-medium mb-3" style="color: var(--color-text-muted);">
            Кнопка з посиланням (необов'язково)
          </p>
          <div class="space-y-2">
            <input type="text" name="cta_text"
                   placeholder="Текст кнопки (напр. Перейти до квізу)"
                   class="w-full px-3 py-2 rounded-lg text-xs outline-none"
                   style="border: 1px solid var(--color-border);">
            <input type="url" name="cta_url"
                   placeholder="https://... або /quiz/uuid"
                   class="w-full px-3 py-2 rounded-lg text-xs outline-none"
                   style="border: 1px solid var(--color-border);">
          </div>
        </div>

        <div>
          <label class="text-xs font-medium block mb-1"
                 style="color: var(--color-text-muted);">
            Діє до (необов'язково)
          </label>
          <input type="datetime-local" name="expires_at"
                 class="w-full px-3 py-2.5 rounded-xl text-sm outline-none"
                 style="border: 1.5px solid var(--color-border);">
          <p class="text-xs mt-1" style="color: var(--color-text-muted);">
            Якщо не вказано — діє безстроково
          </p>
        </div>

        <button type="submit"
                class="w-full py-3 rounded-xl text-white text-sm font-semibold"
                style="background: var(--color-accent);"
                onmouseover="this.style.background='var(--color-accent-dark)'"
                onmouseout="this.style.background='var(--color-accent)'">
          📣 Опублікувати оповіщення
        </button>

      </form>
    </div>
  </div>

</div>
{% endblock %}
```

---

## Завдання 11 — Зареєструвати роутери в app/main.py

```python
from app.routers import (
    auth, trainee, admin, docs,
    admin_docs, admin_permissions,
    announcements, admin_announcements,  # ← нові
)

app.include_router(announcements.router)
app.include_router(admin_announcements.router)
```

---

## Завдання 12 — Додати посилання в адмін дашборд

В `app/templates/admin/dashboard.html` додай до навігації:

```html
{% if user.has_permission('manage_announcements') %}
<a href="/admin/announcements"
   class="px-4 py-2 rounded-lg hover:opacity-80 transition-all"
   style="background: #FFF7ED;
          border: 1px solid #FED7AA;
          color: var(--color-accent);">
  📣 Оповіщення
</a>
{% endif %}
```

---

## Перевірка після виконання

```bash
uvicorn app.main:app --reload
```

Чекліст:
- [ ] Superadmin отримує `manage_announcements` автоматично (або додай вручну через `/admin/permissions`)
- [ ] `/admin/announcements` — список оповіщень + форма створення
- [ ] Створи тестове оповіщення для "Всіх стажерів"
- [ ] Відкрий `/dashboard` як стажист — модаль з'являється автоматично
- [ ] Натисни "Зрозумів" — модаль зникає, в БД з'явився запис в `announcement_reads`
- [ ] Перезавантаж `/dashboard` — модаль більше не показується (вже прочитано)
- [ ] Створи два оповіщення — перевір що після закриття першого автоматично з'являється друге
- [ ] Вимкни оповіщення в адмінці — воно більше не показується стажистам
- [ ] Перевір що оповіщення для "admins" не бачать стажери і навпаки
