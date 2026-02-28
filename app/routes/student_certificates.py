# app/routes/student_certificates.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import get_current_student
from app.core.cert_storage import presign_certificate_download_url

from app.models.student import Student
from app.models.activity_session import ActivitySession, ActivitySessionStatus
from app.models.certificate import Certificate


router = APIRouter(prefix="/student/certificates", tags=["Student - Certificates"])


@router.get("/{session_id}/download-url")
async def get_certificate_download_url(
    session_id: int,
    expires_in: int = Query(3600, ge=60, le=604800, description="Presigned URL expiry in seconds"),
    db: AsyncSession = Depends(get_db),
    student: Student = Depends(get_current_student),
):
    """
    Returns { url, expires_in } for React Native to open/download.
    - 404: session not found OR certificate not generated
    - 403: session not owned by the student
    """
    # 1) Fetch session
    s_stmt = select(ActivitySession).where(ActivitySession.id == session_id)
    s_res = await db.execute(s_stmt)
    session = s_res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.student_id != student.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    # Optional: enforce eligibility (recommended)
    if session.status != ActivitySessionStatus.APPROVED:
        raise HTTPException(status_code=404, detail="Certificate not available")

    # 2) Find certificate row (by session)
    c_stmt = select(Certificate).where(Certificate.session_id == session_id)
    c_res = await db.execute(c_stmt)
    cert = c_res.scalar_one_or_none()

    if not cert or not cert.pdf_path:
        raise HTTPException(status_code=404, detail="Certificate not generated")

    # 3) Presign MinIO URL
    try:
        url = presign_certificate_download_url(cert.pdf_path, expires_in=expires_in)
    except Exception:
        # Do not leak internals
        raise HTTPException(status_code=500, detail="Could not generate download link")

    return {"url": url, "expires_in": expires_in, "cert_id": cert.id}