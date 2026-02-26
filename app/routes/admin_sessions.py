from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_admin
from app.models.activity_session import ActivitySessionStatus

from app.schemas.admin_sessions import (
    AdminSessionListItemOut,
    AdminSessionDetailOut,
    RejectSessionIn,
)
from app.controllers.admin_sessions_controller import (
    admin_list_sessions,
    admin_get_session_detail,
    admin_approve_session,
    admin_reject_session,
)

router = APIRouter(prefix="/admin/sessions", tags=["Admin - Sessions"])


@router.get("", response_model=list[AdminSessionListItemOut])
async def list_sessions(
    status: ActivitySessionStatus | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return await admin_list_sessions(db=db, status=status, q=q, limit=limit, offset=offset)


@router.get("/{session_id}", response_model=AdminSessionDetailOut)
async def session_detail(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return await admin_get_session_detail(db=db, session_id=session_id)


@router.post("/{session_id}/approve")
async def approve_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    s = await admin_approve_session(db=db, session_id=session_id)
    return {"success": True, "status": s.status, "session_id": s.id}


@router.post("/{session_id}/reject")
async def reject_session(
    session_id: int,
    payload: RejectSessionIn,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    s = await admin_reject_session(db=db, session_id=session_id, reason=payload.reason)
    return {"success": True, "status": s.status, "session_id": s.id}