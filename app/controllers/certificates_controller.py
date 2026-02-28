from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.certificate import CertificateCounter, Certificate
from app.models.activity_session import ActivitySession
from app.models.student import Student
from app.models.events import Event


def month_code(dt: datetime) -> str:
    return dt.strftime("%b")  # Jan, Feb, ...


async def next_certificate_no(db: AsyncSession, academic_year: str, dt: datetime) -> str:
    m = month_code(dt)

    stmt = select(CertificateCounter).where(
        CertificateCounter.month_code == m,
        CertificateCounter.academic_year == academic_year,
    ).with_for_update()

    res = await db.execute(stmt)
    counter = res.scalar_one_or_none()

    if counter is None:
        counter = CertificateCounter(month_code=m, academic_year=academic_year, next_seq=1)
        db.add(counter)
        await db.flush()  # assign id

    seq = counter.next_seq
    counter.next_seq = seq + 1
    counter.updated_at = datetime.utcnow()

    # SEQ formatting: 619 or 000619? you can decide.
    # If you want fixed width 3 digits: f"{seq:03d}"
    return f"BG/VF/{m}{seq}/{academic_year}"


async def get_session_full(db: AsyncSession, session_id: int) -> ActivitySession:
    stmt = (
        select(ActivitySession)
        .options(
            selectinload(ActivitySession.student),
            selectinload(ActivitySession.event),
        )
        .where(ActivitySession.id == session_id)
    )
    res = await db.execute(stmt)
    s = res.scalar_one_or_none()
    if not s:
        raise ValueError("Session not found")
    return s