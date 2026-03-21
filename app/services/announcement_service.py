from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.announcement import Announcement, AnnouncementRead
from app.models.user import User


async def get_pending_announcements(
    db: AsyncSession,
    user: User,
) -> list[Announcement]:
    """
    Повертає список активних непрочитаних оповіщень для конкретного юзера.
    Відфільтровані за аудиторією, активністю та датою закінчення.
    Відсортовані від найстаріших до найновіших.
    """
    now = datetime.now(timezone.utc)

    already_read = (
        select(AnnouncementRead.announcement_id)
        .where(AnnouncementRead.user_id == user.id)
        .scalar_subquery()
    )

    if user.role == "trainee":
        audience_filter = Announcement.audience.in_(["all", "trainees"])
    elif user.is_admin_or_above:
        audience_filter = Announcement.audience.in_(["all", "admins"])
    else:
        audience_filter = Announcement.audience == "all"

    stmt = (
        select(Announcement)
        .where(
            and_(
                Announcement.is_active == True,
                audience_filter,
                Announcement.id.not_in(already_read),
                or_(
                    Announcement.expires_at == None,
                    Announcement.expires_at > now,
                ),
            )
        )
        .order_by(Announcement.created_at.asc())
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def mark_as_read(
    db: AsyncSession,
    announcement_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Позначити оповіщення як прочитане. Ігнорує якщо вже прочитане."""
    existing = await db.execute(
        select(AnnouncementRead).where(
            AnnouncementRead.announcement_id == announcement_id,
            AnnouncementRead.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        return

    read = AnnouncementRead(
        announcement_id=announcement_id,
        user_id=user_id,
    )
    db.add(read)
    await db.flush()


async def get_all_announcements(
    db: AsyncSession,
) -> list[Announcement]:
    """Всі оповіщення для адмін панелі."""
    result = await db.execute(
        select(Announcement)
        .options(selectinload(Announcement.reads))
        .order_by(Announcement.created_at.desc())
    )
    return list(result.scalars().all())


async def get_announcement_by_id(
    db: AsyncSession,
    announcement_id: uuid.UUID,
) -> Announcement | None:
    result = await db.execute(
        select(Announcement)
        .where(Announcement.id == announcement_id)
        .options(selectinload(Announcement.reads))
    )
    return result.scalar_one_or_none()


async def create_announcement(
    db: AsyncSession,
    title: str,
    body: str,
    audience: str,
    created_by: uuid.UUID,
    cta_text: str | None = None,
    cta_url: str | None = None,
    expires_at: datetime | None = None,
) -> Announcement:
    announcement = Announcement(
        title=title.strip(),
        body=body.strip(),
        audience=audience,
        created_by=created_by,
        cta_text=cta_text.strip() if cta_text else None,
        cta_url=cta_url.strip() if cta_url else None,
        expires_at=expires_at,
        is_active=True,
    )
    db.add(announcement)
    await db.flush()
    await db.refresh(announcement)
    return announcement


async def toggle_announcement(
    db: AsyncSession,
    announcement: Announcement,
) -> Announcement:
    """Вмикає/вимикає оповіщення."""
    announcement.is_active = not announcement.is_active
    await db.flush()
    return announcement


async def delete_announcement(
    db: AsyncSession,
    announcement: Announcement,
) -> None:
    await db.delete(announcement)
    await db.flush()
