import secrets
from datetime import datetime, timedelta, time, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from app.models.activity_type import ActivityType, ActivityTypeStatus
from app.models.activity_session import ActivitySession, ActivitySessionStatus
from app.models.activity_photo import ActivityPhoto
from app.models.student_activity_stats import StudentActivityStats
from app.controllers.activity_photos_controller import add_activity_photo
from app.schemas.activity import PhotoOut

MIN_PHOTOS = 3
MAX_PHOTOS = 5


# ─────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────

def _end_of_day(dt: datetime) -> datetime:
    return datetime.combine(dt.date(), time(23, 59, 59), tzinfo=dt.tzinfo)


def _calc_duration_hours(photo_times: list[datetime]) -> float:
    if len(photo_times) < 2:
        return 0.0
    start = min(photo_times)
    end = max(photo_times)
    seconds = (end - start).total_seconds()
    return max(0.0, seconds / 3600.0)


# ─────────────────────────────────────────────
# Activity Types
# ─────────────────────────────────────────────

async def list_activity_types(db: AsyncSession, include_pending: bool = False):
    q = select(ActivityType).where(ActivityType.is_active == True)
    if not include_pending:
        q = q.where(ActivityType.status == ActivityTypeStatus.APPROVED)
    q = q.order_by(ActivityType.name.asc())
    res = await db.execute(q)
    return res.scalars().all()


async def request_new_activity_type(db: AsyncSession, name: str, description: str | None):
    existing = await db.execute(
        select(ActivityType).where(func.lower(ActivityType.name) == name.lower())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Activity type already exists")

    at = ActivityType(
        name=name.strip(),
        description=description,
        status=ActivityTypeStatus.PENDING,
        hours_per_unit=20,
        points_per_unit=5,
        max_points=20,
    )
    db.add(at)
    await db.commit()
    await db.refresh(at)
    return at


# ─────────────────────────────────────────────
# Create Session
# ─────────────────────────────────────────────

async def create_session(
    db: AsyncSession,
    student_id: int,
    activity_type_id: int,
    activity_name: str,
    description: str | None,
):
    at_res = await db.execute(
        select(ActivityType).where(ActivityType.id == activity_type_id)
    )
    activity_type = at_res.scalar_one_or_none()
    if not activity_type:
        raise HTTPException(status_code=404, detail="Activity type not found")

    now = datetime.now(timezone.utc)

    session = ActivitySession(
        student_id=student_id,
        activity_type_id=activity_type_id,
        activity_name=activity_name.strip(),
        description=description,
        session_code=secrets.token_hex(8),
        started_at=now,
        expires_at=_end_of_day(now),
        status=ActivitySessionStatus.DRAFT,
    )

    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


# ─────────────────────────────────────────────
# Add Photo
# ─────────────────────────────────────────────

async def add_photo_to_session(
    db: AsyncSession,
    student_id: int,
    session_id: int,
    seq_no: int,
    image_url: str,
    captured_at: datetime,
    lat: float,
    lng: float,
    sha256: str | None = None,
) -> PhotoOut:
    # 1) Verify session exists + belongs to student
    res = await db.execute(
        select(ActivitySession).where(
            ActivitySession.id == session_id,
            ActivitySession.student_id == student_id,
        )
    )
    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 2) Ensure still draft
    if session.status != ActivitySessionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Cannot add photo after submission")

    # 3) Ensure not expired
    now = datetime.now(timezone.utc)
    if now > session.expires_at:
        session.status = ActivitySessionStatus.EXPIRED
        await db.commit()
        raise HTTPException(status_code=400, detail="Session expired")

    # 4) Enforce seq range
    if seq_no < 1 or seq_no > MAX_PHOTOS:
        raise HTTPException(status_code=400, detail=f"seq_no must be between 1 and {MAX_PHOTOS}")

    # 5) Optional: prevent exceeding max photos count
    count_res = await db.execute(
        select(func.count(ActivityPhoto.id)).where(ActivityPhoto.session_id == session_id)
    )
    existing_count = int(count_res.scalar() or 0)
    if existing_count >= MAX_PHOTOS:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_PHOTOS} photos allowed")

    # 6) Save via photo controller (upsert/duplicate logic stays there)
    row = await add_activity_photo(
        db=db,
        session_id=session_id,
        student_id=student_id,
        seq_no=seq_no,
        image_url=image_url,
        lat=lat,
        lng=lng,
        captured_at=captured_at,
        sha256=sha256,
    )
    return row


