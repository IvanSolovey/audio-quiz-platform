from __future__ import annotations
import uuid
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_permission
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
    admin: User = Depends(require_permission("manage_knowledge")),
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
    admin: User = Depends(require_permission("manage_knowledge")),
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
    admin: User = Depends(require_permission("manage_knowledge")),
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
    admin: User = Depends(require_permission("manage_knowledge")),
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
    admin: User = Depends(require_permission("manage_knowledge")),
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
    admin: User = Depends(require_permission("manage_knowledge")),
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
    admin: User = Depends(require_permission("manage_knowledge")),
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
    admin: User = Depends(require_permission("manage_knowledge")),
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
    admin: User = Depends(require_permission("manage_knowledge")),
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
    admin: User = Depends(require_permission("manage_knowledge")),
):
    """HTMX ендпоінт — повертає HTML рендер Markdown для live preview."""
    html = render_markdown(content)
    return HTMLResponse(content=html)
