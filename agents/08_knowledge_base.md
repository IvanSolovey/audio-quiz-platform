# Агент 8 — Knowledge Base (База знань)

> Прочитай CLAUDE.md перед виконанням.
> Залежить від: Агенти 1-5 завершені (моделі, auth, dependencies вже існують).
> Цей агент додає НОВІ сутності — не змінює існуючі моделі.

---

## Огляд

Додаємо повноцінну базу знань всередині платформи:
- Стажист читає статті згруповані по категоріям
- Адмін створює/редагує статті через Markdown редактор
- Контент зберігається в PostgreSQL (не файли на диску)
- Markdown рендериться в красивий HTML через python-markdown

---

## Завдання 1 — Встанови нові залежності

Додай до `requirements.txt`:
```
markdown==3.6
bleach==6.1.0
```

Встанови:
```bash
pip install markdown==3.6 bleach==6.1.0
```

---

## Завдання 2 — app/models/knowledge.py

```python
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Category(Base):
    __tablename__ = "kb_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str] = mapped_column(String(10), default="📄")
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    articles: Mapped[list[Article]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
        order_by="Article.order_index",
    )

    def __repr__(self) -> str:
        return f"<Category '{self.name}'>"


class Article(Base):
    __tablename__ = "kb_articles"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("kb_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_visible: Mapped[bool] = mapped_column(Boolean, default=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    category: Mapped[Category] = relationship(back_populates="articles")
    author: Mapped[User | None] = relationship()

    def __repr__(self) -> str:
        return f"<Article '{self.title}'>"
```

---

## Завдання 3 — Оновити app/models/__init__.py

Додай імпорти нових моделей:

```python
from app.models.user import User
from app.models.quiz import Quiz, Question, AnswerOption
from app.models.result import QuizAttempt, AttemptAnswer
from app.models.knowledge import Category, Article

__all__ = [
    "User",
    "Quiz", "Question", "AnswerOption",
    "QuizAttempt", "AttemptAnswer",
    "Category", "Article",
]
```

---

## Завдання 4 — Alembic міграція

```bash
alembic revision --autogenerate -m "add_knowledge_base"
alembic upgrade head
```

Перевір що створились таблиці `kb_categories` і `kb_articles`.

---

## Завдання 5 — app/services/knowledge_service.py

```python
from __future__ import annotations
import uuid
import re
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
import markdown
import bleach

from app.models.knowledge import Category, Article


# ─── Slug утиліта ─────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Перетворює текст на URL-безпечний slug."""
    # Транслітерація основних українських символів
    translit = {
        'а':'a','б':'b','в':'v','г':'h','ґ':'g','д':'d','е':'e','є':'ye',
        'ж':'zh','з':'z','и':'y','і':'i','ї':'yi','й':'y','к':'k','л':'l',
        'м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u',
        'ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ь':'',
        'ю':'yu','я':'ya',
    }
    text = text.lower().strip()
    result = []
    for char in text:
        if char in translit:
            result.append(translit[char])
        elif char.isalnum():
            result.append(char)
        elif char in (' ', '-', '_'):
            result.append('-')
    slug = re.sub(r'-+', '-', ''.join(result)).strip('-')
    return slug or 'article'


def render_markdown(content: str) -> str:
    """
    Конвертує Markdown у безпечний HTML.
    Дозволені теги: заголовки, параграфи, списки, таблиці, код, посилання.
    """
    allowed_tags = [
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'p', 'br', 'hr',
        'ul', 'ol', 'li',
        'strong', 'em', 'del', 'code', 'pre',
        'blockquote',
        'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'a', 'img',
        'div', 'span',
    ]
    allowed_attrs = {
        'a': ['href', 'title', 'target'],
        'img': ['src', 'alt', 'title', 'width', 'height'],
        'th': ['align'],
        'td': ['align'],
        '*': ['class'],
    }

    html = markdown.markdown(
        content,
        extensions=[
            'tables',
            'fenced_code',
            'codehilite',
            'toc',
            'nl2br',
            'attr_list',
        ],
        output_format='html',
    )

    clean_html = bleach.clean(
        html,
        tags=allowed_tags,
        attributes=allowed_attrs,
        strip=True,
    )
    return clean_html


# ─── Category CRUD ────────────────────────────────────────────────────────────

async def get_all_categories(
    db: AsyncSession,
    visible_only: bool = False,
) -> list[Category]:
    query = select(Category).options(
        selectinload(Category.articles)
    ).order_by(Category.order_index, Category.name)

    if visible_only:
        query = query.where(Category.is_visible == True)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_category_by_slug(
    db: AsyncSession, slug: str
) -> Category | None:
    result = await db.execute(
        select(Category)
        .where(Category.slug == slug)
        .options(
            selectinload(Category.articles)
        )
    )
    return result.scalar_one_or_none()


async def create_category(
    db: AsyncSession,
    name: str,
    description: str | None,
    icon: str,
    order_index: int,
) -> Category:
    slug = slugify(name)

    # Унікальність slug
    existing = await db.execute(
        select(Category).where(Category.slug == slug)
    )
    if existing.scalar_one_or_none():
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    category = Category(
        name=name,
        slug=slug,
        description=description or None,
        icon=icon or "📄",
        order_index=order_index,
    )
    db.add(category)
    await db.flush()
    await db.refresh(category)
    return category


async def update_category(
    db: AsyncSession,
    category: Category,
    name: str,
    description: str | None,
    icon: str,
    order_index: int,
    is_visible: bool,
) -> Category:
    category.name = name
    category.description = description or None
    category.icon = icon or "📄"
    category.order_index = order_index
    category.is_visible = is_visible
    await db.flush()
    return category


async def delete_category(db: AsyncSession, category: Category) -> None:
    await db.delete(category)
    await db.flush()


# ─── Article CRUD ─────────────────────────────────────────────────────────────

async def get_article_by_slug(
    db: AsyncSession, slug: str
) -> Article | None:
    result = await db.execute(
        select(Article)
        .where(Article.slug == slug)
        .options(selectinload(Article.category))
    )
    return result.scalar_one_or_none()


async def get_article_by_id(
    db: AsyncSession, article_id: uuid.UUID
) -> Article | None:
    result = await db.execute(
        select(Article)
        .where(Article.id == article_id)
        .options(selectinload(Article.category))
    )
    return result.scalar_one_or_none()


async def create_article(
    db: AsyncSession,
    category_id: uuid.UUID,
    title: str,
    content: str,
    order_index: int,
    created_by: uuid.UUID,
    is_visible: bool = False,
) -> Article:
    slug = slugify(title)

    # Унікальність slug
    existing = await db.execute(
        select(Article).where(Article.slug == slug)
    )
    if existing.scalar_one_or_none():
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    article = Article(
        category_id=category_id,
        title=title.strip(),
        slug=slug,
        content=content,
        order_index=order_index,
        created_by=created_by,
        is_visible=is_visible,
    )
    db.add(article)
    await db.flush()
    await db.refresh(article)
    return article


async def update_article(
    db: AsyncSession,
    article: Article,
    title: str,
    content: str,
    category_id: uuid.UUID,
    order_index: int,
    is_visible: bool,
) -> Article:
    article.title = title.strip()
    article.content = content
    article.category_id = category_id
    article.order_index = order_index
    article.is_visible = is_visible
    await db.flush()
    return article


async def delete_article(db: AsyncSession, article: Article) -> None:
    await db.delete(article)
    await db.flush()


async def search_articles(
    db: AsyncSession,
    query: str,
    visible_only: bool = True,
) -> list[Article]:
    from sqlalchemy import or_, func as sqlfunc
    search = f"%{query.lower()}%"

    stmt = (
        select(Article)
        .options(selectinload(Article.category))
        .where(
            or_(
                sqlfunc.lower(Article.title).like(search),
                sqlfunc.lower(Article.content).like(search),
            )
        )
        .order_by(Article.title)
        .limit(20)
    )

    if visible_only:
        stmt = stmt.where(Article.is_visible == True)

    result = await db.execute(stmt)
    return list(result.scalars().all())
```

