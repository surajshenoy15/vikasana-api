# app/controllers/events_controller.py
from __future__ import annotations

from datetime import datetime, date as date_type, time as time_type, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Optional
from urllib.parse import quote
from sqlalchemy import delete
from typing import List
from fastapi import HTTPException
from sqlalchemy import select, func, delete as sql_delete, update, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.cert_sign import sign_cert
from app.core.cert_pdf import build_certificate_pdf
from app.core.cert_storage import (
    upload_certificate_pdf_bytes,
    presign_certificate_download_url,
)

from app.core.event_thumbnail_storage import generate_event_thumbnail_presigned_put

from app.models.events import Event, EventSubmission, EventSubmissionPhoto
from app.models.student import Student

# ✅ Activity tracking
from app.models.activity_session import ActivitySession, ActivitySessionStatus
from app.models.activity_type import ActivityType

# ✅ Event ↔ ActivityType mapping
from app.models.event_activity_type import EventActivityType

# ✅ Certificates
from app.models.certificate import Certificate, CertificateCounter


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
IST = ZoneInfo("Asia/Kolkata")


# =========================================================
# ---------------------- PARSERS ---------------------------
# =========================================================

def _parse_date(val: Any) -> Optional[date_type]:
    """
    Accepts:
      - date
      - datetime
      - ISO string: "2026-03-01" or "2026-03-01T10:00:00"
    """
    if val is None:
        return None
    if isinstance(val, date_type) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        # take first 10 chars for YYYY-MM-DD
        try:
            return date_type.fromisoformat(s[:10])
        except Exception:
            return None
    return None


def _parse_time(val: Any) -> Optional[time_type]:
    """
    Accepts:
      - time
      - datetime (uses .time())
      - strings: "HH:MM", "HH:MM:SS", "HH:MM:SS.sss"
      - ISO datetime strings: "2026-03-01T12:22:00"
    Returns: datetime.time or None
    """
    if val is None:
        return None

    if isinstance(val, time_type) and not isinstance(val, datetime):
        return val.replace(tzinfo=None)

    if isinstance(val, datetime):
        return val.time().replace(tzinfo=None)

    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None

        # ISO datetime → extract time
        if "T" in s or " " in s:
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                return dt.time().replace(tzinfo=None)
            except Exception:
                pass

        # time-only: HH:MM[:SS[.ffffff]]
        try:
            return time_type.fromisoformat(s).replace(tzinfo=None)
        except Exception:
            pass

        # manual fallback
        try:
            parts = s.split(":")
            hh = int(parts[0])
            mm = int(parts[1]) if len(parts) > 1 else 0
            ss = int(float(parts[2])) if len(parts) > 2 else 0
            return time_type(hour=hh, minute=mm, second=ss)
        except Exception:
            return None

    return None


# # =========================================================
# ---------------------- TIME HELPERS ----------------------
# =========================================================

from __future__ import annotations

from datetime import datetime, timezone, timedelta, time as time_type
from zoneinfo import ZoneInfo
from fastapi import HTTPException

IST = ZoneInfo("Asia/Kolkata")


def _now_ist_aware() -> datetime:
    """Current time in IST (timezone-aware)."""
    return datetime.now(IST)


def _event_window_ist_aware(event) -> tuple[datetime, datetime]:
    """
    Build event window as timezone-aware IST datetimes.

    event.event_date: date (required)
    event.start_time: time | None
    event.end_time  : time | None

    ✅ Supports cross-midnight windows: if end <= start, end is moved to next day.
    """
    if not getattr(event, "event_date", None):
        raise HTTPException(status_code=400, detail="Event date not configured.")

    start_t: time_type = getattr(event, "start_time", None) or time_type(0, 0)
    end_t: time_type = getattr(event, "end_time", None) or time_type(23, 59, 59)

    start_ist = datetime.combine(event.event_date, start_t).replace(tzinfo=IST)
    end_ist = datetime.combine(event.event_date, end_t).replace(tzinfo=IST)

    # ✅ Cross-midnight safety (e.g., 23:00 -> 01:00 next day)
    if end_ist <= start_ist:
        end_ist = end_ist + timedelta(days=1)

    return start_ist, end_ist


