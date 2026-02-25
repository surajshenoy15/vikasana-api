from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Float,
    func,
    Boolean,
    Index,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class ActivityPhoto(Base):
    __tablename__ = "activity_photos"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(
        Integer,
        ForeignKey("activity_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ✅ IMPORTANT: store student_id directly to avoid NULL student_id inserts in face checks
    student_id = Column(
        Integer,
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # store in MinIO/S3/etc
    image_url = Column(String(500), nullable=False)

    sha256 = Column(String(64), nullable=True, index=True)

    captured_at = Column(DateTime(timezone=True), nullable=False, index=True)

    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)

    # basic verification flags
    is_duplicate = Column(Boolean, nullable=False, default=False, server_default="false")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # -------------------------
    # RELATIONSHIPS
    # -------------------------
    session = relationship("ActivitySession", back_populates="photos", lazy="joined")

    # optional but useful
    student = relationship("Student", lazy="joined")

    # ✅ Needed for ActivityFaceCheck.photo relationship
    face_checks = relationship(
        "ActivityFaceCheck",
        back_populates="photo",
        cascade="all, delete-orphan",
    )


Index("ix_activity_photos_session_time", ActivityPhoto.session_id, ActivityPhoto.captured_at)
Index("ix_activity_photos_student_time", ActivityPhoto.student_id, ActivityPhoto.captured_at)