---

## Завдання 6 — app/routers/docs.py (стажист)

```python
from __future__ import annotations
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_user
from app.models.user import User
from app.services.knowledge_service import (
    get_all_categories,
    get_category_by_slug,
    get_article_by_slug,
    render_markdown,
    search_articles,
)

router = APIRouter(prefix="/docs", tags=["docs"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def docs_index(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Головна сторінка бази знань — список категорій."""
    categories = await get_all_categories(db, visible_only=True)

    # Фільтруємо тільки видимі статті для стажиста
    for cat in categories:
        cat.articles = [a for a in cat.articles if a.is_visible]

    return templates.TemplateResponse("docs/index.html", {
        "request": request,
        "categories": categories,
        "user": current_user,
    })


@router.get("/search", response_class=HTMLResponse)
async def docs_search(
    request: Request,
    q: str = Query(default="", min_length=2),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Пошук по статтям."""
    articles = []
    if q:
        articles = await search_articles(db, q, visible_only=True)

    return templates.TemplateResponse("docs/search.html", {
        "request": request,
        "articles": articles,
        "query": q,
        "user": current_user,
    })


@router.get("/{category_slug}", response_class=HTMLResponse)
async def docs_category(
    request: Request,
    category_slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Список статей у категорії."""
    category = await get_category_by_slug(db, category_slug)

    if not category or not category.is_visible:
        return templates.TemplateResponse("docs/404.html", {
            "request": request,
            "user": current_user,
        }, status_code=404)

    # Тільки видимі статті
    visible_articles = [a for a in category.articles if a.is_visible]

    return templates.TemplateResponse("docs/category.html", {
        "request": request,
        "category": category,
        "articles": visible_articles,
        "user": current_user,
    })


@router.get("/{category_slug}/{article_slug}", response_class=HTMLResponse)
async def docs_article(
    request: Request,
    category_slug: str,
    article_slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Сторінка статті з рендером Markdown."""
    article = await get_article_by_slug(db, article_slug)

    if not article or not article.is_visible:
        return templates.TemplateResponse("docs/404.html", {
            "request": request,
            "user": current_user,
        }, status_code=404)

    # Рендер Markdown → HTML
    content_html = render_markdown(article.content)

    return templates.TemplateResponse("docs/article.html", {
        "request": request,
        "article": article,
        "category": article.category,
        "content_html": content_html,
        "user": current_user,
    })
```

---

## Завдання 7 — app/routers/admin_docs.py (адмін)

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
from app.dependencies import require_admin
from app.models.user import User
from app.models.knowledge import Category, Article
from app.services.knowledge_service import (
    get_all_categories,
    get_category_by_slug,
    get_article_by_id,
    create_category,
    update_category,
    delete_category,
    create_article,
    update_article,
    delete_article,
    render_markdown,
)

router = APIRouter(prefix="/admin/docs", tags=["admin-docs"])
templates = Jinja2Templates(directory="app/templates")


# ─── Categories ───────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def admin_docs_index(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    categories = await get_all_categories(db, visible_only=False)
    return templates.TemplateResponse("admin/docs/index.html", {
        "request": request,
        "categories": categories,
        "user": admin,
    })


