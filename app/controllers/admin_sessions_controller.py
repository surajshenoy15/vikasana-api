from typing import Optional, List
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_session import ActivitySession, ActivitySessionStatus
from app.models.activity_photo import ActivityPhoto
from app.models.activity_face_check import ActivityFaceCheck


async def admin_list_sessions(
    db: AsyncSession,
    status: Optional[ActivitySessionStatus] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    # Base
    stmt = select(ActivitySession)

    # Filter status
    if status:
        stmt = stmt.where(ActivitySession.status == status)
    else:
        # default: show review queue
        stmt = stmt.where(ActivitySession.status.in_([ActivitySessionStatus.SUBMITTED, ActivitySessionStatus.FLAGGED]))

    # Optional search (activity_name/session_code)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            (ActivitySession.activity_name.ilike(like)) |
            (ActivitySession.session_code.ilike(like))
        )

    stmt = stmt.order_by(ActivitySession.id.desc()).limit(limit).offset(offset)

    res = await db.execute(stmt)
    sessions = res.scalars().all()

    # Enrich: photos_count + latest face check (cheap approach per-row; OK for small lists)
    items = []
    for s in sessions:
        photos_count = await db.scalar(
            select(func.count(ActivityPhoto.id)).where(ActivityPhoto.session_id == s.id)
        )

        latest_fc = await db.execute(
            select(ActivityFaceCheck)
            .where(ActivityFaceCheck.session_id == s.id)
            .order_by(ActivityFaceCheck.id.desc())
            .limit(1)
        )
        latest_fc_obj = latest_fc.scalars().first()

        items.append({
            "id": s.id,
            "student_id": s.student_id,
            "activity_type_id": s.activity_type_id,
            "activity_name": s.activity_name,
            "status": s.status,
            "submitted_at": s.submitted_at,
            "flag_reason": s.flag_reason,
            "created_at": s.created_at,
            "photos_count": int(photos_count or 0),
            "latest_face_matched": (latest_fc_obj.matched if latest_fc_obj else None),
            "latest_face_reason": (latest_fc_obj.reason if latest_fc_obj else None),
            "latest_face_score": (latest_fc_obj.cosine_score if latest_fc_obj else None),
        })

    return items


async def admin_get_session_detail(db: AsyncSession, session_id: int):
    s = await db.get(ActivitySession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    photos_res = await db.execute(
        select(ActivityPhoto)
        .where(ActivityPhoto.session_id == session_id)
        .order_by(ActivityPhoto.captured_at.asc())
    )
    photos = photos_res.scalars().all()

    face_res = await db.execute(
        select(ActivityFaceCheck)
        .where(ActivityFaceCheck.session_id == session_id)
        .order_by(ActivityFaceCheck.id.desc())
        .limit(1)
    )
    latest_face = face_res.scalars().first()

    return {
        "id": s.id,
        "student_id": s.student_id,
        "activity_type_id": s.activity_type_id,
        "activity_name": s.activity_name,
        "description": s.description,
        "status": s.status,
        "started_at": s.started_at,
        "expires_at": s.expires_at,
        "submitted_at": s.submitted_at,
        "flag_reason": s.flag_reason,
        "created_at": s.created_at,
        "photos": photos,
        "latest_face_check": latest_face,
    }


async def admin_approve_session(db: AsyncSession, session_id: int):
    s = await db.get(ActivitySession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    if s.status not in [ActivitySessionStatus.SUBMITTED, ActivitySessionStatus.FLAGGED]:
        raise HTTPException(status_code=400, detail="Only SUBMITTED/FLAGGED sessions can be approved")

    s.status = ActivitySessionStatus.APPROVED
    await db.commit()
    await db.refresh(s)
    return s


async def admin_reject_session(db: AsyncSession, session_id: int, reason: str):
    s = await db.get(ActivitySession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    if s.status not in [ActivitySessionStatus.SUBMITTED, ActivitySessionStatus.FLAGGED]:
        raise HTTPException(status_code=400, detail="Only SUBMITTED/FLAGGED sessions can be rejected")

    s.status = ActivitySessionStatus.REJECTED
    s.flag_reason = reason  # reuse flag_reason as rejection reason (or add a new column if you want)
    await db.commit()
    await db.refresh(s)
    return s