def _event_window_utc(event) -> tuple[datetime, datetime]:
    """
    Returns (start_utc, end_utc) as timezone-aware UTC datetimes.
    ✅ Use these for DB comparisons against timestamptz columns.
    """
    start_ist, end_ist = _event_window_ist_aware(event)
    return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)


def _ensure_event_window(event) -> None:
    """
    ✅ Unified window check using the SAME event window logic used for session filtering.
    Avoids naive datetime bugs and timezone mismatches.

    Raises:
      403 if event not active / not started / ended
      400 if window not configured
    """
    if not getattr(event, "is_active", True):
        raise HTTPException(status_code=403, detail="Event has ended.")

    start_ist, end_ist = _event_window_ist_aware(event)
    now_ist = _now_ist_aware()

    if now_ist < start_ist:
        raise HTTPException(status_code=403, detail="Event has not started yet.")

    if now_ist > end_ist:
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
    - Session.started_at within event window (UTC-aware)

    ActivitySession.started_at is usually UTC-aware.
    So compare against event window converted to UTC-aware.
    """
    if not activity_type_ids:
        return []

    start_utc, end_utc = _event_window_utc(event)

    q = await db.execute(
        select(func.distinct(ActivitySession.student_id)).where(
            func.lower(cast(ActivitySession.status, String)) == "approved",
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
    """
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # ✅ Try mapped activity types first
    activity_type_ids = await _get_event_activity_type_ids(db, event_id)

    # ✅ FALLBACK: infer activity types from APPROVED sessions inside event window
    if not activity_type_ids:
        start_utc, end_utc = _event_window_utc(event)
        aq = await db.execute(
            select(func.distinct(ActivitySession.activity_type_id)).where(
                ActivitySession.status == ActivitySessionStatus.APPROVED,
                ActivitySession.started_at >= start_utc,
                ActivitySession.started_at <= end_utc,
                ActivitySession.activity_type_id.is_not(None),
            )
        )
        activity_type_ids = [int(r[0]) for r in aq.all() if r and r[0] is not None]

    if not activity_type_ids:
        return {"event_id": event_id, "eligible_students": 0, "submissions_approved": 0, "certificates_issued": 0}

    eligible_student_ids = await _eligible_students_from_sessions(db, event, activity_type_ids)
    if not eligible_student_ids:
        return {"event_id": event_id, "eligible_students": 0, "submissions_approved": 0, "certificates_issued": 0}

    now_utc = datetime.now(timezone.utc)

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
            sub = EventSubmission(event_id=event_id, student_id=sid, status="approved")
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

    issued = await _issue_certificates_for_event(db, event)

    return {
        "event_id": event_id,
        "eligible_students": len(eligible_student_ids),
        "submissions_approved": submissions_approved,
        "certificates_issued": issued,
    }


async def _infer_activity_type_ids_from_sessions(
    db: AsyncSession,
    start_utc: datetime,
    end_utc: datetime,
) -> list[int]:
    """
    Infer activity types from APPROVED sessions overlapping the event window.
    ✅ No ActivitySession.event_id (your table doesn't have it)
    """
    aq = await db.execute(
        select(func.distinct(ActivitySession.activity_type_id)).where(
            ActivitySession.status == ActivitySessionStatus.APPROVED,
            ActivitySession.activity_type_id.is_not(None),
            # overlap with window
            ActivitySession.started_at <= end_utc,
            func.coalesce(ActivitySession.submitted_at, ActivitySession.expires_at) >= start_utc,
        )
    )
    return [int(r[0]) for r in aq.all() if r and r[0] is not None]



# assumes these are already imported in your file:
# Event, EventSubmission, ActivitySession, ActivityType, Certificate
# settings, sign_cert, build_certificate_pdf, upload_certificate_pdf_bytes
# _event_window_utc, _now_ist_naive, _academic_year_from_date
# _get_event_activity_type_ids, _infer_activity_type_ids_from_sessions
# _next_certificate_no


