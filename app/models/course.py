from __future__ import annotations
from datetime import datetime


from typing import TYPE_CHECKING

from sqlalchemy import String, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db

if TYPE_CHECKING:
    from .enrollment import Enrollment
    from app.models.attendance_session import AttendanceSession
    from .user import User
    
class Course(db.Model):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)  # e.g., CS101
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    planned_sessions: Mapped[int] = mapped_column(nullable=False, default=14)

    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    semester: Mapped[str | None] = mapped_column(String(40), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # relations
    teacher: Mapped["User"] = relationship("User", back_populates="courses_taught", lazy="joined")
    enrollments: Mapped[list["Enrollment"]] = relationship(
        "Enrollment",
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    sessions: Mapped[list["AttendanceSession"]] = relationship(
        "AttendanceSession",
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "teacher_id": self.teacher_id,
            "semester": self.semester,
            "planned_sessions": self.planned_sessions,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
