from __future__ import annotations

from typing import Optional
from datetime import datetime

from sqlalchemy import Integer, String, DateTime, ForeignKey, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

class StudentPointAdjustment(Base):
    __tablename__ = "student_point_adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    student_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # how many points changed (+10, -5, etc.)
    delta_points: Mapped[int] = mapped_column(Integer, nullable=False)

    # total after change
    new_total_points: Mapped[int] = mapped_column(Integer, nullable=False)

    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # admin who changed it (if you have admin/faculty id)
    created_by_admin_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Optional: relationship back to Student (only if you want)
    student = relationship("Student", back_populates="point_adjustments")

    __table_args__ = (
        Index("ix_point_adj_student_created", "student_id", "created_at"),
    )