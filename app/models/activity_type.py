from sqlalchemy import Column, Integer, String, DateTime, Enum, Boolean, func
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base

class ActivityTypeStatus(str, enum.Enum):
    APPROVED = "APPROVED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"

class ActivityType(Base):
    __tablename__ = "activity_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), unique=True, nullable=False, index=True)
    description = Column(String(500), nullable=True)

    status = Column(Enum(ActivityTypeStatus), nullable=False, default=ActivityTypeStatus.APPROVED)

    # Scoring rule: 20 hours = 5 points (your instruction)
    hours_per_unit = Column(Integer, nullable=False, default=20)
    points_per_unit = Column(Integer, nullable=False, default=5)
    max_points = Column(Integer, nullable=False, default=20)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    sessions = relationship("ActivitySession", back_populates="activity_type")