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
from app.services.knowledge_service import render_markdown

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
    """
    pending = await get_pending_announcements(db, current_user)

    if not pending:
        return HTMLResponse("")

    announcement = pending[0]
    remaining = len(pending) - 1

    return templates.TemplateResponse(
        "partials/announcement_modal.html",
        {
            "request": request,
            "announcement": announcement,
            "body_html": render_markdown(announcement.body),
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
    HTMX ендпоінт — позначає оповіщення як прочитане,
    потім повертає наступне непрочитане або порожній рядок.
    """
    await mark_as_read(db, announcement_id, current_user.id)
    await db.commit()

    pending = await get_pending_announcements(db, current_user)

    if not pending:
        return HTMLResponse("")

    next_announcement = pending[0]
    remaining = len(pending) - 1

    return templates.TemplateResponse(
        "partials/announcement_modal.html",
        {
            "request": request,
            "announcement": next_announcement,
            "body_html": render_markdown(next_announcement.body),
            "remaining": remaining,
        },
    )
