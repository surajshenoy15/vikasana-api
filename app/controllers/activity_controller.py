import secrets
from datetime import datetime, timedelta, time, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException
from sqlalchemy.orm import selectinload

from app.models.activity_type import ActivityType, ActivityTypeStatus
from app.models.activity_session import ActivitySession, ActivitySessionStatus
from app.models.activity_photo import ActivityPhoto
from app.models.student_activity_stats import StudentActivityStats

MIN_PHOTOS = 3
MAX_PHOTOS = 5

def _end_of_day(dt: datetime) -> datetime:
    # end of the calendar day 23:59:59
    eod = datetime.combine(dt.date(), time(23, 59, 59), tzinfo=dt.tzinfo)
    return eod

def _calc_duration_hours(photo_times: list[datetime]) -> float:
    if len(photo_times) < 2:
        return 0.0
    start = min(photo_times)
    end = max(photo_times)
    seconds = (end - start).total_seconds()
    return max(0.0, seconds / 3600.0)

async def list_activity_types(db: AsyncSession, include_pending: bool = False):
    q = select(ActivityType).where(ActivityType.is_active == True)
    if not include_pending:
        q = q.where(ActivityType.status == ActivityTypeStatus.APPROVED)
    q = q.order_by(ActivityType.name.asc())
    res = await db.execute(q)
    return res.scalars().all()

async def request_new_activity_type(db: AsyncSession, name: str, description: str | None):
    # create as PENDING
    existing = await db.execute(select(ActivityType).where(func.lower(ActivityType.name) == name.lower()))
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

async def create_session(db: AsyncSession, student_id: int, activity_type_id: int, activity_name: str, description: str | None):
    at_res = await db.execute(select(ActivityType).where(ActivityType.id == activity_type_id))
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

async def add_photo_to_session(
    db: AsyncSession,
    student_id: int,
    session_id: int,
    image_url: str,
    captured_at: datetime,
    lat: float,
    lng: float,
    sha256: str | None,
):
    res = await db.execute(select(ActivitySession).where(ActivitySession.id == session_id))
    session = res.scalar_one_or_none()
    if not session or session.student_id != student_id:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status not in (ActivitySessionStatus.DRAFT,):
        raise HTTPException(status_code=400, detail="Cannot add photo after submission")

    now = datetime.now(timezone.utc)
    if now > session.expires_at:
        session.status = ActivitySessionStatus.EXPIRED
        await db.commit()
        raise HTTPException(status_code=400, detail="Session expired")

    # enforce 3–5 photos overall
    photo_count = await db.execute(select(func.count(ActivityPhoto.id)).where(ActivityPhoto.session_id == session_id))
    count = int(photo_count.scalar() or 0)
    if count >= MAX_PHOTOS:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_PHOTOS} photos allowed")

    # duplication check by sha256 (basic)
    is_dup = False
    if sha256:
        dup = await db.execute(select(ActivityPhoto).where(ActivityPhoto.sha256 == sha256))
        if dup.scalar_one_or_none():
            is_dup = True

    p = ActivityPhoto(
        session_id=session_id,
        image_url=image_url,
        captured_at=captured_at,
        lat=lat,
        lng=lng,
        sha256=sha256,
        is_duplicate=is_dup,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p

async def submit_session(db: AsyncSession, student_id: int, session_id: int):
    res = await db.execute(
        select(ActivitySession).where(ActivitySession.id == session_id)
    )
    session = res.scalar_one_or_none()
    if not session or session.student_id != student_id:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != ActivitySessionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Session already submitted or closed")

    now = datetime.now(timezone.utc)
    if now > session.expires_at:
        session.status = ActivitySessionStatus.EXPIRED
        await db.commit()
        raise HTTPException(status_code=400, detail="Session expired")

    photos_res = await db.execute(select(ActivityPhoto).where(ActivityPhoto.session_id == session_id))
    photos = photos_res.scalars().all()

    if len(photos) < MIN_PHOTOS:
        raise HTTPException(status_code=400, detail=f"Minimum {MIN_PHOTOS} photos required")

    # --- Auto verification checks (basic, scalable) ---
    # 1) same-day check: captured_at date must match session started_at date (calendar day)
    # 2) must be within session window
    # 3) duplication check (already flagged per photo)
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

        if ph.is_duplicate:
            suspicious = True
            reasons.append("duplicate_photo_detected")

    duration_hours = _calc_duration_hours(photo_times)

    session.duration_hours = duration_hours
    session.submitted_at = now
    session.status = ActivitySessionStatus.SUBMITTED

    # If activity type is pending, store but award 0 now (as blueprint)
    at_res = await db.execute(select(ActivityType).where(ActivityType.id == session.activity_type_id))
    activity_type = at_res.scalar_one()

    newly_awarded = 0

    if activity_type.status != ActivityTypeStatus.APPROVED:
        # Keep it submitted, but no points
        await db.commit()
        await db.refresh(session)
        stats = await _get_or_create_stats(db, student_id, session.activity_type_id)
        return session, 0, stats.points_awarded, stats.total_verified_hours

    # if suspicious -> FLAGGED (admin only)
    if suspicious:
        session.status = ActivitySessionStatus.FLAGGED
        session.flag_reason = ",".join(sorted(set(reasons)))
        await db.commit()
        await db.refresh(session)
        stats = await _get_or_create_stats(db, student_id, session.activity_type_id)
        return session, 0, stats.points_awarded, stats.total_verified_hours

    # Otherwise APPROVE + award points
    session.status = ActivitySessionStatus.APPROVED
    await db.commit()
    await db.refresh(session)

    stats = await _get_or_create_stats(db, student_id, session.activity_type_id)

    # Add verified hours
    stats.total_verified_hours += duration_hours

    # Calculate total points eligible by hours:
    # units = floor(total_hours / hours_per_unit)
    # eligible_points = units * points_per_unit
    units = int(stats.total_verified_hours // float(activity_type.hours_per_unit))
    eligible_points = units * int(activity_type.points_per_unit)

    # Cap by max_points per activity type
    eligible_points = min(eligible_points, int(activity_type.max_points))

    # award delta only
    newly_awarded = max(0, eligible_points - stats.points_awarded)
    stats.points_awarded = max(stats.points_awarded, eligible_points)

    # Mark completed if reached max_points
    if stats.points_awarded >= int(activity_type.max_points) and stats.completed_at is None:
        stats.completed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(stats)

    return session, newly_awarded, stats.points_awarded, stats.total_verified_hours

async def _get_or_create_stats(db: AsyncSession, student_id: int, activity_type_id: int) -> StudentActivityStats:
    res = await db.execute(
        select(StudentActivityStats).where(
            StudentActivityStats.student_id == student_id,
            StudentActivityStats.activity_type_id == activity_type_id,
        )
    )
    stats = res.scalar_one_or_none()
    if stats:
        return stats
    stats = StudentActivityStats(student_id=student_id, activity_type_id=activity_type_id)
    db.add(stats)
    await db.commit()
    await db.refresh(stats)
    return stats

async def list_student_sessions(db, student_id: int):
    res = await db.execute(
        select(ActivitySession)
        .where(ActivitySession.student_id == student_id)
        .order_by(ActivitySession.id.desc())
    )
    return list(res.scalars().all())

async def get_student_session_detail(db, student_id: int, session_id: int):
    res = await db.execute(
        select(ActivitySession)
        .where(ActivitySession.id == session_id, ActivitySession.student_id == student_id)
        .options(selectinload(ActivitySession.photos))
    )
    session = res.scalar_one_or_none()
    if not session:
        raise ValueError("Session not found")
    return session