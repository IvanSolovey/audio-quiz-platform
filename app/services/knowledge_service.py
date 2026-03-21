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
