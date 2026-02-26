from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import get_current_student  # <- use your student auth dependency
from app.models.activity_session import ActivitySession, ActivitySessionStatus
from app.models.activity_type import ActivityType

router = APIRouter(prefix="/api/student/activity", tags=["Student - Activity Sessions"])

@router.post("/sessions")
async def create_session(
    activity_type_id: int = Query(..., ge=1),
    meta_captured_at: str = Query(...),
    lat: float | None = Query(None),
    lng: float | None = Query(None),
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    # parse iso time safely
    try:
        captured_at = datetime.fromisoformat(meta_captured_at.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid meta_captured_at. Must be ISO string.")

    # validate activity type
    r = await db.execute(select(ActivityType).where(ActivityType.id == activity_type_id))
    at = r.scalar_one_or_none()
    if not at:
        raise HTTPException(status_code=404, detail="Activity type not found")

    s = ActivitySession(
        student_id=student.id,
        activity_type_id=activity_type_id,
        status=ActivitySessionStatus.IN_PROGRESS,
        started_at=captured_at,
        started_lat=lat,
        started_lng=lng,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)

    return {"success": True, "session_id": s.id, "status": s.status}


@router.get("/sessions/{session_id}")
async def get_session(session_id: int, db: AsyncSession = Depends(get_db), student=Depends(get_current_student)):
    r = await db.execute(
        select(ActivitySession).where(ActivitySession.id == session_id, ActivitySession.student_id == student.id)
    )
    s = r.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": s.id, "status": s.status}