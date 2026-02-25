from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean,
    DateTime, ForeignKey, UniqueConstraint,Date, Time
)
from sqlalchemy.orm import relationship
from app.core.database import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    required_photos = Column(Integer, nullable=False, default=3)
    is_active = Column(Boolean, default=True)
    event_date = Column(Date, nullable=True)
    start_time = Column(Time, nullable=True)
    end_time   = Column(DateTime, nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    thumbnail_url = Column(String, nullable=True)

    submissions = relationship("EventSubmission", back_populates="event")


class EventSubmission(Base):
    __tablename__ = "event_submissions"

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"))
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"))

    status = Column(String(30), default="in_progress")  # in_progress/submitted
    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    submitted_at = Column(DateTime(timezone=True), nullable=True)

    event = relationship("Event", back_populates="submissions")
    photos = relationship("EventSubmissionPhoto", back_populates="submission")

    __table_args__ = (
        UniqueConstraint("event_id", "student_id", name="uq_event_student"),
    )


class EventSubmissionPhoto(Base):
    __tablename__ = "event_submission_photos"

    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("event_submissions.id", ondelete="CASCADE"))

    seq_no = Column(Integer, nullable=False)
    image_url = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    submission = relationship("EventSubmission", back_populates="photos")

    __table_args__ = (
        UniqueConstraint("submission_id", "seq_no", name="uq_submission_seq"),
    )