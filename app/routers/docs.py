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

    content_html = render_markdown(article.content)

    return templates.TemplateResponse("docs/article.html", {
        "request": request,
        "article": article,
        "category": article.category,
        "content_html": content_html,
        "user": current_user,
    })
