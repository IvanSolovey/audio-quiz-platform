from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import (
    String, Boolean, Text, DateTime,
    ForeignKey, Enum, func, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


AUDIENCE_TYPES = Enum(
    "all",
    "trainees",
    "admins",
    name="announcement_audience",
)


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    cta_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cta_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    audience: Mapped[str] = mapped_column(
        AUDIENCE_TYPES, nullable=False, default="all"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    reads: Mapped[list[AnnouncementRead]] = relationship(
        back_populates="announcement",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    author: Mapped[object | None] = relationship(
        "User", foreign_keys=[created_by], lazy="raise"
    )

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        from datetime import timezone
        return datetime.now(timezone.utc) > self.expires_at

    def __repr__(self) -> str:
        return f"<Announcement '{self.title}' → {self.audience}>"


class AnnouncementRead(Base):
    __tablename__ = "announcement_reads"
    __table_args__ = (
        UniqueConstraint(
            "announcement_id", "user_id",
            name="uq_announcement_user"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    announcement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    announcement: Mapped[Announcement] = relationship(
        back_populates="reads", lazy="raise"
    )
    user: Mapped[object] = relationship("User", lazy="raise")
