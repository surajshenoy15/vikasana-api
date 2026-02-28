# app/controllers/events_controller.py
from __future__ import annotations

import os
from datetime import datetime, date as date_type, time as time_type, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select, func, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import Event, EventSubmission, EventSubmissionPhoto
from app.models.student import Student  # ✅ make sure this exists

# ✅ NEW (Certificates)
from app.models.certificate import Certificate, CertificateCounter
from app.core.cert_sign import sign_cert
from app.core.cert_pdf import build_certificate_pdf
from app.core.config import settings

from app.core.event_thumbnail_storage import generate_event_thumbnail_presigned_put

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

IST = ZoneInfo("Asia/Kolkata")


# =========================================================
# ---------------------- TIME HELPERS ----------------------
# =========================================================

def _now_ist_naive() -> datetime:
    return datetime.now(IST).replace(tzinfo=None)


def _combine_event_datetime_ist_naive(event_date: date_type, t: time_type) -> datetime:
    return datetime.combine(event_date, t).replace(tzinfo=None)


def _ensure_event_window(event: Event) -> None:
    now_dt = _now_ist_naive()
    now_date = now_dt.date()
    now_time = now_dt.time()

    if not getattr(event, "is_active", True):
        raise HTTPException(status_code=403, detail="Event has ended.")

    if not getattr(event, "event_date", None):
        raise HTTPException(status_code=400, detail="Event date not configured.")

    if event.event_date != now_date:
        raise HTTPException(status_code=403, detail="Event is not available today.")

    if getattr(event, "start_time", None) and now_time < event.start_time:
        raise HTTPException(status_code=403, detail="Event has not started yet.")

    end_val = getattr(event, "end_time", None)
    if end_val:
        if isinstance(end_val, datetime):
            if now_dt > end_val:
                raise HTTPException(status_code=403, detail="Event has ended.")
        elif isinstance(end_val, time_type):
            if now_time > end_val:
                raise HTTPException(status_code=403, detail="Event has ended.")


# =========================================================
# ---------------------- CERT HELPERS ----------------------
# =========================================================

def _month_code(dt: datetime) -> str:
    return dt.strftime("%b")  # Jan, Feb...


def _academic_year_from_date(dt: datetime) -> str:
    """
    Academic year in India typically: Jun -> May
    Example:
      Feb 2025 => 2024-25
      Jul 2025 => 2025-26
    """
    y = dt.year
    m = dt.month
    start_year = y if m >= 6 else (y - 1)
    end_year_short = str(start_year + 1)[-2:]
    return f"{start_year}-{end_year_short}"


async def _next_certificate_no(db: AsyncSession, academic_year: str, dt: datetime) -> str:
    """
    BG/VF/{MONTH_CODE}{SEQ}/{ACADEMIC_YEAR}
    Example: BG/VF/Jan619/2024-25
    Uses row lock to avoid duplicate seq in concurrent end_event calls.
    """
    m = _month_code(dt)

    stmt = (
        select(CertificateCounter)
        .where(
            CertificateCounter.month_code == m,
            CertificateCounter.academic_year == academic_year,
        )
        .with_for_update()
    )
    res = await db.execute(stmt)
    counter = res.scalar_one_or_none()

    if counter is None:
        counter = CertificateCounter(month_code=m, academic_year=academic_year, next_seq=1)
        db.add(counter)
        await db.flush()

    seq = int(counter.next_seq or 1)
    counter.next_seq = seq + 1
    counter.updated_at = datetime.utcnow()

    return f"BG/VF/{m}{seq}/{academic_year}"


