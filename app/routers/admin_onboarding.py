from __future__ import annotations
import uuid
import json
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_permission
from app.models.user import User
from app.models.onboarding import (
    OnboardingTrack, TrackStage, StageItem, UserTrack, UserItemProgress
)
from app.models.knowledge import Article
from app.models.quiz import Quiz
from app.services.onboarding_service import (
    get_all_tracks, get_track_by_id,
    assign_track_to_user, mark_item_complete,
    mark_item_incomplete, get_user_track,
    get_completed_item_ids, calculate_stage_progress,
    get_checklist_items,
)

router = APIRouter(prefix="/admin/onboarding", tags=["admin-onboarding"])
templates = Jinja2Templates(directory="app/templates")


# ─── Tracks ───────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def onboarding_index(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_users")),
):
    tracks = await get_all_tracks(db)

    result = await db.execute(
        select(User).where(User.role == "trainee").order_by(User.name)
    )
    trainees = list(result.scalars().all())

    assignments_result = await db.execute(
        select(UserTrack).options(
            selectinload(UserTrack.user),
            selectinload(UserTrack.track),
        )
    )
    assignments = list(assignments_result.scalars().all())

    return templates.TemplateResponse("admin/onboarding/index.html", {
        "request": request,
        "tracks": tracks,
        "trainees": trainees,
        "assignments": assignments,
        "user": admin,
    })


@router.post("/track/new")
async def create_track(
    request: Request,
    title: str = Form(...),
    position_name: str = Form(...),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_users")),
):
    track = OnboardingTrack(
        title=title.strip(),
        position_name=position_name.strip(),
        description=description.strip() or None,
        created_by=admin.id,
    )
    db.add(track)
    await db.flush()
    await db.commit()

    request.session["flash"] = {
        "type": "success",
        "message": f"Програму '{title}' створено!",
    }
    return RedirectResponse(f"/admin/onboarding/track/{track.id}", status_code=303)


@router.get("/track/{track_id}", response_class=HTMLResponse)
async def edit_track(
    request: Request,
    track_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_users")),
):
    track = await get_track_by_id(db, track_id)
    if not track:
        raise HTTPException(status_code=404)

    articles_result = await db.execute(
        select(Article).where(Article.is_visible == True).order_by(Article.title)
    )
    articles = list(articles_result.scalars().all())

    quizzes_result = await db.execute(
        select(Quiz).where(Quiz.is_published == True).order_by(Quiz.title)
    )
    quizzes = list(quizzes_result.scalars().all())

    return templates.TemplateResponse("admin/onboarding/track_edit.html", {
        "request": request,
        "track": track,
        "articles": articles,
        "quizzes": quizzes,
        "user": admin,
    })


@router.post("/track/{track_id}/delete")
async def delete_track(
    track_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_users")),
):
    result = await db.execute(
        select(OnboardingTrack).where(OnboardingTrack.id == track_id)
    )
    track = result.scalar_one_or_none()
    if track:
        await db.delete(track)
        await db.commit()
    return RedirectResponse("/admin/onboarding", status_code=303)


# ─── Stages ───────────────────────────────────────────────────────────────────

@router.post("/track/{track_id}/stage/add")
async def add_stage(
    request: Request,
    track_id: uuid.UUID,
    title: str = Form(...),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_users")),
):
    track = await get_track_by_id(db, track_id)
    if not track:
        raise HTTPException(status_code=404)

    stage = TrackStage(
        track_id=track_id,
        title=title.strip(),
        description=description.strip() or None,
        order_index=len(track.stages),
    )
    db.add(stage)
    await db.commit()

    request.session["flash"] = {"type": "success", "message": "Етап додано!"}
    return RedirectResponse(f"/admin/onboarding/track/{track_id}", status_code=303)


@router.post("/track/{track_id}/stage/{stage_id}/delete")
async def delete_stage(
    track_id: uuid.UUID,
    stage_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_users")),
):
    result = await db.execute(
        select(TrackStage).where(TrackStage.id == stage_id)
    )
    stage = result.scalar_one_or_none()
    if stage:
        await db.delete(stage)
        await db.commit()
    return RedirectResponse(f"/admin/onboarding/track/{track_id}", status_code=303)


# ─── Items ────────────────────────────────────────────────────────────────────

