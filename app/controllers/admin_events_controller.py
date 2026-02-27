# app/controllers/admin_events_controller.py
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.admin_event import AdminEvent  # <-- change to your actual model

async def admin_end_event(db: AsyncSession, event_id: int):
    q = await db.execute(select(AdminEvent).where(AdminEvent.id == event_id))
    ev = q.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")

    # mark as ended (adjust fields to your schema)
    ev.ended_at = datetime.now(timezone.utc)
    ev.is_active = False  # if you have it
    ev.status = "ended"   # if you have it

    await db.commit()
    await db.refresh(ev)
    return ev