from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Float, func, Index
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base

class ActivitySessionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    FLAGGED = "FLAGGED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

class ActivitySession(Base):
    __tablename__ = "activity_sessions"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_type_id = Column(Integer, ForeignKey("activity_types.id", ondelete="RESTRICT"), nullable=False, index=True)

    activity_name = Column(String(200), nullable=False)
    description = Column(String(800), nullable=True)

    session_code = Column(String(32), unique=True, nullable=False, index=True)

    started_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    submitted_at = Column(DateTime(timezone=True), nullable=True)

    status = Column(Enum(ActivitySessionStatus), nullable=False, default=ActivitySessionStatus.DRAFT)

    # computed on submit
    duration_hours = Column(Float, nullable=True)

    # if flagged
    flag_reason = Column(String(500), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    student = relationship("Student", back_populates="activity_sessions")
    activity_type = relationship("ActivityType", back_populates="sessions")
    photos = relationship("ActivityPhoto", back_populates="session", cascade="all, delete-orphan")

Index("ix_activity_sessions_student_type_day", ActivitySession.student_id, ActivitySession.activity_type_id, ActivitySession.started_at)