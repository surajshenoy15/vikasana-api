# app/routes/admin_events.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.controllers.admin_events_controller import admin_end_event

# ❌ REMOVE /api from here
router = APIRouter(prefix="/admin/events", tags=["Admin - Events"])

@router.post("/{event_id}/end")
async def end_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await admin_end_event(db=db, event_id=event_id)