from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.cert_sign import verify_sig
from app.models.certificate import Certificate

router = APIRouter(prefix="/public/certificates", tags=["Public - Certificates"])

@router.get("/verify")
async def verify_certificate(
    cert_id: int = Query(...),
    sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if not verify_sig(cert_id, sig):
        raise HTTPException(status_code=400, detail="Invalid signature")

    stmt = (
        select(Certificate)
        .options(
            selectinload(Certificate.student),
            selectinload(Certificate.event),
        )
        .where(Certificate.id == cert_id)
    )
    res = await db.execute(stmt)
    cert = res.scalar_one_or_none()
    if not cert or cert.revoked_at is not None:
        return {"valid": False, "reason": "Not found or revoked"}

    return {
        "valid": True,
        "certificate_no": cert.certificate_no,
        "issued_at": cert.issued_at,
        "student": {
            "name": getattr(cert.student, "name", None),
            "usn": getattr(cert.student, "usn", None),
            "college": getattr(cert.student, "college", None),
            "branch": getattr(cert.student, "branch", None),
        },
        "event": {
            "id": cert.event_id,
            "name": getattr(cert.event, "title", None) or getattr(cert.event, "name", None),
        },
    }