# app/controllers/events_controller.py
from __future__ import annotations

from datetime import datetime, date as date_type, time as time_type, timezone
from zoneinfo import ZoneInfo
from typing import Iterable

from fastapi import HTTPException
from sqlalchemy import select, func, delete as sql_delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import Event, EventSubmission, EventSubmissionPhoto
from app.models.student import Student

# ✅ Activity tracking
from app.models.activity_session import ActivitySession, ActivitySessionStatus
from app.models.activity_type import ActivityType

# ✅ Event ↔ ActivityType mapping
from app.models.event_activity_type import EventActivityType

# ✅ Certificates
from app.models.certificate import Certificate, CertificateCounter
from app.core.cert_sign import sign_cert
from app.core.cert_pdf import build_certificate_pdf
from app.core.config import settings

# ✅ MinIO upload + presign
from app.core.cert_storage import upload_certificate_pdf_bytes, presign_certificate_download_url

# ✅ Thumbnail presign
from app.core.event_thumbnail_storage import generate_event_thumbnail_presigned_put

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
IST = ZoneInfo("Asia/Kolkata")


# =========================================================
# ---------------------- TIME HELPERS ----------------------
# =========================================================

def _now_ist_naive() -> datetime:
    # IST clock-time, tzinfo removed because your Event.end_time is stored as naive
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
            if now_dt > end_val.replace(tzinfo=None):
                raise HTTPException(status_code=403, detail="Event has ended.")
        elif isinstance(end_val, time_type):
            if now_time > end_val:
                raise HTTPException(status_code=403, detail="Event has ended.")


def _event_window_ist_naive(event: Event) -> tuple[datetime, datetime]:
    """
    Returns (start_dt, end_dt) as naive datetime representing IST clock time.
    end_time is stored as naive datetime in DB (TIMESTAMP WITHOUT TZ).
    """
    if not getattr(event, "event_date", None):
        raise HTTPException(status_code=400, detail="Event date not configured.")

    start_t = getattr(event, "start_time", None) or time_type(0, 0)
    start_dt = datetime.combine(event.event_date, start_t).replace(tzinfo=None)

    end_val = getattr(event, "end_time", None)
    if not end_val:
        end_dt = datetime.combine(event.event_date, time_type(23, 59, 59)).replace(tzinfo=None)
    else:
        if isinstance(end_val, datetime):
            end_dt = end_val.replace(tzinfo=None)
        elif isinstance(end_val, time_type):
            end_dt = _combine_event_datetime_ist_naive(event.event_date, end_val)
        else:
            end_dt = datetime.combine(event.event_date, time_type(23, 59, 59)).replace(tzinfo=None)

    return start_dt, end_dt


# ✅ NEW: convert IST-naive -> UTC-aware for comparing with ActivitySession timestamps (usually UTC aware)
def _ist_naive_to_utc_aware(dt_naive_ist: datetime) -> datetime:
    """
    Treat dt_naive_ist as IST clock time and convert to UTC aware.
    Example: 2026-02-28 10:00 (IST naive) -> 2026-02-28 04:30+00:00
    """
    return dt_naive_ist.replace(tzinfo=IST).astimezone(timezone.utc)


# ✅ NEW: event window in UTC aware
def _event_window_utc(event: Event) -> tuple[datetime, datetime]:
    start_ist_naive, end_ist_naive = _event_window_ist_naive(event)
    return _ist_naive_to_utc_aware(start_ist_naive), _ist_naive_to_utc_aware(end_ist_naive)


def _event_out_dict(event: Event) -> dict:
    """
    ✅ EventOut schema expects end_time as Optional[time].
    But DB stores end_time as naive datetime.
    So convert datetime -> time for API response.
    """
    end_val = getattr(event, "end_time", None)
    end_time = end_val.time() if isinstance(end_val, datetime) else end_val

    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "required_photos": event.required_photos,
        "is_active": bool(getattr(event, "is_active", True)),
        "event_date": event.event_date,
        "start_time": event.start_time,
        "end_time": end_time,
        "venue_name": getattr(event, "venue_name", None),
        "maps_url": getattr(event, "maps_url", None),
        "thumbnail_url": getattr(event, "thumbnail_url", None),
    }


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
    Uses row lock to avoid duplicate seq in concurrent generations.
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
    counter.updated_at = datetime.now(timezone.utc)

    return f"BG/VF/{m}{seq}/{academic_year}"


async def _get_event_activity_type_ids(db: AsyncSession, event_id: int) -> list[int]:
    aq = await db.execute(
        select(EventActivityType.activity_type_id).where(EventActivityType.event_id == event_id)
    )
    return [int(r[0]) for r in aq.all() if r and r[0] is not None]


