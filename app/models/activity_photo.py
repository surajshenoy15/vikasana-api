from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, func, Boolean, Index
from sqlalchemy.orm import relationship

from app.core.database import Base

class ActivityPhoto(Base):
    __tablename__ = "activity_photos"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("activity_sessions.id", ondelete="CASCADE"), nullable=False, index=True)

    image_url = Column(String(500), nullable=False)      # store in MinIO/S3/etc
    sha256 = Column(String(64), nullable=True, index=True)

    captured_at = Column(DateTime(timezone=True), nullable=False, index=True)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)

    # basic verification flags
    is_duplicate = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    session = relationship("ActivitySession", back_populates="photos")

Index("ix_activity_photos_session_time", ActivityPhoto.session_id, ActivityPhoto.captured_at)