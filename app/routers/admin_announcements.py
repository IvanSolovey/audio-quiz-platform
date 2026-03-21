from __future__ import annotations
import uuid
from datetime import datetime, timezone
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
    content: str = Form(...),
    audience: str = Form(...),
    cta_text: str = Form(""),
    cta_url: str = Form(""),
    expires_at: str = Form(""),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_announcements")),
):
    parsed_expires = None
    if expires_at.strip():
        try:
            parsed_expires = datetime.fromisoformat(expires_at).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            pass

    await create_announcement(
        db=db,
        title=title,
        body=content,
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