async def _issue_certificates_for_event(db: AsyncSession, event: Event) -> int:
    """
    Generates certificates for all APPROVED submissions of an event.
    Saves PDF into storage/certificates/ and stores path in DB.
    """
    # Get all approved submissions for this event
    q = await db.execute(
        select(EventSubmission).where(
            EventSubmission.event_id == event.id,
            EventSubmission.status == "approved",
        )
    )
    submissions = q.scalars().all()
    if not submissions:
        return 0

    now_utc = datetime.now(timezone.utc)
    academic_year = _academic_year_from_date(_now_ist_naive())

    os.makedirs("storage/certificates", exist_ok=True)

    issued = 0
    for sub in submissions:
        # Skip if already issued for this submission
        exists = await db.execute(select(Certificate).where(Certificate.submission_id == sub.id))
        if exists.scalar_one_or_none():
            continue

        cert_no = await _next_certificate_no(db, academic_year, _now_ist_naive())

        # Fetch student
        sq = await db.execute(select(Student).where(Student.id == sub.student_id))
        student = sq.scalar_one_or_none()

        student_name = getattr(student, "name", None) or getattr(student, "student_name", None) or "Student"
        usn = getattr(student, "usn", None) or ""

        activity_type = getattr(event, "title", None) or "Social Activity"

        # Optional: if you store points/hours on submission, use them; else keep 0 for now
        hours = float(getattr(sub, "total_hours", 0) or 0)
        points = int(getattr(sub, "points_awarded", 0) or 0)

        cert = Certificate(
            certificate_no=cert_no,
            submission_id=sub.id,     # ✅ IMPORTANT: your Certificate model must have this FK
            student_id=sub.student_id,
            event_id=event.id,
            issued_at=now_utc,
        )
        db.add(cert)
        await db.flush()  # cert.id available

        sig = sign_cert(cert.id)
        verify_url = f"{settings.PUBLIC_BASE_URL}/api/public/certificates/verify?cert_id={cert.id}&sig={sig}"

        pdf_bytes = build_certificate_pdf(
            certificate_no=cert_no,
            issue_date=_now_ist_naive().strftime("%d.%m.%Y"),
            student_name=student_name,
            usn=usn,
            activity_type=activity_type,
            hours=hours,
            points=points,
            verify_url=verify_url,
        )

        path = f"storage/certificates/cert_{cert.id}.pdf"
        with open(path, "wb") as f:
            f.write(pdf_bytes)

        cert.pdf_path = path
        issued += 1

    return issued


# =========================================================
# ---------------------- THUMBNAIL -------------------------
# =========================================================

async def get_event_thumbnail_upload_url(admin_id: int, filename: str, content_type: str):
    return await generate_event_thumbnail_presigned_put(
        filename=filename,
        content_type=content_type,
        admin_id=admin_id,
    )


# =========================================================
# ---------------------- ADMIN -----------------------------
# =========================================================

