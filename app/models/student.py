from __future__ import annotations

from enum import Enum
from typing import List, Optional, TYPE_CHECKING
from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    DateTime,
    func,
    UniqueConstraint,
    Enum as SAEnum,
    Boolean,
    Index,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.faculty import Faculty
    from app.models.activity_session import ActivitySession
    from app.models.student_activity_stats import StudentActivityStats
    from app.models.student_face_embedding import StudentFaceEmbedding
    from app.models.activity_face_check import ActivityFaceCheck
    from app.models.activity_photo import ActivityPhoto


# --------------------------------------------------
# ENUM
# --------------------------------------------------

class StudentType(str, Enum):
    REGULAR = "REGULAR"
    DIPLOMA = "DIPLOMA"


# --------------------------------------------------
# MODEL
# --------------------------------------------------

class Student(Base):
    __tablename__ = "students"

    __table_args__ = (
        UniqueConstraint("usn", name="uq_students_usn"),
        UniqueConstraint("email", name="uq_students_email"),
        Index("ix_students_college_branch", "college", "branch"),
    )

    # --------------------------------------------------
    # PRIMARY KEY
    # --------------------------------------------------

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # --------------------------------------------------
    # BASIC DETAILS
    # --------------------------------------------------

    college: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    usn: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    branch: Mapped[str] = mapped_column(String(80), nullable=False)

    email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    student_type: Mapped[StudentType] = mapped_column(
        SAEnum(StudentType, name="student_type_enum"),
        nullable=False,
        server_default=StudentType.REGULAR.value,
    )

    # --------------------------------------------------
    # POINTS SYSTEM
    # --------------------------------------------------

    required_total_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default="100",
    )

    total_points_earned: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # --------------------------------------------------
    # FACE ENROLLMENT SYSTEM
    # --------------------------------------------------

    face_enrolled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )

    face_enrolled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # --------------------------------------------------
    # ACADEMIC YEARS
    # --------------------------------------------------

    passout_year: Mapped[int] = mapped_column(Integer, nullable=False)
    admitted_year: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # --------------------------------------------------
    # CREATED BY (FACULTY)
    # --------------------------------------------------

    created_by_faculty_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("faculty.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_by_faculty: Mapped[Optional["Faculty"]] = relationship(
        "Faculty",
        back_populates="students_created",
        foreign_keys=[created_by_faculty_id],
        lazy="joined",
    )

    # --------------------------------------------------
    # RELATIONSHIPS
    # --------------------------------------------------

    activity_sessions: Mapped[List["ActivitySession"]] = relationship(
        "ActivitySession",
        back_populates="student",
        cascade="all, delete-orphan",
    )

    activity_stats: Mapped[List["StudentActivityStats"]] = relationship(
        "StudentActivityStats",
        back_populates="student",
        cascade="all, delete-orphan",
    )

    face_embeddings: Mapped[List["StudentFaceEmbedding"]] = relationship(
        "StudentFaceEmbedding",
        back_populates="student",
        cascade="all, delete-orphan",
    )

    face_checks: Mapped[List["ActivityFaceCheck"]] = relationship(
        "ActivityFaceCheck",
        back_populates="student",
        cascade="all, delete-orphan",
    )

    activity_photos: Mapped[List["ActivityPhoto"]] = relationship(
        "ActivityPhoto",
        back_populates="student",
        cascade="all, delete-orphan",
    )