@router.post("/category/new")
async def admin_create_category(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    icon: str = Form("📄"),
    order_index: int = Form(0),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    await create_category(
        db=db,
        name=name,
        description=description,
        icon=icon,
        order_index=order_index,
    )
    await db.commit()
    request.session["flash"] = {
        "type": "success",
        "message": f"Категорію '{name}' створено!",
    }
    return RedirectResponse("/admin/docs", status_code=303)


@router.post("/category/{category_id}/update")
async def admin_update_category(
    request: Request,
    category_id: uuid.UUID,
    name: str = Form(...),
    description: str = Form(""),
    icon: str = Form("📄"),
    order_index: int = Form(0),
    is_visible: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(
        select(Category).where(Category.id == category_id)
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404)

    await update_category(
        db=db,
        category=category,
        name=name,
        description=description,
        icon=icon,
        order_index=order_index,
        is_visible=is_visible,
    )
    await db.commit()
    request.session["flash"] = {"type": "success", "message": "Збережено!"}
    return RedirectResponse("/admin/docs", status_code=303)


@router.post("/category/{category_id}/delete")
async def admin_delete_category(
    request: Request,
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(
        select(Category)
        .where(Category.id == category_id)
        .options(selectinload(Category.articles))
    )
    category = result.scalar_one_or_none()
    if category:
        await delete_category(db, category)
        await db.commit()
    return RedirectResponse("/admin/docs", status_code=303)


# ─── Articles ─────────────────────────────────────────────────────────────────

@router.get("/article/new", response_class=HTMLResponse)
async def admin_new_article_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    categories = await get_all_categories(db, visible_only=False)
    return templates.TemplateResponse("admin/docs/article_edit.html", {
        "request": request,
        "article": None,
        "categories": categories,
        "user": admin,
    })


@router.post("/article/new")
async def admin_create_article(
    request: Request,
    category_id: str = Form(...),
    title: str = Form(...),
    content: str = Form(...),
    order_index: int = Form(0),
    is_visible: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    article = await create_article(
        db=db,
        category_id=uuid.UUID(category_id),
        title=title,
        content=content,
        order_index=order_index,
        created_by=admin.id,
        is_visible=is_visible,
    )
    await db.commit()
    request.session["flash"] = {
        "type": "success",
        "message": f"Статтю '{title}' створено!",
    }
    return RedirectResponse(f"/admin/docs/article/{article.id}/edit", status_code=303)


@router.get("/article/{article_id}/edit", response_class=HTMLResponse)
async def admin_edit_article_page(
    request: Request,
    article_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    article = await get_article_by_id(db, article_id)
    if not article:
        raise HTTPException(status_code=404)

    categories = await get_all_categories(db, visible_only=False)
    preview_html = render_markdown(article.content) if article.content else ""

    return templates.TemplateResponse("admin/docs/article_edit.html", {
        "request": request,
        "article": article,
        "categories": categories,
        "preview_html": preview_html,
        "user": admin,
    })


@router.post("/article/{article_id}/update")
async def admin_update_article(
    request: Request,
    article_id: uuid.UUID,
    category_id: str = Form(...),
    title: str = Form(...),
    content: str = Form(...),
    order_index: int = Form(0),
    is_visible: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    article = await get_article_by_id(db, article_id)
    if not article:
        raise HTTPException(status_code=404)

    await update_article(
        db=db,
        article=article,
        title=title,
        content=content,
        category_id=uuid.UUID(category_id),
        order_index=order_index,
        is_visible=is_visible,
    )
    await db.commit()
    request.session["flash"] = {"type": "success", "message": "Збережено!"}
    return RedirectResponse(
        f"/admin/docs/article/{article_id}/edit", status_code=303
    )


@router.post("/article/{article_id}/delete")
async def admin_delete_article(
    article_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    article = await get_article_by_id(db, article_id)
    if article:
        await delete_article(db, article)
        await db.commit()
    return RedirectResponse("/admin/docs", status_code=303)


# ─── HTMX Preview ─────────────────────────────────────────────────────────────

@router.post("/preview", response_class=HTMLResponse)
async def admin_preview_markdown(
    content: str = Form(...),
    admin: User = Depends(require_admin),
):
    """HTMX ендпоінт — повертає HTML рендер Markdown для live preview."""
    html = render_markdown(content)
    return HTMLResponse(content=html)
```

---

## Завдання 8 — Шаблони стажиста

### app/templates/docs/index.html

```html
{% extends "base.html" %}
{% block title %}База знань{% endblock %}

{% block extra_head %}
<style>
  .category-card:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
    border-color: #A0B8D0;
  }
  .category-card { transition: all 0.2s ease; }
</style>
{% endblock %}

{% block content %}
<div class="max-w-4xl mx-auto">

  <!-- Header -->
  <div class="mb-8">
    <h1 style="font-family: var(--font-display); font-size: 2rem; font-weight: 800; color: var(--color-text);">
      📚 База знань
    </h1>
    <p class="mt-2" style="color: var(--color-text-muted);">
      Документація, посадові інструкції та навчальні матеріали OSD
    </p>
  </div>

  <!-- Search -->
  <form action="/docs/search" method="get" class="mb-8">
    <div class="flex gap-3">
      <input
        type="search"
        name="q"
        placeholder="Пошук по статтям..."
        class="flex-1 px-4 py-3 rounded-xl text-sm outline-none transition-all"
        style="border: 1.5px solid var(--color-border); background: var(--color-surface);
               font-family: var(--font-body);"
        onfocus="this.style.borderColor='var(--color-primary)'"
        onblur="this.style.borderColor='var(--color-border)'">
      <button type="submit"
              class="px-5 py-3 rounded-xl text-white text-sm font-semibold"
              style="background: var(--color-primary);">
        Знайти
      </button>
    </div>
  </form>

  <!-- Categories grid -->
  {% if categories %}
  <div class="grid gap-4 sm:grid-cols-2">
    {% for category in categories %}
    {% if category.articles %}
    <a href="/docs/{{ category.slug }}"
       class="category-card block p-6 rounded-2xl"
       style="background: var(--color-surface);
              border: 1px solid var(--color-border);
              box-shadow: var(--shadow-sm);
              text-decoration: none;">
      <div class="flex items-start gap-4">
        <div class="text-3xl">{{ category.icon }}</div>
        <div class="flex-1">
          <h2 class="font-bold text-base mb-1"
              style="font-family: var(--font-display); color: var(--color-text);">
            {{ category.name }}
          </h2>
          {% if category.description %}
          <p class="text-sm mb-3" style="color: var(--color-text-muted);">
            {{ category.description }}
          </p>
          {% endif %}
          <span class="text-xs font-medium px-2.5 py-1 rounded-lg"
                style="background: #EEF4FF; color: var(--color-primary);">
            {{ category.articles | length }} статей
          </span>
        </div>
      </div>
    </a>
    {% endif %}
    {% endfor %}
  </div>
  {% else %}
  <div class="text-center py-16" style="color: var(--color-text-muted);">
    <p class="text-4xl mb-4">📭</p>
    <p>База знань поки порожня. Адміністратор скоро додасть матеріали.</p>
  </div>
  {% endif %}

</div>
{% endblock %}
```

---

### app/templates/docs/category.html

```html
{% extends "base.html" %}
{% block title %}{{ category.name }}{% endblock %}

{% block content %}
<div class="max-w-3xl mx-auto">

  <!-- Breadcrumb -->
  <nav class="flex items-center gap-2 text-sm mb-6" style="color: var(--color-text-muted);">
    <a href="/docs" class="hover:underline" style="color: var(--color-primary);">База знань</a>
    <span>›</span>
    <span>{{ category.name }}</span>
  </nav>

  <div class="flex items-center gap-3 mb-8">
    <span class="text-4xl">{{ category.icon }}</span>
    <div>
      <h1 style="font-family: var(--font-display); font-size: 1.75rem;
                 font-weight: 800; color: var(--color-text);">
        {{ category.name }}
      </h1>
      {% if category.description %}
      <p class="mt-1 text-sm" style="color: var(--color-text-muted);">
        {{ category.description }}
      </p>
      {% endif %}
    </div>
  </div>

  <!-- Articles list -->
  {% if articles %}
  <div class="space-y-2">
    {% for article in articles %}
    <a href="/docs/{{ category.slug }}/{{ article.slug }}"
       class="flex items-center gap-4 px-5 py-4 rounded-xl transition-all group"
       style="background: var(--color-surface);
              border: 1px solid var(--color-border);
              text-decoration: none;"
       onmouseover="this.style.borderColor='#A0B8D0'; this.style.boxShadow='var(--shadow-sm)';"
       onmouseout="this.style.borderColor='var(--color-border)'; this.style.boxShadow='none';">
      <span class="text-xl">📄</span>
      <span class="flex-1 font-medium text-sm"
            style="color: var(--color-text); font-family: var(--font-display);">
        {{ article.title }}
      </span>
      <span class="text-xs" style="color: var(--color-text-muted);">
        {{ article.updated_at.strftime('%d.%m.%Y') }}
      </span>
      <span style="color: var(--color-accent);">→</span>
    </a>
    {% endfor %}
  </div>
  {% else %}
  <div class="text-center py-12" style="color: var(--color-text-muted);">
    <p>У цій категорії поки немає статей.</p>
    <a href="/docs" class="text-sm mt-2 block hover:underline"
       style="color: var(--color-primary);">← Повернутись до бази знань</a>
  </div>
  {% endif %}

</div>
{% endblock %}
```

---

### app/templates/docs/article.html

```html
{% extends "base.html" %}
{% block title %}{{ article.title }}{% endblock %}

{% block extra_head %}
<style>
  /* Markdown стилі */
  .markdown-body h1 { font-size: 1.75rem; font-weight: 800; margin: 1.5rem 0 1rem;
                       font-family: var(--font-display); color: var(--color-text); }
  .markdown-body h2 { font-size: 1.35rem; font-weight: 700; margin: 1.5rem 0 0.75rem;
                       font-family: var(--font-display); color: var(--color-text);
                       padding-bottom: 0.5rem; border-bottom: 2px solid var(--color-border); }
  .markdown-body h3 { font-size: 1.1rem; font-weight: 700; margin: 1.25rem 0 0.5rem;
                       font-family: var(--font-display); color: var(--color-text); }
  .markdown-body p  { margin: 0.75rem 0; line-height: 1.7;
                       color: var(--color-text); font-size: 0.95rem; }
  .markdown-body ul, .markdown-body ol { margin: 0.75rem 0 0.75rem 1.5rem; }
  .markdown-body li { margin: 0.35rem 0; line-height: 1.6;
                       color: var(--color-text); font-size: 0.95rem; }
  .markdown-body strong { font-weight: 700; color: var(--color-text); }
  .markdown-body em { font-style: italic; }
  .markdown-body code {
    background: #F1F5F9; color: #1A3A5C;
    padding: 0.15rem 0.4rem; border-radius: 4px;
    font-size: 0.875rem; font-family: 'Courier New', monospace;
  }
  .markdown-body pre {
    background: #1A2332; color: #E2E8F0;
    padding: 1.25rem; border-radius: 12px;
    overflow-x: auto; margin: 1rem 0;
  }
  .markdown-body pre code { background: transparent; color: inherit; padding: 0; }
  .markdown-body blockquote {
    border-left: 4px solid var(--color-accent);
    padding: 0.75rem 1rem; margin: 1rem 0;
    background: #FFFBEB; border-radius: 0 8px 8px 0;
    color: var(--color-text-muted);
  }
  .markdown-body table {
    width: 100%; border-collapse: collapse; margin: 1rem 0;
    font-size: 0.9rem;
  }
  .markdown-body th {
    background: var(--color-bg); font-weight: 600;
    padding: 0.6rem 1rem; text-align: left;
    border-bottom: 2px solid var(--color-border);
    font-family: var(--font-display);
  }
  .markdown-body td {
    padding: 0.6rem 1rem;
    border-bottom: 1px solid var(--color-border);
    vertical-align: top;
  }
  .markdown-body tr:last-child td { border-bottom: none; }
  .markdown-body tr:hover td { background: var(--color-bg); }
  .markdown-body a { color: var(--color-primary); text-decoration: underline; }
  .markdown-body hr { border: none; border-top: 2px solid var(--color-border);
                       margin: 1.5rem 0; }
</style>
{% endblock %}

{% block content %}
<div class="max-w-3xl mx-auto">

  <!-- Breadcrumb -->
  <nav class="flex items-center gap-2 text-sm mb-6" style="color: var(--color-text-muted);">
    <a href="/docs" class="hover:underline" style="color: var(--color-primary);">База знань</a>
    <span>›</span>
    <a href="/docs/{{ category.slug }}" class="hover:underline"
       style="color: var(--color-primary);">{{ category.name }}</a>
    <span>›</span>
    <span>{{ article.title }}</span>
  </nav>

  <!-- Article header -->
  <div class="mb-8">
    <h1 style="font-family: var(--font-display); font-size: 2rem;
               font-weight: 800; color: var(--color-text); line-height: 1.2;">
      {{ article.title }}
    </h1>
    <p class="text-xs mt-3" style="color: var(--color-text-muted);">
      Оновлено {{ article.updated_at.strftime('%d.%m.%Y о %H:%M') }}
    </p>
  </div>

  <!-- Article content -->
  <div class="markdown-body p-8 rounded-2xl"
       style="background: var(--color-surface);
              border: 1px solid var(--color-border);
              box-shadow: var(--shadow-sm);">
    {{ content_html | safe }}
  </div>

  <!-- Navigation -->
  <div class="mt-8 pt-6 flex items-center justify-between"
       style="border-top: 1px solid var(--color-border);">
    <a href="/docs/{{ category.slug }}"
       class="text-sm hover:underline flex items-center gap-2"
       style="color: var(--color-primary);">
      ← {{ category.name }}
    </a>
    <a href="/docs"
       class="text-sm hover:underline"
       style="color: var(--color-text-muted);">
      База знань
    </a>
  </div>

</div>
{% endblock %}
```

---

### app/templates/docs/search.html

```html
{% extends "base.html" %}
{% block title %}Пошук{% endblock %}

{% block content %}
<div class="max-w-3xl mx-auto">

  <h1 class="text-2xl font-bold mb-6"
      style="font-family: var(--font-display);">
    Пошук по базі знань
  </h1>

  <form action="/docs/search" method="get" class="mb-8">
    <div class="flex gap-3">
      <input type="search" name="q" value="{{ query }}"
             placeholder="Введи запит..."
             autofocus
             class="flex-1 px-4 py-3 rounded-xl text-sm outline-none"
             style="border: 1.5px solid var(--color-primary); background: var(--color-surface);">
      <button type="submit"
              class="px-5 py-3 rounded-xl text-white text-sm font-semibold"
              style="background: var(--color-primary);">
        Знайти
      </button>
    </div>
  </form>

  {% if query %}
    {% if articles %}
    <p class="text-sm mb-4" style="color: var(--color-text-muted);">
      Знайдено {{ articles | length }} результатів для «{{ query }}»
    </p>
    <div class="space-y-2">
      {% for article in articles %}
      <a href="/docs/{{ article.category.slug }}/{{ article.slug }}"
         class="flex items-start gap-4 px-5 py-4 rounded-xl transition-all"
         style="background: var(--color-surface); border: 1px solid var(--color-border);
                text-decoration: none;"
         onmouseover="this.style.borderColor='#A0B8D0';"
         onmouseout="this.style.borderColor='var(--color-border)';">
        <span class="text-xl mt-0.5">{{ article.category.icon }}</span>
        <div>
          <p class="font-semibold text-sm" style="color: var(--color-text);
             font-family: var(--font-display);">{{ article.title }}</p>
          <p class="text-xs mt-0.5" style="color: var(--color-text-muted);">
            {{ article.category.name }}
          </p>
        </div>
      </a>
      {% endfor %}
    </div>
    {% else %}
    <div class="text-center py-12" style="color: var(--color-text-muted);">
      <p class="text-3xl mb-3">🔍</p>
      <p>Нічого не знайдено для «{{ query }}»</p>
      <a href="/docs" class="text-sm mt-2 block hover:underline"
         style="color: var(--color-primary);">← До бази знань</a>
    </div>
    {% endif %}
  {% endif %}

</div>
{% endblock %}
```

---

### app/templates/docs/404.html

```html
{% extends "base.html" %}
{% block title %}Не знайдено{% endblock %}
{% block content %}
<div class="text-center py-20" style="color: var(--color-text-muted);">
  <p class="text-5xl mb-4">📭</p>
  <h1 class="text-xl font-bold mb-2" style="font-family: var(--font-display);">
    Статтю не знайдено
  </h1>
  <p class="text-sm mb-6">Можливо її видалили або вона ще не опублікована.</p>
  <a href="/docs" class="text-sm hover:underline" style="color: var(--color-primary);">
    ← Повернутись до бази знань
  </a>
</div>
{% endblock %}
```

---

## Завдання 9 — Шаблони адмін панелі

### app/templates/admin/docs/index.html

```html
{% extends "base.html" %}
{% block title %}База знань — Адмін{% endblock %}

{% block content %}
<div class="flex items-center justify-between mb-8">
  <div class="flex items-center gap-3">
    <a href="/admin" class="text-sm hover:underline"
       style="color: var(--color-text-muted);">← Адмін панель</a>
    <h1 class="text-2xl font-bold" style="font-family: var(--font-display);">
      База знань
    </h1>
  </div>
  <a href="/admin/docs/article/new"
     class="px-4 py-2 rounded-xl text-white text-sm font-semibold"
     style="background: var(--color-accent);">
    + Нова стаття
  </a>
</div>

<div class="grid grid-cols-3 gap-6">

  <!-- Категорії -->
  <div class="col-span-2">
    {% for category in categories %}
    <div class="mb-6 rounded-2xl overflow-hidden"
         style="background: var(--color-surface);
                border: 1px solid var(--color-border);
                box-shadow: var(--shadow-sm);">

      <!-- Category header -->
      <div class="flex items-center justify-between px-6 py-4"
           style="background: var(--color-bg); border-bottom: 1px solid var(--color-border);">
        <div class="flex items-center gap-3">
          <span class="text-xl">{{ category.icon }}</span>
          <div>
            <span class="font-bold text-sm"
                  style="font-family: var(--font-display);">{{ category.name }}</span>
            <span class="ml-2 text-xs px-2 py-0.5 rounded"
                  style="{% if category.is_visible %}background:#F0FDF4; color:#16A34A;
                         {% else %}background:#F1F5F9; color:var(--color-text-muted);{% endif %}">
              {% if category.is_visible %}Видима{% else %}Прихована{% endif %}
            </span>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <button onclick="toggleCategoryForm('form-{{ category.id }}')"
                  class="text-xs px-3 py-1.5 rounded-lg"
                  style="border: 1px solid var(--color-border); color: var(--color-text-muted);">
            Редагувати
          </button>
          <form action="/admin/docs/category/{{ category.id }}/delete" method="post"
                onsubmit="return confirm('Видалити категорію і всі статті в ній?')">
            <button type="submit" class="text-xs px-3 py-1.5 rounded-lg"
                    style="color: var(--color-error); border: 1px solid #FECACA;">
              Видалити
            </button>
          </form>
        </div>
      </div>

      <!-- Edit form (hidden by default) -->
      <div id="form-{{ category.id }}" class="hidden px-6 py-4"
           style="border-bottom: 1px solid var(--color-border); background: #FAFBFC;">
        <form action="/admin/docs/category/{{ category.id }}/update" method="post"
              class="grid grid-cols-2 gap-3">
          <input type="text" name="name" value="{{ category.name }}" required
                 class="px-3 py-2 rounded-lg text-sm outline-none"
                 style="border: 1px solid var(--color-border);">
          <input type="text" name="icon" value="{{ category.icon }}"
                 placeholder="Емодзі 📄"
                 class="px-3 py-2 rounded-lg text-sm outline-none"
                 style="border: 1px solid var(--color-border);">
          <textarea name="description" rows="2"
                    placeholder="Опис категорії"
                    class="col-span-2 px-3 py-2 rounded-lg text-sm outline-none resize-none"
                    style="border: 1px solid var(--color-border);">{{ category.description or '' }}</textarea>
          <div class="flex items-center gap-4 col-span-2">
            <label class="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" name="is_visible" value="true"
                     {% if category.is_visible %}checked{% endif %}>
              Видима стажистам
            </label>
            <input type="number" name="order_index" value="{{ category.order_index }}"
                   min="0" placeholder="Порядок"
                   class="w-24 px-3 py-2 rounded-lg text-sm outline-none"
                   style="border: 1px solid var(--color-border);">
            <button type="submit"
                    class="px-4 py-2 rounded-lg text-white text-sm font-semibold ml-auto"
                    style="background: var(--color-primary);">
              Зберегти
            </button>
          </div>
        </form>
      </div>

      <!-- Articles list -->
      <div class="divide-y" style="border-color: var(--color-border);">
        {% for article in category.articles %}
        <div class="flex items-center gap-3 px-6 py-3">
          <span class="text-sm flex-1" style="color: var(--color-text);">
            📄 {{ article.title }}
          </span>
          <span class="text-xs px-2 py-0.5 rounded"
                style="{% if article.is_visible %}background:#F0FDF4; color:#16A34A;
                       {% else %}background:#F1F5F9; color:var(--color-text-muted);{% endif %}">
            {% if article.is_visible %}Опублікована{% else %}Чернетка{% endif %}
          </span>
          <span class="text-xs" style="color: var(--color-text-muted);">
            {{ article.updated_at.strftime('%d.%m.%y') }}
          </span>
          <a href="/admin/docs/article/{{ article.id }}/edit"
             class="text-xs hover:underline" style="color: var(--color-primary);">
            Редагувати
          </a>
          <form action="/admin/docs/article/{{ article.id }}/delete" method="post"
                onsubmit="return confirm('Видалити статтю?')">
            <button type="submit" class="text-xs" style="color: var(--color-error);">
              ×
            </button>
          </form>
        </div>
        {% else %}
        <p class="px-6 py-3 text-sm" style="color: var(--color-text-muted);">
          Статей поки немає
        </p>
        {% endfor %}
      </div>

    </div>
    {% endfor %}
  </div>

  <!-- Sidebar: нова категорія -->
  <div>
    <div class="rounded-2xl p-6 sticky top-6"
         style="background: var(--color-surface);
                border: 1px solid var(--color-border);
                box-shadow: var(--shadow-sm);">
      <h2 class="font-bold text-sm mb-4" style="font-family: var(--font-display);">
        Нова категорія
      </h2>
      <form action="/admin/docs/category/new" method="post" class="space-y-3">
        <div>
          <label class="text-xs font-medium block mb-1"
                 style="color: var(--color-text-muted);">Назва *</label>
          <input type="text" name="name" required
                 placeholder="Посадові інструкції"
                 class="w-full px-3 py-2 rounded-lg text-sm outline-none"
                 style="border: 1px solid var(--color-border);">
        </div>
        <div>
          <label class="text-xs font-medium block mb-1"
                 style="color: var(--color-text-muted);">Іконка (емодзі)</label>
          <input type="text" name="icon" value="📄"
                 class="w-full px-3 py-2 rounded-lg text-sm outline-none"
                 style="border: 1px solid var(--color-border);">
        </div>
        <div>
          <label class="text-xs font-medium block mb-1"
                 style="color: var(--color-text-muted);">Опис</label>
          <textarea name="description" rows="2" placeholder="Короткий опис..."
                    class="w-full px-3 py-2 rounded-lg text-sm outline-none resize-none"
                    style="border: 1px solid var(--color-border);"></textarea>
        </div>
        <input type="hidden" name="order_index" value="0">
        <button type="submit"
                class="w-full py-2 rounded-lg text-white text-sm font-semibold"
                style="background: var(--color-primary);">
          Створити категорію
        </button>
      </form>
    </div>
  </div>

</div>

<script>
function toggleCategoryForm(id) {
  const el = document.getElementById(id);
  el.classList.toggle('hidden');
}
</script>
{% endblock %}
```

---

### app/templates/admin/docs/article_edit.html

```html
{% extends "base.html" %}
{% block title %}{% if article %}Редагування{% else %}Нова стаття{% endif %}{% endblock %}

{% block extra_head %}
<style>
  /* Markdown preview стилі (ті ж що в docs/article.html) */
  #preview h1 { font-size: 1.5rem; font-weight: 800; margin: 1rem 0 0.75rem;
                font-family: var(--font-display); }
  #preview h2 { font-size: 1.2rem; font-weight: 700; margin: 1rem 0 0.5rem;
                font-family: var(--font-display);
                padding-bottom: 0.4rem; border-bottom: 2px solid var(--color-border); }
  #preview h3 { font-size: 1rem; font-weight: 700; margin: 0.75rem 0 0.4rem;
                font-family: var(--font-display); }
  #preview p  { margin: 0.5rem 0; line-height: 1.6; font-size: 0.9rem; }
  #preview ul, #preview ol { margin: 0.5rem 0 0.5rem 1.25rem; }
  #preview li { margin: 0.25rem 0; font-size: 0.9rem; }
  #preview code { background: #F1F5F9; padding: 0.1rem 0.3rem;
                  border-radius: 4px; font-size: 0.8rem; }
  #preview pre { background: #1A2332; color: #E2E8F0; padding: 1rem;
                 border-radius: 8px; overflow-x: auto; margin: 0.75rem 0; }
  #preview pre code { background: transparent; color: inherit; }
  #preview blockquote { border-left: 4px solid var(--color-accent);
                        padding: 0.5rem 0.75rem; background: #FFFBEB;
                        margin: 0.75rem 0; border-radius: 0 6px 6px 0; }
  #preview table { width: 100%; border-collapse: collapse; margin: 0.75rem 0;
                   font-size: 0.875rem; }
  #preview th { background: var(--color-bg); font-weight: 600;
                padding: 0.5rem 0.75rem; border-bottom: 2px solid var(--color-border); }
  #preview td { padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--color-border); }
  #preview a { color: var(--color-primary); text-decoration: underline; }

  .editor-pane { height: calc(100vh - 280px); min-height: 400px; }
  textarea#content { resize: none; }
