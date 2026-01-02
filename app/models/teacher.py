from __future__ import annotations
from .user import User
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db


class Teacher(db.Model):
    __tablename__ = "teachers"

    # 1–1: PK is also FK to users.id
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    staff_no: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)

    user: Mapped["User"] = relationship(
        "User",
        back_populates="teacher_profile",
        lazy="joined",
    )

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "staff_no": self.staff_no,
            "title": self.title,
        }
