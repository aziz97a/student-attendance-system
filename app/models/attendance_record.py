from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, DateTime, String, Enum as SAEnum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db

if TYPE_CHECKING:
    from .attendance_session import AttendanceSession
    from .user import User


class AttendanceStatus(str, Enum):
    present = "present"
    late = "late"
    absent = "absent"


class AttendanceRecord(db.Model):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_session_student"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    session_id: Mapped[int] = mapped_column(
        ForeignKey("attendance_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[AttendanceStatus] = mapped_column(
        SAEnum(AttendanceStatus, name="attendance_status"),
        nullable=False,
        default=AttendanceStatus.present,
        index=True,
    )

    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # relationships
    session: Mapped["AttendanceSession"] = relationship("AttendanceSession", back_populates="records", lazy="joined")
    student: Mapped["User"] = relationship("User", back_populates="attendance_records", lazy="joined")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "student_id": self.student_id,
            "status": self.status.value,
            "checked_in_at": self.checked_in_at.isoformat() if self.checked_in_at else None,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