</style>
{% endblock %}

{% block content %}
<div class="flex items-center gap-3 mb-6">
  <a href="/admin/docs" class="text-sm hover:underline"
     style="color: var(--color-text-muted);">← База знань</a>
  <h1 class="text-xl font-bold" style="font-family: var(--font-display);">
    {% if article %}{{ article.title }}{% else %}Нова стаття{% endif %}
  </h1>
</div>

<form action="{% if article %}/admin/docs/article/{{ article.id }}/update
             {% else %}/admin/docs/article/new{% endif %}"
      method="post">

  <!-- Top bar -->
  <div class="flex items-center gap-3 mb-4 p-4 rounded-xl"
       style="background: var(--color-surface); border: 1px solid var(--color-border);">

    <!-- Назва -->
    <input type="text" name="title" required
           value="{{ article.title if article else '' }}"
           placeholder="Назва статті"
           class="flex-1 px-4 py-2.5 rounded-xl text-base font-semibold outline-none"
           style="border: 1.5px solid var(--color-border);
                  font-family: var(--font-display);"
           onfocus="this.style.borderColor='var(--color-primary)'"
           onblur="this.style.borderColor='var(--color-border)'">

    <!-- Категорія -->
    <select name="category_id" required
            class="px-3 py-2.5 rounded-xl text-sm outline-none"
            style="border: 1.5px solid var(--color-border);">
      {% for cat in categories %}
      <option value="{{ cat.id }}"
        {% if article and article.category_id == cat.id %}selected{% endif %}>
        {{ cat.icon }} {{ cat.name }}
      </option>
      {% endfor %}
    </select>

    <!-- Порядок -->
    <input type="number" name="order_index" min="0"
           value="{{ article.order_index if article else 0 }}"
           class="w-20 px-3 py-2.5 rounded-xl text-sm outline-none text-center"
           style="border: 1.5px solid var(--color-border);"
           title="Порядок сортування">

    <!-- Публікація -->
    <label class="flex items-center gap-2 text-sm cursor-pointer px-3">
      <input type="checkbox" name="is_visible" value="true"
             {% if article and article.is_visible %}checked{% endif %}>
      <span style="color: var(--color-text);">Опублікувати</span>
    </label>

    <!-- Save -->
    <button type="submit"
            class="px-5 py-2.5 rounded-xl text-white text-sm font-semibold"
            style="background: var(--color-primary);">
      Зберегти
    </button>
  </div>

  <!-- Split editor -->
  <div class="grid grid-cols-2 gap-4">

    <!-- Editor -->
    <div class="editor-pane flex flex-col rounded-2xl overflow-hidden"
         style="background: var(--color-surface); border: 1px solid var(--color-border);">
      <div class="flex items-center gap-2 px-4 py-2.5 text-xs font-semibold uppercase tracking-wide"
           style="background: var(--color-bg); border-bottom: 1px solid var(--color-border);
                  color: var(--color-text-muted);">
        ✏️ Markdown редактор
      </div>
      <textarea
        id="content"
        name="content"
        class="flex-1 w-full px-5 py-4 text-sm outline-none font-mono"
        style="background: var(--color-surface); color: var(--color-text);
               line-height: 1.6; border: none;"
        placeholder="# Заголовок статті

