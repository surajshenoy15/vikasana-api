from sqlalchemy import String, Integer, DateTime, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base  # make sure Base is exported in app/models/__init__.py


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("usn", name="uq_students_usn"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    usn: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    branch: Mapped[str] = mapped_column(String(80), nullable=False)

    passout_year: Mapped[int] = mapped_column(Integer, nullable=False)
    admitted_year: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())