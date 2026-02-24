from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.models.events import Event, EventSubmission, EventSubmissionPhoto


# ---------------- ADMIN ----------------
async def create_event(db: AsyncSession, payload):
    event = Event(
        title=payload.title,
        description=payload.description,
        required_photos=payload.required_photos,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


# ---------------- STUDENT ----------------
async def list_active_events(db: AsyncSession):
    q = await db.execute(select(Event).where(Event.is_active == True))
    return q.scalars().all()


async def register_for_event(db: AsyncSession, student_id: int, event_id: int):
    # check event
    q = await db.execute(select(Event).where(Event.id == event_id))
    event = q.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")

    # prevent duplicate
    q = await db.execute(
        select(EventSubmission).where(
            EventSubmission.event_id == event_id,
            EventSubmission.student_id == student_id
        )
    )
    existing = q.scalar_one_or_none()
    if existing:
        return {"submission_id": existing.id, "status": existing.status}

    submission = EventSubmission(
        event_id=event_id,
        student_id=student_id,
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    return {"submission_id": submission.id, "status": submission.status}


async def add_photo(
    db: AsyncSession,
    submission_id: int,
    student_id: int,
    seq_no: int,
    image_url: str,
):
    # validate submission
    q = await db.execute(
        select(EventSubmission).where(
            EventSubmission.id == submission_id,
            EventSubmission.student_id == student_id
        )
    )
    submission = q.scalar_one_or_none()
    if not submission:
        raise HTTPException(404, "Submission not found")

    if submission.status != "in_progress":
        raise HTTPException(400, "Already submitted")

    photo = EventSubmissionPhoto(
        submission_id=submission_id,
        seq_no=seq_no,
        image_url=image_url,
    )

    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return photo


async def final_submit(db: AsyncSession, submission_id: int, student_id: int, description: str):
    q = await db.execute(
        select(EventSubmission).where(
            EventSubmission.id == submission_id,
            EventSubmission.student_id == student_id
        )
    )
    submission = q.scalar_one_or_none()
    if not submission:
        raise HTTPException(404, "Submission not found")

    if submission.status != "in_progress":
        raise HTTPException(400, "Already submitted")

    submission.status = "submitted"
    submission.description = description
    submission.submitted_at = datetime.utcnow()

    await db.commit()
    await db.refresh(submission)

    return submission