# app/models/activity_type.py

import enum
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, func, Float, Text, Index
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship

from app.core.database import Base


class ActivityTypeStatus(str, enum.Enum):
    APPROVED = "APPROVED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"


class ActivityType(Base):
    __tablename__ = "activity_types"

    id = Column(Integer, primary_key=True, index=True)

    # Identity
    name = Column(String(120), unique=True, nullable=False, index=True)
    description = Column(String(500), nullable=True)

    # Approval workflow for the type itself (optional but you already have it)
    status = Column(
        SAEnum(ActivityTypeStatus, name="activity_type_status_enum", create_type=False),
        nullable=False,
        default=ActivityTypeStatus.APPROVED,
    )

    # Scoring rule: hours_per_unit hours => points_per_unit points, capped by max_points
    hours_per_unit = Column(Float, nullable=False, default=20.0)
    points_per_unit = Column(Integer, nullable=False, default=5)
    max_points = Column(Integer, nullable=False, default=20)

    # Geofence (admin-configured)
    maps_url = Column(Text, nullable=True)
    target_lat = Column(Float, nullable=True)
    target_lng = Column(Float, nullable=True)
    radius_m = Column(Integer, nullable=False, default=500)  # meters

    # Soft enable/disable
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    sessions = relationship("ActivitySession", back_populates="activity_type")

    __table_args__ = (
        Index("ix_activity_types_active_status", "is_active", "status"),
    )