async def create_event(db: AsyncSession, payload):
    """
    Handles payload.end_time being either:
      - time (preferred from UI), OR
      - datetime (rare)

    We store end_time as NAIVE datetime (IST clock) because DB is TIMESTAMP WITHOUT TZ.
    """
    event_date = getattr(payload, "event_date", None)
    start_time = getattr(payload, "start_time", None)
    end_time_raw = getattr(payload, "end_time", None)

    end_time_dt = None
    if end_time_raw:
        if isinstance(end_time_raw, datetime):
            end_time_dt = end_time_raw.replace(tzinfo=None)
        elif isinstance(end_time_raw, time_type):
            if not event_date:
                raise HTTPException(status_code=422, detail="event_date is required when end_time is a time value")
            end_time_dt = _combine_event_datetime_ist_naive(event_date, end_time_raw)

    venue_name = getattr(payload, "venue_name", None)
    maps_url = getattr(payload, "maps_url", None)

    event = Event(
        title=payload.title,
        description=payload.description,
        required_photos=int(payload.required_photos or 3),
        is_active=True,
        event_date=event_date,
        start_time=start_time,
        end_time=end_time_dt,
        thumbnail_url=getattr(payload, "thumbnail_url", None),
        venue_name=venue_name,
        maps_url=maps_url,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def end_event(db: AsyncSession, event_id: int) -> Event:
    """
    ✅ UPDATED:
    - Ends event
    - Generates certificates for all approved submissions
    """
    q = await db.execute(select(Event).where(Event.id == event_id))
    event = q.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if getattr(event, "is_active", True) is False:
        return event

    event.is_active = False
    if hasattr(event, "end_time"):
        event.end_time = _now_ist_naive()

    # ✅ Issue certificates (in same transaction)
    # If anything fails, you will see error & can retry end_event safely (it skips already issued)
    try:
        issued_count = await _issue_certificates_for_event(db, event)
        # You can store issued_count somewhere if you want (optional)
        # print("Issued certs:", issued_count)
    except Exception as e:
        # If you prefer: allow event to end even if cert fails -> commit first then issue.
        # For now, we stop and show error so you can fix quickly.
        raise HTTPException(status_code=500, detail=f"Certificate generation failed: {str(e)}")

    await db.commit()
    await db.refresh(event)
    return event


async def delete_event(db: AsyncSession, event_id: int) -> None:
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    sub_result = await db.execute(
        select(EventSubmission.id).where(EventSubmission.event_id == event_id)
    )
    submission_ids = [row[0] for row in sub_result.fetchall()]

    if submission_ids:
        await db.execute(
            sql_delete(EventSubmissionPhoto).where(
                EventSubmissionPhoto.submission_id.in_(submission_ids)
            )
        )
        await db.execute(
            sql_delete(EventSubmission).where(EventSubmission.event_id == event_id)
        )

    await db.execute(sql_delete(Event).where(Event.id == event_id))
    await db.commit()


async def list_event_submissions(db: AsyncSession, event_id: int):
    q = await db.execute(select(EventSubmission).where(EventSubmission.event_id == event_id))
    return q.scalars().all()


async def approve_submission(db: AsyncSession, submission_id: int):
    q = await db.execute(select(EventSubmission).where(EventSubmission.id == submission_id))
    submission = q.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status != "submitted":
        raise HTTPException(status_code=400, detail="Only submitted items can be approved")

    submission.status = "approved"
    if hasattr(submission, "approved_at"):
        submission.approved_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(submission)
    return submission


async def reject_submission(db: AsyncSession, submission_id: int, reason: str):
    q = await db.execute(select(EventSubmission).where(EventSubmission.id == submission_id))
    submission = q.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status != "submitted":
        raise HTTPException(status_code=400, detail="Only submitted items can be rejected")

    submission.status = "rejected"
    if hasattr(submission, "rejection_reason"):
        submission.rejection_reason = reason

    await db.commit()
    await db.refresh(submission)
    return submission


# =========================================================
# ---------------------- STUDENT ---------------------------
# =========================================================

async def list_active_events(db: AsyncSession):
    today_ist = _now_ist_naive().date()

    q = await db.execute(
        select(Event).where(
            Event.event_date != None,
            Event.event_date >= today_ist
        ).order_by(
            Event.event_date.asc(),
            Event.start_time.asc().nulls_last(),
            Event.id.desc()
        )
    )
    return q.scalars().all()


async def register_for_event(db: AsyncSession, student_id: int, event_id: int):
    q = await db.execute(select(Event).where(Event.id == event_id))
    event = q.scalar_one_or_none()

    if not event or not getattr(event, "is_active", True):
        raise HTTPException(status_code=404, detail="Event not found")

    _ensure_event_window(event)

    q = await db.execute(
        select(EventSubmission).where(
            EventSubmission.event_id == event_id,
            EventSubmission.student_id == student_id,
        )
    )
    existing = q.scalar_one_or_none()
    if existing:
        return {"submission_id": existing.id, "status": existing.status}

    submission = EventSubmission(
        event_id=event_id,
        student_id=student_id,
        status="in_progress",
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    return {"submission_id": submission.id, "status": submission.status}


# =========================================================
# ---------------------- PHOTO UPLOAD ----------------------
# =========================================================

async def add_photo(
    db: AsyncSession,
    submission_id: int,
    student_id: int,
    seq_no: int,
    image_url: str,
):
    q = await db.execute(
        select(EventSubmission).where(
            EventSubmission.id == submission_id,
            EventSubmission.student_id == student_id
        )
    )
    submission = q.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status != "in_progress":
        raise HTTPException(status_code=400, detail="Submission already completed")

    evq = await db.execute(select(Event).where(Event.id == submission.event_id))
    event = evq.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    _ensure_event_window(event)

    required_photos = int(getattr(event, "required_photos", 3) or 3)
    if seq_no < 1 or seq_no > required_photos:
        raise HTTPException(status_code=400, detail=f"seq_no must be between 1 and {required_photos}")

    q = await db.execute(
        select(EventSubmissionPhoto).where(
            EventSubmissionPhoto.submission_id == submission_id,
            EventSubmissionPhoto.seq_no == seq_no
        )
    )
    existing_photo = q.scalar_one_or_none()

    if existing_photo:
        existing_photo.image_url = image_url
        await db.commit()
        await db.refresh(existing_photo)
        return existing_photo

    photo = EventSubmissionPhoto(
        submission_id=submission_id,
        seq_no=seq_no,
        image_url=image_url,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return photo


# =========================================================
# ---------------------- FINAL SUBMIT ----------------------
# =========================================================

async def final_submit(db: AsyncSession, submission_id: int, student_id: int, description: str):
    q = await db.execute(
        select(EventSubmission).where(
            EventSubmission.id == submission_id,
            EventSubmission.student_id == student_id
        )
    )
    submission = q.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status != "in_progress":
        raise HTTPException(status_code=400, detail="Already submitted")

    evq = await db.execute(select(Event).where(Event.id == submission.event_id))
    event = evq.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    _ensure_event_window(event)

    required_photos = int(getattr(event, "required_photos", 3) or 3)

    q = await db.execute(
        select(func.count(EventSubmissionPhoto.id)).where(
            EventSubmissionPhoto.submission_id == submission_id
        )
    )
    uploaded_photos = int(q.scalar() or 0)

    if uploaded_photos < required_photos:
        raise HTTPException(
            status_code=400,
            detail=(
                f"You must upload at least {required_photos} photos before submitting. "
                f"Currently uploaded: {uploaded_photos}"
            )
        )

    submission.status = "submitted"
    submission.description = description
    if hasattr(submission, "submitted_at"):
        submission.submitted_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(submission)
    return submission