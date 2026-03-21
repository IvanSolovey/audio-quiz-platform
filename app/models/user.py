from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Enum, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


USER_ROLES = Enum("trainee", "admin", "superadmin", name="user_role")

PERMISSION_TYPES = Enum(
    "manage_quizzes",
    "manage_knowledge",
    "view_results",
    "manage_users",
    "manage_announcements",
    "manage_admins",
    name="permission_type",
)


class AdminPermission(Base):
    __tablename__ = "admin_permissions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission: Mapped[str] = mapped_column(PERMISSION_TYPES, nullable=False)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(
        "User", foreign_keys=[user_id], back_populates="permissions", lazy="raise"
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        USER_ROLES,
        nullable=False,
        default="trainee",
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    manager_login_id: Mapped[str | None] = mapped_column(
        String(20),
        unique=True,
        nullable=True,
        index=True,
        comment="Числовий ID з панелі менеджера (1001, 1002...)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    quizzes_created: Mapped[list] = relationship(
        "Quiz", back_populates="creator", lazy="raise"
    )
    attempts: Mapped[list] = relationship(
        "QuizAttempt", back_populates="user", lazy="raise"
    )
    permissions: Mapped[list[AdminPermission]] = relationship(
        "AdminPermission",
        foreign_keys=[AdminPermission.user_id],
        back_populates="user",
        lazy="raise",
        cascade="all, delete-orphan",
    )

    # ─── Permission helpers ────────────────────────────────────────────────────

    @property
    def is_superadmin(self) -> bool:
        return self.role == "superadmin"

    @property
    def is_admin_or_above(self) -> bool:
        return self.role in ("admin", "superadmin")

    def has_permission(self, permission: str) -> bool:
        """Superadmin has all permissions implicitly."""
        if self.is_superadmin:
            return True
        try:
            return any(p.permission == permission for p in self.permissions)
        except Exception:
            return False

    def can_manage_admin(self, target: User) -> bool:
        """Can this user manage (edit/demote) the target admin?"""
        if self.is_superadmin:
            return not target.is_superadmin  # superadmin can manage all non-superadmins
        if target.is_superadmin:
            return False
        return self.has_permission("manage_admins")

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"
