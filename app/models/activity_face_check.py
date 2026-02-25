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
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class ActivityFaceCheck(Base):
    __tablename__ = "activity_face_checks"

    id = Column(Integer, primary_key=True, index=True)

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

    matched = Column(Boolean, nullable=False, default=False)

    cosine_score = Column(Float)
    l2_score = Column(Float)
    total_faces = Column(Integer)

    processed_object = Column(Text)  # face-verification bucket object key
    reason = Column(Text)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "photo_id",
            name="uq_face_checks_session_photo",
        ),
    )

    session = relationship("ActivitySession")
    photo = relationship("ActivityPhoto")