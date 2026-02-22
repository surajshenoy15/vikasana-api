from sqlalchemy import Column, Integer, DateTime, ForeignKey, Float, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.core.database import Base

class StudentActivityStats(Base):
    __tablename__ = "student_activity_stats"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_type_id = Column(Integer, ForeignKey("activity_types.id", ondelete="RESTRICT"), nullable=False, index=True)

    total_verified_hours = Column(Float, nullable=False, default=0.0)
    points_awarded = Column(Integer, nullable=False, default=0)

    completed_at = Column(DateTime(timezone=True), nullable=True)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    student = relationship("Student", back_populates="activity_stats")
    activity_type = relationship("ActivityType")

    __table_args__ = (
        UniqueConstraint("student_id", "activity_type_id", name="uq_student_activity_type"),
    )