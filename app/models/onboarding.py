from __future__ import annotations
import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import (
    String, Text, Boolean, Integer, ForeignKey,
    DateTime, Enum, func, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.knowledge import Article
    from app.models.quiz import Quiz

ITEM_TYPES = Enum(
    "article",    # стаття бази знань
    "quiz",       # квіз
    "checklist",  # текстовий чекліст
    "url",        # зовнішнє посилання
    name="onboarding_item_type",
)


class OnboardingTrack(Base):
    """Програма онбордингу для конкретної посади."""
    __tablename__ = "onboarding_tracks"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    position_name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    stages: Mapped[list[TrackStage]] = relationship(
        back_populates="track",
        cascade="all, delete-orphan",
        order_by="TrackStage.order_index",
    )
    assignments: Mapped[list[UserTrack]] = relationship(
        back_populates="track",
        cascade="all, delete-orphan",
    )
    author: Mapped[User | None] = relationship(foreign_keys=[created_by])

    def __repr__(self) -> str:
        return f"<OnboardingTrack '{self.title}'>"


class TrackStage(Base):
    """Етап онбордингу."""
    __tablename__ = "track_stages"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("onboarding_tracks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    track: Mapped[OnboardingTrack] = relationship(back_populates="stages")
    items: Mapped[list[StageItem]] = relationship(
        back_populates="stage",
        cascade="all, delete-orphan",
        order_by="StageItem.order_index",
    )

    def __repr__(self) -> str:
        return f"<TrackStage '{self.title}'>"


class StageItem(Base):
    """Елемент етапу онбордингу."""
    __tablename__ = "stage_items"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("track_stages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    item_type: Mapped[str] = mapped_column(ITEM_TYPES, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Залежно від типу заповнюється одне з полів:
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("kb_articles.id", ondelete="SET NULL"), nullable=True
    )
    quiz_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("quizzes.id", ondelete="SET NULL"), nullable=True
    )
    external_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    checklist_items: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON список рядків

    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    stage: Mapped[TrackStage] = relationship(back_populates="items")
    article: Mapped[Article | None] = relationship(foreign_keys=[article_id])
    quiz: Mapped[Quiz | None] = relationship(foreign_keys=[quiz_id])

    def __repr__(self) -> str:
        return f"<StageItem '{self.title}' ({self.item_type})>"


class UserTrack(Base):
    """Призначення програми онбордингу стажеру."""
    __tablename__ = "user_tracks"
    __table_args__ = (
        UniqueConstraint("user_id", "track_id", name="uq_user_track"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("onboarding_tracks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    track: Mapped[OnboardingTrack] = relationship(back_populates="assignments")
    assigner: Mapped[User | None] = relationship(foreign_keys=[assigned_by])
    progress: Mapped[list[UserItemProgress]] = relationship(
        back_populates="user_track",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<UserTrack user={self.user_id} track={self.track_id}>"


class UserItemProgress(Base):
    """Прогрес виконання елементу стажером."""
    __tablename__ = "user_item_progress"
    __table_args__ = (
        UniqueConstraint(
            "user_track_id", "item_id",
            name="uq_user_track_item"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    user_track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_tracks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stage_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user_track: Mapped[UserTrack] = relationship(back_populates="progress")
    item: Mapped[StageItem] = relationship()
    completer: Mapped[User | None] = relationship(foreign_keys=[completed_by])
