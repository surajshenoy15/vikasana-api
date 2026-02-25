from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    ForeignKey,
    Text,
    DateTime,
    Float,
    func,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class ActivityFaceCheck(Base):
    __tablename__ = "activity_face_checks"

    # --------------------------------------------------
    # Primary Key
    # --------------------------------------------------
    id = Column(Integer, primary_key=True, index=True)

    # --------------------------------------------------
    # Foreign Keys
    # --------------------------------------------------
    student_id = Column(
        Integer,
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    session_id = Column(
        Integer,
        ForeignKey("activity_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    photo_id = Column(
        Integer,
        ForeignKey("activity_photos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --------------------------------------------------
    # Face Verification Results
    # --------------------------------------------------
    matched = Column(Boolean, nullable=False, default=False)

    cosine_score = Column(Float, nullable=True)
    l2_score = Column(Float, nullable=True)
    total_faces = Column(Integer, nullable=True)

    processed_object = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)

    # --------------------------------------------------
    # Metadata
    # --------------------------------------------------
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # --------------------------------------------------
    # Constraints + Indexes
    # --------------------------------------------------
    __table_args__ = (
        # Prevent duplicate verification for same photo in session
        UniqueConstraint(
            "session_id",
            "photo_id",
            name="uq_face_checks_session_photo",
        ),

        # Useful analytics indexes
        Index("ix_face_checks_matched", "matched"),
        Index("ix_face_checks_student_session", "student_id", "session_id"),
    )

    # --------------------------------------------------
    # Relationships
    # --------------------------------------------------
    student = relationship(
        "Student",
        back_populates="face_checks",
        lazy="joined",
    )

    session = relationship(
        "ActivitySession",
        back_populates="face_checks",
        lazy="joined",
    )

    photo = relationship(
        "ActivityPhoto",
        back_populates="face_checks",
        lazy="joined",
    )