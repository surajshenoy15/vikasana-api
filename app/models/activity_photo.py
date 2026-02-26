from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    DateTime,
    Float,
    Text,
    UniqueConstraint,
    func,
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

    student_id = Column(
        Integer,
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    seq_no = Column(Integer, nullable=False, index=True)

    image_url = Column(Text, nullable=False)

    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)

    captured_at = Column(DateTime(timezone=True), nullable=True)

    sha256 = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("session_id", "seq_no", name="uq_activity_photos_session_seq"),
        Index("ix_activity_photos_student_session", "student_id", "session_id"),
    )

    # Relationships (string refs to avoid circular imports)
    session = relationship("ActivitySession", back_populates="photos")
    student = relationship("Student", back_populates="activity_photos")

    face_checks = relationship(
        "ActivityFaceCheck",
        back_populates="photo",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )