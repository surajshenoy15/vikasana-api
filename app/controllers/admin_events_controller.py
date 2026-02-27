# app/controllers/admin_events_controller.py
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# ✅ Use your existing events model
from app.models.events import Event  # <-- IMPORTANT: must match the class name inside models/events.py


async def admin_end_event(db: AsyncSession, event_id: int):
    # Fetch event
    res = await db.execute(select(Event).where(Event.id == event_id))
    ev = res.scalar_one_or_none()

    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")

    # Mark event as ended (works even if some fields don't exist)
    now = datetime.utcnow()  # ✅ naive datetime (no tzinfo)

    # Common patterns — set whichever exists in your model
    if hasattr(ev, "ended_at"):
        ev.ended_at = now
    if hasattr(ev, "end_time"):
        ev.end_time = now
    if hasattr(ev, "is_active"):
        ev.is_active = False
    if hasattr(ev, "status"):
        # if you store status as string
        try:
            ev.status = "ended"
        except Exception:
            pass

    await db.commit()
    await db.refresh(ev)

    # Return a safe response
    return {
        "id": ev.id,
        "title": getattr(ev, "title", None),
        "status": getattr(ev, "status", None),
        "ended_at": getattr(ev, "ended_at", None) or getattr(ev, "end_time", None),
        "is_active": getattr(ev, "is_active", None),
    }