async def _eligible_students_from_sessions(
    db: AsyncSession,
    event: Event,
    activity_type_ids: list[int],
) -> list[int]:
    """
    ✅ Students eligible for auto-approval:
    - Have ActivitySession APPROVED (face verified)
    - Session.activity_type_id in event's mapped activity_type_ids
    - Session.started_at within event window

    ✅ IMPORTANT FIX:
    ActivitySession.started_at is usually UTC-aware.
    So compare against event window converted to UTC-aware.
    """
    if not activity_type_ids:
        return []

    start_utc, end_utc = _event_window_utc(event)

    q = await db.execute(
        select(func.distinct(ActivitySession.student_id)).where(
            ActivitySession.status == ActivitySessionStatus.APPROVED,
            ActivitySession.activity_type_id.in_(activity_type_ids),
            ActivitySession.started_at >= start_utc,
            ActivitySession.started_at <= end_utc,
        )
    )
    return [int(r[0]) for r in q.all() if r and r[0] is not None]


async def auto_approve_event_from_sessions(db: AsyncSession, event_id: int) -> dict:
    """
    ✅ MAIN BUTTON LOGIC (Top approve):
    - Finds students with APPROVED face sessions within event window
    - Upserts EventSubmission => status=approved, sets submitted_at+approved_at
    - Generates certificates for them

    Returns:
      {event_id, eligible_students, submissions_approved, certificates_issued}
    """
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    activity_type_ids = await _get_event_activity_type_ids(db, event_id)
    if not activity_type_ids:
        raise HTTPException(status_code=400, detail="No activity types mapped to this event")

    eligible_student_ids = await _eligible_students_from_sessions(db, event, activity_type_ids)
    if not eligible_student_ids:
        return {
            "event_id": event_id,
            "eligible_students": 0,
            "submissions_approved": 0,
            "certificates_issued": 0,
        }

    now_utc = datetime.now(timezone.utc)

    # Upsert submissions
    submissions_approved = 0
    for sid in eligible_student_ids:
        res = await db.execute(
            select(EventSubmission).where(
                EventSubmission.event_id == event_id,
                EventSubmission.student_id == sid,
            )
        )
        sub = res.scalar_one_or_none()

        if sub is None:
            sub = EventSubmission(
                event_id=event_id,
                student_id=sid,
                status="approved",
            )
            if hasattr(sub, "submitted_at"):
                sub.submitted_at = now_utc
            if hasattr(sub, "approved_at"):
                sub.approved_at = now_utc
            db.add(sub)
            submissions_approved += 1
        else:
            if sub.status != "approved":
                sub.status = "approved"
                if hasattr(sub, "submitted_at") and sub.submitted_at is None:
                    sub.submitted_at = now_utc
                if hasattr(sub, "approved_at"):
                    sub.approved_at = now_utc
                submissions_approved += 1

    await db.commit()

    # Generate certificates (only for APPROVED submissions)
    issued = await _issue_certificates_for_event(db, event)

    return {
        "event_id": event_id,
        "eligible_students": len(eligible_student_ids),
        "submissions_approved": submissions_approved,
        "certificates_issued": issued,
    }


async def _issue_certificates_for_event(db: AsyncSession, event: Event) -> int:
    """
    ✅ Only APPROVED event_submissions (auto-approved or manual).
    ✅ 1 certificate per activity_type configured for event.
    ✅ Uses ActivitySession to compute hours inside event window.
    ✅ Skips if hours == 0 (no certificate).

    ✅ IMPORTANT FIX:
    Use event window in UTC-aware when filtering ActivitySession.started_at.
    """
    # approved participants
    q = await db.execute(
        select(EventSubmission).where(
            EventSubmission.event_id == event.id,
            func.lower(EventSubmission.status) == "approved",
        )
    )
    submissions = q.scalars().all()
    if not submissions:
        return 0

    # activity types attached to this event
    activity_type_ids = await _get_event_activity_type_ids(db, event.id)
    if not activity_type_ids:
        return 0

    start_utc, end_utc = _event_window_utc(event)

    now_utc = datetime.now(timezone.utc)
    now_ist = _now_ist_naive()
    academic_year = _academic_year_from_date(now_ist)

    issued = 0

    for sub in submissions:
        # Fetch student
        sq = await db.execute(select(Student).where(Student.id == sub.student_id))
        student = sq.scalar_one_or_none()
        student_name = getattr(student, "name", None) or getattr(student, "student_name", None) or "Student"
        usn = getattr(student, "usn", None) or ""

        for at_id in activity_type_ids:
            # Skip if already issued
            ex = await db.execute(
                select(Certificate).where(
                    Certificate.submission_id == sub.id,
                    Certificate.activity_type_id == at_id,
                )
            )
            if ex.scalar_one_or_none():
                continue

            # hours in event window for that type (only APPROVED activity sessions)
            hrs_q = await db.execute(
                select(func.coalesce(func.sum(ActivitySession.duration_hours), 0.0)).where(
                    ActivitySession.student_id == sub.student_id,
                    ActivitySession.activity_type_id == at_id,
                    ActivitySession.started_at >= start_utc,
                    ActivitySession.started_at <= end_utc,
                    ActivitySession.status == ActivitySessionStatus.APPROVED,
                )
            )
            hours = float(hrs_q.scalar() or 0.0)

            # ✅ If no hours, don't issue certificate
            if hours <= 0:
                continue

            # activity type name
            atq = await db.execute(select(ActivityType).where(ActivityType.id == at_id))
            at = atq.scalar_one_or_none()
            activity_type_name = (getattr(at, "name", None) or "").strip() or "Social Activity"

            cert_no = await _next_certificate_no(db, academic_year, now_ist)

            cert = Certificate(
                certificate_no=cert_no,
                submission_id=sub.id,
                student_id=sub.student_id,
                event_id=event.id,
                activity_type_id=at_id,
                issued_at=now_utc,
            )
            db.add(cert)
            await db.flush()  # cert.id available

            sig = sign_cert(cert.id)
            verify_url = f"{settings.PUBLIC_BASE_URL}/api/public/certificates/verify?cert_id={cert.id}&sig={sig}"

            pdf_bytes = build_certificate_pdf(
                certificate_no=cert_no,
                issue_date=now_ist.strftime("%d.%m.%Y"),
                student_name=student_name,
                usn=usn,
                activity_type=activity_type_name,
                verify_url=verify_url,
            )

            object_key = upload_certificate_pdf_bytes(cert.id, pdf_bytes)
            cert.pdf_path = object_key

            issued += 1

    await db.commit()
    return issued


