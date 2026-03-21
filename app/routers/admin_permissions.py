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
from app.services.auth_service import (
    get_all_admins,
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
    ("manage_announcements", "Оповіщення", "📣"),
    ("manage_admins", "Призначення прав адмінам", "🔑"),
]


@router.get("", response_class=HTMLResponse)
async def permissions_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_admins")),
):
    admins = await get_all_admins(db)

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
    result = await db.execute(
        select(User)
        .where(User.id == uuid.UUID(user_id))
        .options(selectinload(User.permissions))
    )
    target = result.scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404)

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
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.permissions))
    )
    target = result.scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404)

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
