# app/models/student_activity_progress.py
from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint, func, Index
from app.core.database import Base

class StudentActivityProgress(Base):
    __tablename__ = "student_activity_progress"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_type_id = Column(Integer, ForeignKey("activity_types.id", ondelete="CASCADE"), nullable=False, index=True)

    total_minutes = Column(Integer, nullable=False, default=0)
    points_awarded = Column(Integer, nullable=False, default=0)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "activity_type_id", name="uq_progress_student_activity"),
        Index("ix_progress_student_activity", "student_id", "activity_type_id"),
    )