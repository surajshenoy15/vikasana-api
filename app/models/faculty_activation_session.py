from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class FacultyActivationSession(Base):
    __tablename__ = "faculty_activation_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # random session id string
    faculty_id: Mapped[int] = mapped_column(Integer, ForeignKey("faculty.id"), index=True, nullable=False)

    otp_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    otp_attempts: Mapped[int] = mapped_column(Integer, default=0)
    otp_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)