## Розділ

Текст статті в **Markdown** форматі.

- Пункт 1
- Пункт 2

| Колонка 1 | Колонка 2 |
|-----------|-----------|
| Значення  | Значення  |"
        hx-post="/admin/docs/preview"
        hx-trigger="keyup changed delay:600ms"
        hx-target="#preview"
        hx-swap="innerHTML"
        hx-include="#content">{{ article.content if article else '' }}</textarea>
    </div>

    <!-- Preview -->
    <div class="editor-pane flex flex-col rounded-2xl overflow-hidden"
         style="background: var(--color-surface); border: 1px solid var(--color-border);">
      <div class="flex items-center gap-2 px-4 py-2.5 text-xs font-semibold uppercase tracking-wide"
           style="background: var(--color-bg); border-bottom: 1px solid var(--color-border);
                  color: var(--color-text-muted);">
        👁 Попередній перегляд
      </div>
      <div id="preview"
           class="flex-1 px-5 py-4 overflow-y-auto text-sm"
           style="line-height: 1.6;">
        {% if preview_html %}
          {{ preview_html | safe }}
        {% else %}
          <p style="color: var(--color-text-muted);">
            Почни писати — тут з'явиться попередній перегляд
          </p>
        {% endif %}
      </div>
    </div>

  </div>

