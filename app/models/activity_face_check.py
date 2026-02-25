from typing import Optional
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_face_check import ActivityFaceCheck
from app.models.activity_photo import ActivityPhoto
from app.models.activity_session import ActivitySession


async def upsert_face_check(
    db: AsyncSession,
    *,
    session_id: int,
    photo_id: int,
    matched: bool,
    cosine_score: Optional[float] = None,
    l2_score: Optional[float] = None,
    total_faces: Optional[int] = None,
    processed_object: Optional[str] = None,
    reason: Optional[str] = None,
) -> ActivityFaceCheck:
    # 1) Load photo (source of truth for student_id)
    photo = await db.get(ActivityPhoto, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="ActivityPhoto not found")

    # 2) Load session (validate photo belongs to session)
    session = await db.get(ActivitySession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="ActivitySession not found")

    if photo.session_id != session_id:
        raise HTTPException(status_code=400, detail="photo_id does not belong to session_id")

    # 3) Derive student_id (NEVER take from request)
    if photo.student_id is None:
        raise HTTPException(status_code=400, detail="Photo student_id is NULL (migration/backfill issue)")

    if session.student_id != photo.student_id:
        raise HTTPException(status_code=400, detail="session student_id and photo student_id mismatch")

    student_id = photo.student_id

    # 4) Upsert by unique key (session_id + photo_id)
    res = await db.execute(
        select(ActivityFaceCheck).where(
            ActivityFaceCheck.session_id == session_id,
            ActivityFaceCheck.photo_id == photo_id,
        )
    )
    face_check = res.scalar_one_or_none()

    if face_check:
        face_check.student_id = student_id
        face_check.matched = matched
        face_check.cosine_score = cosine_score
        face_check.l2_score = l2_score
        face_check.total_faces = total_faces
        face_check.processed_object = processed_object
        face_check.reason = reason

        await db.commit()
        await db.refresh(face_check)
        return face_check

    face_check = ActivityFaceCheck(
        student_id=student_id,
        session_id=session_id,
        photo_id=photo_id,
        matched=matched,
        cosine_score=cosine_score,
        l2_score=l2_score,
        total_faces=total_faces,
        processed_object=processed_object,
        reason=reason,
    )

    db.add(face_check)
    await db.commit()
    await db.refresh(face_check)
    return face_check