from __future__ import annotations
import uuid
import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.onboarding import (
    OnboardingTrack, TrackStage, StageItem,
    UserTrack, UserItemProgress
)
from app.models.knowledge import Article, Category
from app.models.user import User


async def get_all_tracks(db: AsyncSession) -> list[OnboardingTrack]:
    result = await db.execute(
        select(OnboardingTrack)
        .options(
            selectinload(OnboardingTrack.stages)
            .selectinload(TrackStage.items)
        )
        .order_by(OnboardingTrack.created_at.desc())
    )
    return list(result.scalars().all())


async def get_track_by_id(
    db: AsyncSession, track_id: uuid.UUID
) -> OnboardingTrack | None:
    result = await db.execute(
        select(OnboardingTrack)
        .where(OnboardingTrack.id == track_id)
        .options(
            selectinload(OnboardingTrack.stages)
            .selectinload(TrackStage.items)
            .selectinload(StageItem.article)
            .selectinload(Article.category),
            selectinload(OnboardingTrack.stages)
            .selectinload(TrackStage.items)
            .selectinload(StageItem.quiz),
        )
    )
    return result.scalar_one_or_none()


async def get_user_track(
    db: AsyncSession, user_id: uuid.UUID
) -> UserTrack | None:
    """Отримати активну програму онбордингу стажера."""
    result = await db.execute(
        select(UserTrack)
        .where(UserTrack.user_id == user_id)
        .options(
            selectinload(UserTrack.track)
            .selectinload(OnboardingTrack.stages)
            .selectinload(TrackStage.items)
            .selectinload(StageItem.article)
            .selectinload(Article.category),
            selectinload(UserTrack.track)
            .selectinload(OnboardingTrack.stages)
            .selectinload(TrackStage.items)
            .selectinload(StageItem.quiz),
            selectinload(UserTrack.progress),
            selectinload(UserTrack.assigner),
        )
        .order_by(UserTrack.assigned_at.desc())
    )
    return result.scalar_one_or_none()


async def get_completed_item_ids(
    db: AsyncSession, user_track_id: uuid.UUID
) -> set[uuid.UUID]:
    """Повертає множину ID виконаних елементів."""
    result = await db.execute(
        select(UserItemProgress.item_id)
        .where(
            UserItemProgress.user_track_id == user_track_id,
            UserItemProgress.is_completed == True,
        )
    )
    return {row[0] for row in result.all()}


async def mark_item_complete(
    db: AsyncSession,
    user_track_id: uuid.UUID,
    item_id: uuid.UUID,
    completed_by_id: uuid.UUID,
) -> UserItemProgress:
    """Відмітити елемент як виконаний."""
    result = await db.execute(
        select(UserItemProgress).where(
            UserItemProgress.user_track_id == user_track_id,
            UserItemProgress.item_id == item_id,
        )
    )
    progress = result.scalar_one_or_none()

    if progress:
        progress.is_completed = True
        progress.completed_by = completed_by_id
        progress.completed_at = datetime.now(timezone.utc)
    else:
        progress = UserItemProgress(
            user_track_id=user_track_id,
            item_id=item_id,
            is_completed=True,
            completed_by=completed_by_id,
            completed_at=datetime.now(timezone.utc),
        )
        db.add(progress)

    await db.flush()
    return progress


async def mark_item_incomplete(
    db: AsyncSession,
    user_track_id: uuid.UUID,
    item_id: uuid.UUID,
) -> None:
    """Зняти відмітку виконання."""
    result = await db.execute(
        select(UserItemProgress).where(
            UserItemProgress.user_track_id == user_track_id,
            UserItemProgress.item_id == item_id,
        )
    )
    progress = result.scalar_one_or_none()
    if progress:
        progress.is_completed = False
        progress.completed_by = None
        progress.completed_at = None
        await db.flush()


async def assign_track_to_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    track_id: uuid.UUID,
    assigned_by_id: uuid.UUID,
) -> UserTrack:
    """Призначити програму онбордингу стажеру."""
    # Видалити попередню якщо є
    existing = await db.execute(
        select(UserTrack).where(UserTrack.user_id == user_id)
    )
    old = existing.scalar_one_or_none()
    if old:
        await db.delete(old)
        await db.flush()

    user_track = UserTrack(
        user_id=user_id,
        track_id=track_id,
        assigned_by=assigned_by_id,
    )
    db.add(user_track)
    await db.flush()
    await db.refresh(user_track)
    return user_track


def calculate_stage_progress(
    stage: TrackStage,
    completed_ids: set[uuid.UUID],
) -> dict:
    """Підраховує прогрес виконання етапу."""
    total = len(stage.items)
    required = [i for i in stage.items if i.is_required]
    completed = [i for i in stage.items if i.id in completed_ids]
    required_completed = [i for i in required if i.id in completed_ids]

    return {
        "total": total,
        "completed": len(completed),
        "required_total": len(required),
        "required_completed": len(required_completed),
        "is_complete": len(required_completed) >= len(required) if required else len(completed) >= total,
        "percent": round(len(completed) / total * 100) if total > 0 else 0,
    }


def get_checklist_items(item: StageItem) -> list[str]:
    """Повертає список пунктів чекліста."""
    if not item.checklist_items:
        return []
    try:
        return json.loads(item.checklist_items)
    except Exception:
        return [item.checklist_items]
