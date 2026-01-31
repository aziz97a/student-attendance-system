from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, DateTime, Float, Integer, UniqueConstraint, String
from sqlalchemy import Enum as SAEnum
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
        ForeignKey("users.id", ondelete="RESTRICT"),
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

    # these must be nullable because ABSENT has no location
    student_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    student_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_m: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped["AttendanceSession"] = relationship("AttendanceSession", back_populates="records")
    # optional if you have it:
    student: Mapped["User"] = relationship("User", back_populates="attendance_records")

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "student_id": self.student_id,
            "status": self.status.value,
            "checked_in_at": self.checked_in_at.isoformat() if self.checked_in_at else None,
            "student_lat": self.student_lat,
            "student_lng": self.student_lng,
            "distance_m": self.distance_m,
            "note": self.note,
        }