# ─────────────────────────────────────────────
# Submit Session
# ─────────────────────────────────────────────

async def submit_session(db: AsyncSession, student_id: int, session_id: int):
    res = await db.execute(
        select(ActivitySession).where(
            ActivitySession.id == session_id,
            ActivitySession.student_id == student_id,
        )
    )
    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != ActivitySessionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Session already submitted")

    now = datetime.now(timezone.utc)
    if now > session.expires_at:
        session.status = ActivitySessionStatus.EXPIRED
        await db.commit()
        raise HTTPException(status_code=400, detail="Session expired")

    photos_res = await db.execute(
        select(ActivityPhoto).where(ActivityPhoto.session_id == session_id)
    )
    photos = photos_res.scalars().all()

    if len(photos) < MIN_PHOTOS:
        raise HTTPException(status_code=400, detail=f"Minimum {MIN_PHOTOS} photos required")

    photo_times = []
    suspicious = False
    reasons = []

    for ph in photos:
        photo_times.append(ph.captured_at)

        if ph.captured_at.date() != session.started_at.date():
            suspicious = True
            reasons.append("photo_not_same_day")

        if not (session.started_at <= ph.captured_at <= session.expires_at):
            suspicious = True
            reasons.append("photo_outside_time_window")

        if ph.sha256:
            dup2 = await db.execute(
                select(ActivityPhoto.id).where(
                    ActivityPhoto.session_id == session_id,
                    ActivityPhoto.sha256 == ph.sha256,
                    ActivityPhoto.id != ph.id,
                )
            )
            if dup2.scalar_one_or_none() is not None:
                suspicious = True
                reasons.append("duplicate_photo_detected")

    session.duration_hours = _calc_duration_hours(photo_times)
    session.submitted_at = now

    if suspicious:
        session.status = ActivitySessionStatus.FLAGGED
        session.flag_reason = ",".join(sorted(set(reasons)))
        await db.commit()
        return session, 0, 0, 0

    session.status = ActivitySessionStatus.APPROVED
    await db.commit()

    return session, 0, 0, 0


# ─────────────────────────────────────────────
# Session Detail
# ─────────────────────────────────────────────

async def get_student_session_detail(db, student_id: int, session_id: int):
    res = await db.execute(
        select(ActivitySession)
        .where(
            ActivitySession.id == session_id,
            ActivitySession.student_id == student_id,
        )
        .options(selectinload(ActivitySession.photos))
    )

    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    photos = list(session.photos or [])

    sha_counts = {}
    for ph in photos:
        if ph.sha256:
            sha_counts[ph.sha256] = sha_counts.get(ph.sha256, 0) + 1

    photos_out = []
    for ph in photos:
        photos_out.append({
            "id": ph.id,
            "image_url": ph.image_url,
            "sha256": ph.sha256,
            "captured_at": ph.captured_at,
            "lat": ph.lat,
            "lng": ph.lng,
            "is_duplicate": bool(ph.sha256 and sha_counts.get(ph.sha256, 0) > 1),
        })

    return {
        "id": session.id,
        "activity_type_id": session.activity_type_id,
        "activity_name": session.activity_name,
        "description": session.description,
        "started_at": session.started_at,
        "expires_at": session.expires_at,
        "submitted_at": session.submitted_at,
        "status": session.status.value,
        "duration_hours": session.duration_hours,
        "flag_reason": session.flag_reason,
        "photos": photos_out,
    }