async def _issue_certificates_for_event(db: AsyncSession, event: Event) -> int:
    """
    ✅ FIXED PERMANENTLY:
    - EventSubmission.status + ActivitySession.status are matched case-insensitively
      (handles DB enums stored as "APPROVED" etc.)
    - Uses mapped activity_type_ids; if missing -> infer from APPROVED sessions in window
    - Computes HOURS by overlap inside event window:
        overlap = max(0, min(session_end, end_utc) - max(started_at, start_utc))
      where session_end = coalesce(submitted_at, expires_at, end_utc)  ✅ IMPORTANT FIX
      (prevents NULL end timestamps from producing 0 rows / 0 hours)
    - Issues certificate only if hours > 0 for that student + activity_type in window
    - If mapping exists but yields 0, retries with inferred ids (mapping mismatch safety)
    """

    # -----------------------
    # Approved submissions
    # -----------------------
    q = await db.execute(
        select(EventSubmission).where(
            EventSubmission.event_id == event.id,
            func.lower(cast(EventSubmission.status, String)) == "approved",
        )
    )
    submissions = q.scalars().all()
    if not submissions:
        return 0

    # -----------------------
    # Event window in UTC
    # -----------------------
    start_utc, end_utc = _event_window_utc(event)

    # Safety if old rows have bad end_time
    if end_utc <= start_utc:
        end_utc = start_utc + timedelta(hours=6)

    # -----------------------
    # Activity types (mapped -> else infer)
    # -----------------------
    mapped_ids = await _get_event_activity_type_ids(db, event.id)
    activity_type_ids = sorted({int(x) for x in mapped_ids if x is not None})

    if not activity_type_ids:
        activity_type_ids = await _infer_activity_type_ids_from_sessions(db, event.id, start_utc, end_utc)

    if not activity_type_ids:
        raise HTTPException(
            status_code=400,
            detail="No activity types found for this event (mapping empty and no approved sessions in event window).",
        )

    # -----------------------
    # Caches
    # -----------------------
    now_utc = datetime.now(timezone.utc)
    now_ist = _now_ist_aware()
    academic_year = _academic_year_from_date(now_ist)

    venue_name = (
        getattr(event, "venue_name", None)
        or getattr(event, "venue", None)
        or getattr(event, "location", None)
        or ""
    ).strip() or "N/A"

    student_ids = sorted({int(s.student_id) for s in submissions if s.student_id is not None})
    st_q = await db.execute(select(Student).where(Student.id.in_(student_ids)))
    students = st_q.scalars().all()
    student_by_id = {int(s.id): s for s in students}

    at_q = await db.execute(select(ActivityType).where(ActivityType.id.in_(activity_type_ids)))
    ats = at_q.scalars().all()
    at_by_id = {int(a.id): a for a in ats}

    # -----------------------
    # Helper: hours overlap
    # -----------------------
    async def _hours_in_window(student_id: int, at_id: int) -> float:
        """
        Sum overlapped hours inside [start_utc, end_utc] for APPROVED sessions.

        ✅ IMPORTANT:
        Some rows may have submitted_at/expires_at NULL even when APPROVED.
        If we don't fallback, the filter `end >= start_utc` becomes NULL and kills the match.
        So session_end = coalesce(submitted_at, expires_at, end_utc).
        """
        session_end = func.coalesce(
            ActivitySession.submitted_at,
            ActivitySession.expires_at,
            end_utc,  # ✅ fallback prevents NULL end from breaking overlap logic
        )

        hrs_q = await db.execute(
            select(
                func.coalesce(
                    func.sum(
                        func.greatest(
                            0.0,
                            func.extract(
                                "epoch",
                                (
                                    func.least(session_end, end_utc)
                                    - func.greatest(ActivitySession.started_at, start_utc)
                                ),
                            )
                            / 3600.0,
                        )
                    ),
                    0.0,
                )
            ).where(
                ActivitySession.student_id == student_id,
                ActivitySession.activity_type_id == at_id,

                # ✅ FIX: case-insensitive APPROVED match
                func.lower(cast(ActivitySession.status, String)) == "approved",

                # ✅ must overlap window (use same session_end)
                ActivitySession.started_at <= end_utc,
                session_end >= start_utc,
            )
        )
        return float(hrs_q.scalar() or 0.0)

    # -----------------------
    # Main issue loop
    # -----------------------
    issued = 0

    for sub in submissions:
        if sub.student_id is None:
            continue

        student = student_by_id.get(int(sub.student_id))
        if not student:
            continue

        student_name = (getattr(student, "name", None) or "Student").strip()
        usn = (getattr(student, "usn", None) or "").strip()

        for at_id in activity_type_ids:
            at_id = int(at_id)

            # already issued?
            ex = await db.execute(
                select(Certificate.id).where(
                    Certificate.submission_id == sub.id,
                    Certificate.activity_type_id == at_id,
                )
            )
            if ex.scalar_one_or_none():
                continue

            hours = await _hours_in_window(int(sub.student_id), at_id)
            if hours <= 0:
                continue

            at = at_by_id.get(at_id)
            activity_type_name = (getattr(at, "name", None) or "").strip() or f"Activity Type #{at_id}"

            # points
            points_awarded = 0
            if at:
                ppu = getattr(at, "points_per_unit", None)
                hpu = getattr(at, "hours_per_unit", None)
                if ppu is not None and hpu:
                    try:
                        points_awarded = int(round((hours / float(hpu)) * float(ppu)))
                    except Exception:
                        points_awarded = 0

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
            await db.flush()

            sig = sign_cert(cert.certificate_no)
            verify_url = (
                f"{settings.PUBLIC_BASE_URL}/api/public/certificates/verify"
                f"?cert_id={quote(cert.certificate_no)}&sig={quote(sig)}"
            )

            pdf_bytes = build_certificate_pdf(
                template_pdf_path=settings.CERT_TEMPLATE_PDF_PATH,
                certificate_no=cert.certificate_no,
                issue_date=(cert.issued_at.date().isoformat() if cert.issued_at else now_ist.date().isoformat()),
                student_name=student_name,
                usn=usn,
                activity_type=activity_type_name,
                venue_name=venue_name,
                activity_points=int(points_awarded),
                verify_url=verify_url,
            )

            object_key = upload_certificate_pdf_bytes(cert.id, pdf_bytes)
            cert.pdf_path = object_key

            issued += 1

    # -----------------------
    # Mapping mismatch retry
    # -----------------------
    if issued == 0 and mapped_ids:
        inferred_ids = await _infer_activity_type_ids_from_sessions(db, event.id, start_utc, end_utc)
        inferred_ids = sorted({int(i) for i in inferred_ids if i is not None and int(i) > 0})
        inferred_ids = [i for i in inferred_ids if i not in activity_type_ids]

        if inferred_ids:
            at_q2 = await db.execute(select(ActivityType).where(ActivityType.id.in_(inferred_ids)))
            for a in at_q2.scalars().all():
                at_by_id[int(a.id)] = a

            for sub in submissions:
                if sub.student_id is None:
                    continue

                student = student_by_id.get(int(sub.student_id))
                if not student:
                    continue

                student_name = (getattr(student, "name", None) or "Student").strip()
                usn = (getattr(student, "usn", None) or "").strip()

                for at_id in inferred_ids:
                    at_id = int(at_id)

                    ex = await db.execute(
                        select(Certificate.id).where(
                            Certificate.submission_id == sub.id,
                            Certificate.activity_type_id == at_id,
                        )
                    )
                    if ex.scalar_one_or_none():
                        continue

                    hours = await _hours_in_window(int(sub.student_id), at_id)
                    if hours <= 0:
                        continue

                    at = at_by_id.get(at_id)
                    activity_type_name = (getattr(at, "name", None) or "").strip() or f"Activity Type #{at_id}"

                    points_awarded = 0
                    if at:
                        ppu = getattr(at, "points_per_unit", None)
                        hpu = getattr(at, "hours_per_unit", None)
                        if ppu is not None and hpu:
                            try:
                                points_awarded = int(round((hours / float(hpu)) * float(ppu)))
                            except Exception:
                                points_awarded = 0

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
                    await db.flush()

                    sig = sign_cert(cert.certificate_no)
                    verify_url = (
                        f"{settings.PUBLIC_BASE_URL}/api/public/certificates/verify"
                        f"?cert_id={quote(cert.certificate_no)}&sig={quote(sig)}"
                    )

                    pdf_bytes = build_certificate_pdf(
                        template_pdf_path=settings.CERT_TEMPLATE_PDF_PATH,
                        certificate_no=cert.certificate_no,
                        issue_date=(cert.issued_at.date().isoformat() if cert.issued_at else now_ist.date().isoformat()),
                        student_name=student_name,
                        usn=usn,
                        activity_type=activity_type_name,
                        venue_name=venue_name,
                        activity_points=int(points_awarded),
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
        select(Certificate, ActivityType.name)
        .outerjoin(ActivityType, ActivityType.id == Certificate.activity_type_id)
        .where(
            Certificate.student_id == student_id,
            Certificate.event_id == event_id,
            Certificate.revoked_at.is_(None),
        )
        .order_by(Certificate.issued_at.desc(), Certificate.id.desc())
    )

    rows = q.all()
    out = []
    for cert, at_name in rows:
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
            "activity_type_id": cert.activity_type_id,
            "activity_type_name": at_name or f"Activity Type #{cert.activity_type_id}",
            "pdf_url": pdf_url,
        })
    return out


