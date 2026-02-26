from typing import Optional
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_session import ActivitySession, ActivitySessionStatus
from app.models.activity_photo import ActivityPhoto
from app.models.activity_face_check import ActivityFaceCheck

from app.core.minio_client import get_presigned_url
import os

FACE_BUCKET = os.getenv("MINIO_FACE_BUCKET", "face-verification")
# If raw activity photos are also in minio and you store object keys, set this:
ACTIVITY_BUCKET = os.getenv("MINIO_ACTIVITY_BUCKET", "activity-uploads")


def _safe_presigned(bucket: str, obj: Optional[str]) -> Optional[str]:
    if not obj:
        return None
    try:
        return get_presigned_url(bucket=bucket, object_name=obj, expiry_seconds=3600)
    except Exception:
        # don't break sessions page if one object missing
        return None


async def admin_list_sessions(
    db: AsyncSession,
    status: Optional[ActivitySessionStatus] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    stmt = select(ActivitySession)

    # Filter status
    if status:
        stmt = stmt.where(ActivitySession.status == status)
    else:
        stmt = stmt.where(
            ActivitySession.status.in_(
                [ActivitySessionStatus.SUBMITTED, ActivitySessionStatus.FLAGGED]
            )
        )

    # Optional search (activity_name/session_code)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            (ActivitySession.activity_name.ilike(like))
            | (ActivitySession.session_code.ilike(like))
        )

    stmt = stmt.order_by(ActivitySession.id.desc()).limit(limit).offset(offset)

    res = await db.execute(stmt)
    sessions = res.scalars().all()

    items = []
    for s in sessions:
        photos_count = await db.scalar(
            select(func.count(ActivityPhoto.id)).where(ActivityPhoto.session_id == s.id)
        )

        latest_fc_res = await db.execute(
            select(ActivityFaceCheck)
            .where(ActivityFaceCheck.session_id == s.id)
            .order_by(ActivityFaceCheck.id.desc())
            .limit(1)
        )
        latest_fc = latest_fc_res.scalars().first()

        latest_face_processed_url = None
        latest_face_raw_url = None
        latest_face_matched = None
        latest_face_reason = None
        latest_face_score = None

        if latest_fc:
            latest_face_matched = latest_fc.matched
            latest_face_reason = latest_fc.reason
            latest_face_score = latest_fc.cosine_score

            # processed_object is stored in face-verification bucket
            latest_face_processed_url = _safe_presigned(
                FACE_BUCKET, latest_fc.processed_object
            )

            # raw_image_url: if you store object key, you can presign it.
            # If raw_image_url is already a full URL, just return it.
            if latest_fc.raw_image_url:
                if latest_fc.raw_image_url.startswith("http://") or latest_fc.raw_image_url.startswith("https://"):
                    latest_face_raw_url = latest_fc.raw_image_url
                else:
                    latest_face_raw_url = _safe_presigned(ACTIVITY_BUCKET, latest_fc.raw_image_url)

        items.append(
            {
                "id": s.id,
                "student_id": s.student_id,
                "activity_type_id": s.activity_type_id,
                "activity_name": s.activity_name,
                "status": s.status,
                "submitted_at": s.submitted_at,
                "flag_reason": s.flag_reason,
                "created_at": s.created_at,
                "photos_count": int(photos_count or 0),

                # existing fields
                "latest_face_matched": latest_face_matched,
                "latest_face_reason": latest_face_reason,
                "latest_face_score": latest_face_score,

                # ✅ NEW URLs for UI
                "latest_face_processed_url": latest_face_processed_url,
                "latest_face_raw_url": latest_face_raw_url,
            }
        )

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

    latest_face_processed_url = None
    latest_face_raw_url = None

    if latest_face:
        latest_face_processed_url = _safe_presigned(FACE_BUCKET, latest_face.processed_object)

        if latest_face.raw_image_url:
            if latest_face.raw_image_url.startswith("http://") or latest_face.raw_image_url.startswith("https://"):
                latest_face_raw_url = latest_face.raw_image_url
            else:
                latest_face_raw_url = _safe_presigned(ACTIVITY_BUCKET, latest_face.raw_image_url)

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

        # keep existing object if you want (but UI should use URLs)
        "latest_face_check": latest_face,

        # ✅ NEW URLs
        "latest_face_processed_url": latest_face_processed_url,
        "latest_face_raw_url": latest_face_raw_url,
    }


async def admin_approve_session(db: AsyncSession, session_id: int):
    s = await db.get(ActivitySession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    if s.status not in [ActivitySessionStatus.SUBMITTED, ActivitySessionStatus.FLAGGED]:
        raise HTTPException(
            status_code=400,
            detail="Only SUBMITTED/FLAGGED sessions can be approved",
        )

    s.status = ActivitySessionStatus.APPROVED
    await db.commit()
    await db.refresh(s)
    return s


async def admin_reject_session(db: AsyncSession, session_id: int, reason: str):
    s = await db.get(ActivitySession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    if s.status not in [ActivitySessionStatus.SUBMITTED, ActivitySessionStatus.FLAGGED]:
        raise HTTPException(
            status_code=400,
            detail="Only SUBMITTED/FLAGGED sessions can be rejected",
        )

    s.status = ActivitySessionStatus.REJECTED
    s.flag_reason = reason
    await db.commit()
    await db.refresh(s)
    return s