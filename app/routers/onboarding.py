from __future__ import annotations
import uuid
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_user
from app.models.user import User
from app.services.onboarding_service import (
    get_user_track,
    get_completed_item_ids,
    mark_item_complete,
    mark_item_incomplete,
    calculate_stage_progress,
    get_checklist_items,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/timeline", response_class=HTMLResponse)
async def get_timeline(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    user_track = await get_user_track(db, current_user.id)
    completed_ids: set[uuid.UUID] = set()
    if user_track:
        completed_ids = await get_completed_item_ids(db, user_track.id)

    return templates.TemplateResponse(
        "partials/onboarding_timeline.html",
        {
            "request": request,
            "user_track": user_track,
            "completed_ids": completed_ids,
            "calculate_stage_progress": calculate_stage_progress,
            "get_checklist_items": get_checklist_items,
            "user": current_user,
        },
    )


@router.post("/item/{item_id}/complete", response_class=HTMLResponse)
async def complete_item(
    request: Request,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """HTMX — відмітити елемент як виконаний."""
    user_track = await get_user_track(db, current_user.id)
    if not user_track:
        return HTMLResponse("")

    await mark_item_complete(db, user_track.id, item_id, current_user.id)
    await db.commit()

    # Повернути оновлений таймлайн
    user_track = await get_user_track(db, current_user.id)
    completed_ids = await get_completed_item_ids(db, user_track.id)

    return templates.TemplateResponse(
        "partials/onboarding_timeline.html",
        {
            "request": request,
            "user_track": user_track,
            "completed_ids": completed_ids,
            "calculate_stage_progress": calculate_stage_progress,
            "get_checklist_items": get_checklist_items,
            "user": current_user,
        },
    )


@router.post("/item/{item_id}/uncomplete", response_class=HTMLResponse)
async def uncomplete_item(
    request: Request,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """HTMX — зняти відмітку виконання."""
    user_track = await get_user_track(db, current_user.id)
    if not user_track:
        return HTMLResponse("")

    await mark_item_incomplete(db, user_track.id, item_id)
    await db.commit()

    user_track = await get_user_track(db, current_user.id)
    completed_ids = await get_completed_item_ids(db, user_track.id)

    return templates.TemplateResponse(
        "partials/onboarding_timeline.html",
        {
            "request": request,
            "user_track": user_track,
            "completed_ids": completed_ids,
            "calculate_stage_progress": calculate_stage_progress,
            "get_checklist_items": get_checklist_items,
            "user": current_user,
        },
    )