</form>
{% endblock %}
```

---

## Завдання 10 — Зареєструвати роутери в app/main.py

Додай імпорти і реєстрацію:

```python
from app.routers import auth, trainee, admin, docs, admin_docs

app.include_router(auth.router)
app.include_router(trainee.router)
app.include_router(admin.router)
app.include_router(docs.router)
app.include_router(admin_docs.router)
```

---

## Завдання 11 — Оновити навігацію в base.html

Додай посилання "База знань" для стажистів:

```html
{% if request.state.user.role != 'admin' %}
  <a href="/docs" ...>📚 База знань</a>
{% endif %}
```

Для адміна в navbar або admin dashboard додай:

```html
<a href="/admin/docs" ...>📚 База знань</a>
```

---

## Завдання 12 — Міграція контенту з Jekyll

Створи файл `scripts/migrate_content.py` — скрипт що наповнить БД контентом з Jekyll сайту:

```python
"""
Скрипт міграції контенту з Jekyll в базу знань.
Запуск: python scripts/migrate_content.py

ВАЖЛИВО: запускати ПІСЛЯ alembic upgrade head
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.services.knowledge_service import create_category, create_article
import uuid

# UUID адміна — замінити на реальний після першого запуску сервера
# Отримати через: SELECT id FROM users WHERE role='admin' LIMIT 1;
ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")  # замінити!

CONTENT = [
    {
        "category": {
            "name": "Посадові інструкції",
            "description": "Функціональні обов'язки та вимоги по кожній посаді",
            "icon": "👔",
            "order_index": 1,
        },
        "articles": [
            {
                "title": "Менеджер первинної обробки (SDR)",
                "order_index": 1,
                "is_visible": True,
                "content": """# Функціональні обов'язки менеджера з первинної обробки