@router.post("/track/{track_id}/stage/{stage_id}/item/add")
async def add_item(
    request: Request,
    track_id: uuid.UUID,
    stage_id: uuid.UUID,
    title: str = Form(...),
    item_type: str = Form(...),
    description: str = Form(""),
    article_id: str = Form(""),
    quiz_id: str = Form(""),
    external_url: str = Form(""),
    checklist_text: str = Form(""),
    is_required: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_users")),
):
    result = await db.execute(
        select(TrackStage)
        .where(TrackStage.id == stage_id)
        .options(selectinload(TrackStage.items))
    )
    stage = result.scalar_one_or_none()
    if not stage:
        raise HTTPException(status_code=404)

    # Парсинг чекліста — кожен рядок окремий пункт
    checklist_json = None
    if item_type == "checklist" and checklist_text.strip():
        items = [
            line.strip()
            for line in checklist_text.strip().splitlines()
            if line.strip()
        ]
        checklist_json = json.dumps(items, ensure_ascii=False)

    item = StageItem(
        stage_id=stage_id,
        title=title.strip(),
        item_type=item_type,
        description=description.strip() or None,
        article_id=uuid.UUID(article_id) if article_id.strip() else None,
        quiz_id=uuid.UUID(quiz_id) if quiz_id.strip() else None,
        external_url=external_url.strip() or None,
        checklist_items=checklist_json,
        is_required=is_required,
        order_index=len(stage.items),
    )
    db.add(item)
    await db.commit()

    request.session["flash"] = {"type": "success", "message": "Елемент додано!"}
    return RedirectResponse(f"/admin/onboarding/track/{track_id}", status_code=303)


@router.post("/track/{track_id}/stage/{stage_id}/item/{item_id}/delete")
async def delete_item(
    track_id: uuid.UUID,
    stage_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_users")),
):
    result = await db.execute(
        select(StageItem).where(StageItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if item:
        await db.delete(item)
        await db.commit()
    return RedirectResponse(f"/admin/onboarding/track/{track_id}", status_code=303)


# ─── Assignments ──────────────────────────────────────────────────────────────

@router.post("/assign")
async def assign_track(
    request: Request,
    user_id: str = Form(...),
    track_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_users")),
):
    await assign_track_to_user(
        db=db,
        user_id=uuid.UUID(user_id),
        track_id=uuid.UUID(track_id),
        assigned_by_id=admin.id,
    )
    await db.commit()

    request.session["flash"] = {
        "type": "success",
        "message": "Програму онбордингу призначено!",
    }
    return RedirectResponse("/admin/onboarding", status_code=303)


# ─── Admin mark complete ───────────────────────────────────────────────────────

@router.post("/user/{user_id}/item/{item_id}/complete")
async def admin_complete_item(
    request: Request,
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_users")),
):
    """Адмін відмічає виконання за стажера."""
    user_track = await get_user_track(db, user_id)
    if not user_track:
        raise HTTPException(status_code=404)

    await mark_item_complete(db, user_track.id, item_id, admin.id)
    await db.commit()

    request.session["flash"] = {"type": "success", "message": "Відмічено!"}
    return RedirectResponse(
        f"/admin/onboarding/user/{user_id}", status_code=303
    )


@router.post("/user/{user_id}/unassign")
async def unassign_track(
    request: Request,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_users")),
):
    """Видалити призначену програму онбордингу зі стажера."""
    result = await db.execute(
        select(UserTrack).where(UserTrack.user_id == user_id)
    )
    user_track = result.scalar_one_or_none()
    if user_track:
        await db.delete(user_track)
        await db.commit()

    request.session["flash"] = {
        "type": "success",
        "message": "Програму онбордингу знято зі стажера",
    }
    return RedirectResponse(f"/admin/trainees/{user_id}", status_code=303)


@router.get("/user/{user_id}", response_class=HTMLResponse)
async def view_user_progress(
    request: Request,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("manage_users")),
):
    """Перегляд прогресу конкретного стажера."""
    result = await db.execute(select(User).where(User.id == user_id))
    trainee = result.scalar_one_or_none()
    if not trainee:
        raise HTTPException(status_code=404)

    user_track = await get_user_track(db, user_id)
    completed_ids: set[uuid.UUID] = set()
    if user_track:
        completed_ids = await get_completed_item_ids(db, user_track.id)

    return templates.TemplateResponse("admin/onboarding/user_progress.html", {
        "request": request,
        "trainee": trainee,
        "user_track": user_track,
        "completed_ids": completed_ids,
        "calculate_stage_progress": calculate_stage_progress,
        "get_checklist_items": get_checklist_items,
        "user": admin,
    })
