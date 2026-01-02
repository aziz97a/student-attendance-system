from __future__ import annotations
from .user import User
from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db


class Student(db.Model):
    __tablename__ = "students"

    # 1–1: PK is also FK to users.id
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    student_no: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)
    year_level: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped["User"] = relationship(
        "User",
        back_populates="student_profile",
        lazy="joined",
    )

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "student_no": self.student_no,
            "department": self.department,
            "year_level": self.year_level,
        }