## Хто такий SDR у нашій команді?

**Sales Development Representative (SDR)** — це ключовий гравець у процесі лідогенерації,
який забезпечує перший контакт із потенційними клієнтами, кваліфікує ліди та передає їх
замовникам для подальшого опрацювання.

## 1. Мета твоєї ролі

Твоя головна задача — **якісна первинна обробка лідів**, їх **кваліфікація за чіткими
критеріями** та **передача кваліфікованих лідів менеджерам замовника**.

## 2. Твої ключові обов'язки

### 2.1. Первинна обробка лідів
- Здійснюєш холодні дзвінки, надсилаєш email/повідомлення в месенджерах
- Кваліфікуєш ліди за методологією компанії
- Фіксуєш взаємодії в CRM

### 2.2. Комунікація з потенційними клієнтами
- Використовуєш затверджені скрипти та шаблони
- Обробляєш заперечення, мотивуєш до наступного етапу

### 2.3. Звітність та контроль якості
- Відстежуєш виконання KPI
- Готуєш звіти про оброблені контакти та ліди

## 3. KPI

| Показник | Норма |
|----------|-------|
| Анкет на день | 120 |
| Термінових | 5 |
| Теплих | 8 |
| Передзвонів | 44 |
""",
            },
            {
                "title": "Помічник HR-рекрутера",
                "order_index": 2,
                "is_visible": True,
                "content": """# Помічник HR-рекрутера

