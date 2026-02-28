from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import get_current_student
from app.models.certificate import Certificate

router = APIRouter(prefix="/student/certificates", tags=["Student - Certificates"])

@router.get("/{event_id}/download")
async def download_my_certificate(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    stmt = select(Certificate).where(
        Certificate.event_id == event_id,
        Certificate.student_id == student.id,
    )
    res = await db.execute(stmt)
    cert = res.scalar_one_or_none()
    if not cert or not cert.pdf_path:
        raise HTTPException(status_code=404, detail="Certificate not available")

    return FileResponse(
        cert.pdf_path,
        media_type="application/pdf",
        filename=f"{cert.certificate_no.replace('/','_')}.pdf",
    )