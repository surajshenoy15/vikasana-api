from enum import Enum
from typing import List

from sqlalchemy import (
    String,
    Integer,
    DateTime,
    func,
    UniqueConstraint,
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


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
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # ✅ College isolation
    college: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    usn: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    branch: Mapped[str] = mapped_column(String(80), nullable=False)

    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    student_type: Mapped[StudentType] = mapped_column(
        SAEnum(StudentType, name="student_type_enum"),
        nullable=False,
        server_default=StudentType.REGULAR.value,
    )

    # ✅ NEW: Total points required for course completion
    # REGULAR = 100
    # DIPLOMA = 60
    required_total_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default="100",
    )

    # ✅ NEW: Track total points earned (fast dashboard lookup)
    total_points_earned: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    passout_year: Mapped[int] = mapped_column(Integer, nullable=False)
    admitted_year: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # --------------------------------------------------
    # RELATIONSHIPS (Activity Tracker)
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