## Завдання

Підтримка процесу підбору персоналу для команди OSD.

> Детальний опис додай вручну через адмін панель.
""",
            },
            {
                "title": "Координатор",
                "order_index": 3,
                "is_visible": True,
                "content": """# Координатор

## Завдання

Координація роботи команди менеджерів.

> Детальний опис додай вручну через адмін панель.
""",
            },
        ],
    },
    {
        "category": {
            "name": "Технічні питання",
            "description": "Вирішення типових технічних проблем на робочому місці",
            "icon": "🔧",
            "order_index": 2,
        },
        "articles": [
            {
                "title": "Технічні проблеми — FAQ",
                "order_index": 1,
                "is_visible": True,
                "content": """# Технічні питання та вирішення

## Мене/мій мікрофон погано чують

1. Перевір чи мікрофон підключений до правильного порту
2. Перевір рівень гучності в системних налаштуваннях
3. Зверніться до IT-спеціаліста якщо проблема не вирішена

## Не працюють кнопки в анкеті

- Спробуй оновити сторінку (F5)
- Перевір чи не заблокований JavaScript у браузері
- Використовуй Chrome або Firefox

## «Зриває» з'єднання

- Перевір інтернет-з'єднання
- Перезапусти браузер
- Зверніться до IT якщо проблема повторюється

> Якщо не знайшов відповідь — зверніться до IT-спеціаліста особисто або через Slack.
""",
            },
        ],
    },
    {
        "category": {
            "name": "Навчання",
            "description": "Навчальні матеріали, термінологія та перші кроки",
            "icon": "🎓",
            "order_index": 3,
        },
        "articles": [
            {
                "title": "Перші кроки в OSD",
                "order_index": 1,
                "is_visible": True,
                "content": """# Перші кроки в OSD

## Ласкаво просимо до команди!

Ця інструкція допоможе тобі швидко увійти в курс справи.

## Рекомендований графік дня

| Час | Інструкція |
|-----|-----------|
| **8:50 – 9:00** | Прийти на роботу, підготувати робоче місце |
| **9:00 – 9:30** | Командне навчання з керівником кластеру |
| **9:30 – 10:00** | Підготовка до роботи — прослуховування тренінгу |
| **13:00 – 14:00** | Обідня перерва |
| **17:30 – 18:00** | Командне навчання — аналіз розмов |
| **18:00** | Завершення робочого дня |

> 18:00 — завершення робочого дня, а не всі в дверях!

## Нормативи

- **120** анкет на день
- **5** термінових (гарячих/трансферів)
- **8** потенційно зацікавлених (теплих)
- **44** передзвонів
""",
            },
            {
                "title": "Термінологія та базові реакції",
                "order_index": 2,
                "is_visible": True,
                "content": """# Термінологія та базові реакції опрацювання клієнта

## Основні терміни

**Лід** — потенційний клієнт який виявив певний інтерес

**Кваліфікація** — процес визначення чи відповідає лід критеріям

**SDR** — Sales Development Representative, менеджер первинної обробки

**KPI** — ключові показники ефективності

> Детальний глосарій додай вручну через адмін панель.
""",
            },
        ],
    },
    {
        "category": {
            "name": "Документація та процеси",
            "description": "Оформлення документів, КП, анкети",
            "icon": "📋",
            "order_index": 4,
        },
        "articles": [
            {
                "title": "Оформлення записів в анкетах",
                "order_index": 1,
                "is_visible": True,
                "content": """# Оформлення записів в анкетах

## Як правильно оформити запис

> Детальну інструкцію додай вручну через адмін панель,
> скопіювавши контент з https://outsorcing.github.io/FAQ/anketa.html
""",
            },
            {
                "title": "Комерційна пропозиція",
                "order_index": 2,
                "is_visible": True,
                "content": """# Комерційна пропозиція

## Запит на матеріали для КП

> Детальну інструкцію додай вручну через адмін панель,
> скопіювавши контент з https://outsorcing.github.io/FAQ/commercial_offer.html
""",
            },
        ],
    },
]


async def migrate():
    async with SessionLocal() as db:
        print("🚀 Починаємо міграцію контенту...")

        for section in CONTENT:
            cat_data = section["category"]
            print(f"\n📁 Створюємо категорію: {cat_data['name']}")

            category = await create_category(
                db=db,
                name=cat_data["name"],
                description=cat_data["description"],
                icon=cat_data["icon"],
                order_index=cat_data["order_index"],
            )

            # Робимо категорію видимою
            category.is_visible = True

            for art_data in section["articles"]:
                print(f"   📄 Стаття: {art_data['title']}")
                await create_article(
                    db=db,
                    category_id=category.id,
                    title=art_data["title"],
                    content=art_data["content"],
                    order_index=art_data["order_index"],
                    created_by=ADMIN_ID,
                    is_visible=art_data["is_visible"],
                )

        await db.commit()
        print("\n✅ Міграцію завершено успішно!")
        print("👉 Відкрий /docs щоб перевірити результат")
        print("👉 Детальний контент додай вручну через /admin/docs")


if __name__ == "__main__":
    asyncio.run(migrate())
```

---

## Завдання 13 — Створи папки для шаблонів

```bash
mkdir -p app/templates/docs
mkdir -p app/templates/admin/docs
mkdir -p scripts
```

---

## Перевірка після виконання

```bash
# 1. Міграція БД
alembic upgrade head

# 2. Отримай UUID адміна для скрипта
# В psql: SELECT id FROM users WHERE role='admin' LIMIT 1;
# Встав UUID в scripts/migrate_content.py рядок ADMIN_ID

# 3. Запусти міграцію контенту
python scripts/migrate_content.py

# 4. Запусти сервер
uvicorn app.main:app --reload
```

Чекліст перевірки:
- [ ] `http://localhost:8000/docs` — список категорій з картками
- [ ] `/docs/posadovi-instruktsii` — список статей категорії
- [ ] `/docs/posadovi-instruktsii/menedzher-pervynnoyi-obrobky-sdr` — стаття з Markdown
- [ ] `/docs/search?q=менеджер` — результати пошуку
- [ ] `/admin/docs` — адмін панель бази знань
- [ ] `/admin/docs/article/new` — split-editor з live preview
- [ ] Редагування існуючої статті — HTMX preview оновлюється при друці
