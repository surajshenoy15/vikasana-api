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

    # actual change in total points
    delta_points: Mapped[int] = mapped_column(Integer, nullable=False)

    # total after this change
    new_total_points: Mapped[int] = mapped_column(Integer, nullable=False)

    # old field; keep for compatibility if already used
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_by_admin_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ✅ new UI fields
    activity_name: Mapped[str] = mapped_column(String(120), nullable=False, server_default="Manual Points")
    category: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    activity_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="approved")
    remarks: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    student = relationship("Student", back_populates="point_adjustments")

    __table_args__ = (
        Index("ix_point_adj_student_created", "student_id", "created_at"),
    )