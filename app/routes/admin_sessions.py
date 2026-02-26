from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.activity_session import ActivitySessionStatus
from app.controllers.admin_sessions_controller import (
    admin_list_sessions,
    admin_get_session_detail,
    admin_approve_session,
    admin_reject_session,
)

router = APIRouter(prefix="/admin/sessions", tags=["Admin - Sessions"])

@router.get("")
async def list_sessions(
    status: Optional[ActivitySessionStatus] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await admin_list_sessions(db=db, status=status, q=q, limit=limit, offset=offset)

@router.get("/{session_id}")
async def get_session_detail(
    session_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await admin_get_session_detail(db=db, session_id=session_id)

@router.post("/{session_id}/approve")
async def approve(
    session_id: int,
    db: AsyncSession = Depends(get_db),
):
    s = await admin_approve_session(db=db, session_id=session_id)
    return {"id": s.id, "status": s.status}

@router.post("/{session_id}/reject")
async def reject(
    session_id: int,
    reason: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    s = await admin_reject_session(db=db, session_id=session_id, reason=reason)
    return {"id": s.id, "status": s.status}