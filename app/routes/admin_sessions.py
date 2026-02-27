# app/routes/admin_sessions.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_admin
from app.models.activity_session import ActivitySessionStatus

from app.controllers.admin_sessions_controller import (
    admin_list_sessions,
    admin_get_session_detail,
    admin_approve_session,
    admin_reject_session,
)

router = APIRouter(prefix="/admin/sessions", tags=["Admin - Sessions"])


# ─────────────────────────────────────────────────────────────
# LIST
# ─────────────────────────────────────────────────────────────

# app/routes/admin_sessions.py

@router.get("")
async def list_sessions(
    status: Optional[str] = Query(
        None,
        description=(
            "Filter by status. Omit for Queue (SUBMITTED+FLAGGED). "
            "Use 'ALL' for no status filter. "
            "Other: SUBMITTED | FLAGGED | APPROVED | REJECTED | DRAFT | EXPIRED"
        ),
    ),
    q: Optional[str] = Query(None, description="Search by activity name or session code"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    parsed_status: Optional[ActivitySessionStatus] = None
    include_all = False  # ✅ NEW

    if status:
        s = status.upper().strip()
        if s == "ALL":
            include_all = True  # ✅ means NO FILTER
        else:
            try:
                parsed_status = ActivitySessionStatus(s)
            except ValueError:
                parsed_status = None  # invalid -> fallback queue

    return await admin_list_sessions(
        db=db,
        status=parsed_status,
        include_all=include_all,  # ✅ NEW
        q=q,
        limit=limit,
        offset=offset,
    )


# ─────────────────────────────────────────────────────────────
# GET DETAIL
# ─────────────────────────────────────────────────────────────

@router.get("/{session_id}")
async def get_session_detail(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """
    Full session detail including:
    - Student info (name, USN, college, face_enrolled)
    - Activity type details + point calculation
    - in_time / out_time
    - Photos with presigned URLs + per-photo face + geo info
    - Location trail (all lat/lng points ordered by time)
    - Latest face check with presigned processed image
    - Target location from activity type
    """
    return await admin_get_session_detail(db=db, session_id=session_id)


# ─────────────────────────────────────────────────────────────
# APPROVE
# ─────────────────────────────────────────────────────────────

@router.post("/{session_id}/approve")
async def approve_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    # ✅ admin_approve_session now returns a dict (includes points info)
    return await admin_approve_session(db=db, session_id=session_id)


# ─────────────────────────────────────────────────────────────
# REJECT
# ─────────────────────────────────────────────────────────────

class RejectBody(BaseModel):
    reason: str = Field(..., min_length=1, description="Rejection reason shown to student")


@router.post("/{session_id}/reject")
async def reject_session(
    session_id: int,
    payload: RejectBody,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    s = await admin_reject_session(db=db, session_id=session_id, reason=payload.reason)
    return {
        "id": s.id,
        "status": s.status.value if hasattr(s.status, "value") else str(s.status),
        "flag_reason": s.flag_reason,
    }