from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from sqlalchemy import select, func

async def regenerate_event_certificates(db: AsyncSession, event_id: int) -> dict:
    """
    - Only allow when event is ENDED (is_active=False)
    - Auto-approve submissions from APPROVED face sessions
    - Then generate certificates for all approved submissions
    """
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if bool(getattr(event, "is_active", True)):
        raise HTTPException(status_code=400, detail="End the event first, then generate certificates")

    # 1) auto-approve (may approve 0 if already approved)
    auto = await auto_approve_event_from_sessions(db, event_id)

    # 2) IMPORTANT: issue certificates based on approved submissions
    issued = await _issue_certificates_for_event(db, event)

    if issued == 0:
        raise HTTPException(
            status_code=400,
            detail="No certificates generated. Ensure approved submissions exist and approved sessions exist within the event window for the mapped activity types.",
        )

    return {
        "event_id": event_id,
        "eligible_students": auto.get("eligible_students", 0),
        "submissions_approved": auto.get("submissions_approved", 0),
        "certificates_issued": issued,
    }

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
async def create_event(db: AsyncSession, payload) -> dict:
    """
    ✅ UPDATED create_event (no _event_out_dict dependency):
    - Uses ONLY payload.activity_type_ids (schema normalizes frontend keys)
    - Requires end_time (TIME) and validates end_time > start_time
    - Validates ActivityType IDs exist
    - Inserts mapping rows atomically (transaction)
    - Returns dict directly (so missing _event_out_dict won't break)
    """

    # ─────────────────────────────────────────────
    # Parse date/time
    # ─────────────────────────────────────────────
    event_date: date_type | None = _parse_date(
        getattr(payload, "event_date", None) or getattr(payload, "date", None)
    )
    if not event_date:
        raise HTTPException(status_code=422, detail="event_date is required")

    start_time: time_type | None = _parse_time(
        getattr(payload, "start_time", None) or getattr(payload, "time", None)
    )
    if start_time is None:
        raise HTTPException(status_code=422, detail="start_time is required (HH:MM)")

    end_time: time_type | None = _parse_time(getattr(payload, "end_time", None))
    if end_time is None:
        raise HTTPException(status_code=422, detail="end_time is required (HH:MM)")

    if end_time <= start_time:
        raise HTTPException(status_code=422, detail="end_time must be after start_time")

    # ─────────────────────────────────────────────
    # required_photos safety
    # ─────────────────────────────────────────────
    required_photos = int(getattr(payload, "required_photos", 3) or 3)
    if required_photos < 3 or required_photos > 5:
        raise HTTPException(status_code=422, detail="required_photos must be between 3 and 5")

    # ─────────────────────────────────────────────
    # Activity type ids (ONLY from schema)
    # ─────────────────────────────────────────────
    ids: List[int] = list(getattr(payload, "activity_type_ids", None) or [])
    ids = sorted({int(x) for x in ids if x is not None and int(x) > 0})

    if not ids:
        raise HTTPException(status_code=422, detail="Please select at least 1 activity type")

    # Validate IDs exist in ActivityType
    q = await db.execute(select(ActivityType.id).where(ActivityType.id.in_(ids)))
    existing = {int(r[0]) for r in q.all()}
    missing = [i for i in ids if i not in existing]
    if missing:
        raise HTTPException(status_code=422, detail=f"Invalid activity_type_ids: {missing}")

    # ─────────────────────────────────────────────
    # Create event + mapping atomically
    # ─────────────────────────────────────────────
    maps_url = getattr(payload, "maps_url", None) or getattr(payload, "venue_maps_url", None)

    try:
        async with db.begin():  # ✅ atomic transaction
            event = Event(
                title=str(getattr(payload, "title", "")).strip(),
                description=(getattr(payload, "description", None) or None),
                required_photos=required_photos,
                is_active=True,
                event_date=event_date,
                start_time=start_time,
                end_time=end_time,  # ✅ TIME column
                thumbnail_url=getattr(payload, "thumbnail_url", None),
                venue_name=getattr(payload, "venue_name", None),
                maps_url=maps_url,
                location_lat=getattr(payload, "location_lat", None),
                location_lng=getattr(payload, "location_lng", None),
                geo_radius_m=getattr(payload, "geo_radius_m", None),
            )
            db.add(event)
            await db.flush()  # ✅ event.id available

            # ✅ insert mapping rows
            db.add_all(
                [EventActivityType(event_id=event.id, activity_type_id=at_id) for at_id in ids]
            )

        # outside begin: committed successfully
        await db.refresh(event)

        # ✅ Return dict directly (no _event_out_dict)
        out = {
            "id": event.id,
            "title": event.title,
            "description": event.description,
            "required_photos": event.required_photos,
            "is_active": event.is_active,
            "event_date": event.event_date,
            "start_time": event.start_time,
            "end_time": event.end_time,
            "thumbnail_url": getattr(event, "thumbnail_url", None),
            "venue_name": getattr(event, "venue_name", None),
            "maps_url": getattr(event, "maps_url", None),
            "location_lat": getattr(event, "location_lat", None),
            "location_lng": getattr(event, "location_lng", None),
            "geo_radius_m": getattr(event, "geo_radius_m", None),
            "activity_type_ids": ids,  # helpful for UI/debug
        }
        return out

    except HTTPException:
        raise
    except Exception as e:
        # db.begin() rolls back automatically on exception, but keeping this is fine
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create event: {str(e)}")
    
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

    sub_result = await db.execute(select(EventSubmission.id).where(EventSubmission.event_id == event_id))
    submission_ids = [row[0] for row in sub_result.fetchall()]

    if submission_ids:
        await db.execute(
            sql_delete(EventSubmissionPhoto).where(EventSubmissionPhoto.submission_id.in_(submission_ids))
        )
        await db.execute(sql_delete(EventSubmission).where(EventSubmission.event_id == event_id))

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

    event = await db.get(Event, submission.event_id)
    if event:
        await _issue_certificates_for_event(db, event)

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
    now_ist = datetime.now(IST)

    q = await db.execute(
        select(Event)
        .where(
            Event.event_date.is_not(None),
            Event.is_active.is_(True),
        )
        .order_by(
            Event.event_date.desc(),
            Event.start_time.asc().nulls_last(),
            Event.id.desc(),
        )
    )
    events = q.scalars().all()

    active: list[Event] = []
    for e in events:
        try:
            start_ist, end_ist = _event_window_ist_aware(e)
            if now_ist <= end_ist:
                active.append(e)
        except Exception:
            continue

    return active


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
            EventSubmission.student_id == student_id,
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
            EventSubmissionPhoto.seq_no == seq_no,
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
            EventSubmission.student_id == student_id,
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
            ),
        )

    submission.status = "submitted"
    submission.description = description
    if hasattr(submission, "submitted_at"):
        submission.submitted_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(submission)
    return submission