# =========================================================
# ---------------------- CERT LIST (STUDENT) ----------------
# =========================================================

async def list_student_event_certificates(db: AsyncSession, student_id: int, event_id: int) -> list[dict]:
    q = await db.execute(
        select(Certificate)
        .where(
            Certificate.student_id == student_id,
            Certificate.event_id == event_id,
            Certificate.revoked_at.is_(None),
        )
        .order_by(Certificate.issued_at.desc(), Certificate.id.desc())
    )
    certs = q.scalars().all()

    out = []
    for cert in certs:
        pdf_url = None
        if cert.pdf_path:
            try:
                pdf_url = presign_certificate_download_url(cert.pdf_path, expires_in=3600)
            except Exception:
                pdf_url = None

        out.append({
            "id": cert.id,
            "certificate_no": cert.certificate_no,
            "issued_at": cert.issued_at,
            "event_id": cert.event_id,
            "submission_id": cert.submission_id,
            "activity_type_id": getattr(cert, "activity_type_id", None),
            "pdf_url": pdf_url,
        })
    return out


async def regenerate_event_certificates(db: AsyncSession, event_id: int) -> dict:
    """
    Manual regen: generates missing certs for all APPROVED submissions.
    (If you use auto_approve, call that first, then regen is optional.)
    """
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    issued = await _issue_certificates_for_event(db, event)
    return {"event_id": event_id, "issued": issued}


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
    Stores end_time as NAIVE datetime (IST clock) because DB is TIMESTAMP WITHOUT TZ.
    Also stores selected activity types into event_activity_types table.

    ✅ Supports BOTH:
      - payload.activity_type_ids: [1,2,3]
      - payload.activity_list: ["Tree Plantation", "Blood Donation"]
    ✅ Accepts time fields from payload: start_time/end_time OR event_time/time
    """
    event_date = getattr(payload, "event_date", None) or getattr(payload, "date", None)
    start_time = getattr(payload, "start_time", None) or getattr(payload, "event_time", None) or getattr(payload, "time", None)
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
    maps_url = getattr(payload, "maps_url", None) or getattr(payload, "venue_maps_url", None)

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

    # ─────────────────────────────────────────────────────
    # ✅ Save selected activity types for this event
    # Supports ids and/or names
    # ─────────────────────────────────────────────────────

    ids: list[int] = []
    raw_ids = getattr(payload, "activity_type_ids", None) or []
    for x in raw_ids:
        try:
            ids.append(int(x))
        except Exception:
            pass

    # Fallback: activity_list contains names from frontend
    if not ids:
        names = [str(x).strip() for x in (getattr(payload, "activity_list", None) or []) if str(x).strip()]
        if names:
            rq = await db.execute(select(ActivityType.id).where(ActivityType.name.in_(names)))
            ids = [int(r[0]) for r in rq.all()]

    for at_id in sorted(set(ids)):
        db.add(EventActivityType(event_id=event.id, activity_type_id=at_id))

    await db.commit()
    await db.refresh(event)

    return _event_out_dict(event)


async def end_event(db: AsyncSession, event_id: int):
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event.is_active = False

    # Expire only unfinished
    await db.execute(
        update(EventSubmission)
        .where(
            EventSubmission.event_id == event_id,
            EventSubmission.status.in_(["in_progress", "draft"]),
        )
        .values(status="expired")
    )

    await db.commit()
    await db.refresh(event)
    return event


async def delete_event(db: AsyncSession, event_id: int) -> None:
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    await db.execute(sql_delete(EventActivityType).where(EventActivityType.event_id == event_id))

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
    """
    Manual single approve (still works)
    NOTE: certificates are better generated via auto_approve_event_from_sessions / regenerate.
    """
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
    events = q.scalars().all()
    return [_event_out_dict(e) for e in events]


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