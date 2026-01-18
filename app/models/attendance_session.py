from __future__ import annotations

from datetime import datetime, date
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, DateTime, Date, String, Float, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db

if TYPE_CHECKING:
    from .course import Course
    from .user import User
    from .attendance_record import AttendanceRecord


class AttendanceSession(db.Model):
    __tablename__ = "attendance_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # classroom location (from teacher phone)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    radius_m: Mapped[int] = mapped_column(Integer, nullable=False, default=50)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    qr_token: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # relationships
    course: Mapped["Course"] = relationship("Course", back_populates="sessions", lazy="joined")
    teacher: Mapped["User"] = relationship("User", back_populates="sessions_created", lazy="joined")

    records: Mapped[list["AttendanceRecord"]] = relationship(
        "AttendanceRecord",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def is_open(self, now: datetime) -> bool:
        """True if session is active AND within time window."""
        return self.is_active and self.starts_at <= now <= self.ends_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "course_id": self.course_id,
            "teacher_id": self.teacher_id,
            "session_date": self.session_date.isoformat(),
            "starts_at": self.starts_at.isoformat(),
            "ends_at": self.ends_at.isoformat(),
            "lat": self.lat,
            "lng": self.lng,
            "radius_m": self.radius_m,
            "is_active": self.is_active,
            "qr_token": self.qr_token,
            "created_at": self.created_at.isoformat(),
        }
