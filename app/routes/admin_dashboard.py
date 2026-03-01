from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

from app.core.database import get_db
from app.core.dependencies import get_current_admin

from app.models.student import Student
from app.models.faculty import Faculty  # adjust if your model name differs
from app.models.activity_session import ActivitySession, ActivitySessionStatus
from app.models.activity_type import ActivityType
from app.models.certificate import Certificate

router = APIRouter(prefix="/admin/dashboard", tags=["Admin - Dashboard"])


@router.get("/stats")
async def dashboard_stats(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    total_students = (await db.execute(select(func.count(Student.id)))).scalar() or 0
    active_students = (await db.execute(select(func.count(Student.id)).where(Student.is_active == True))).scalar() or 0

    total_faculty = (await db.execute(select(func.count(Faculty.id)))).scalar() or 0
    pending_faculty = (await db.execute(select(func.count(Faculty.id)).where(Faculty.is_active == False))).scalar() or 0

    total_activities = (await db.execute(select(func.count(ActivitySession.id)))).scalar() or 0
    approved_activities = (
        await db.execute(select(func.count(ActivitySession.id)).where(ActivitySession.status == ActivitySessionStatus.APPROVED))
    ).scalar() or 0

    total_certificates = (await db.execute(select(func.count(Certificate.id)))).scalar() or 0

    return {
        "totalStudents": total_students,
        "activeStudents": active_students,
        "totalFaculty": total_faculty,
        "pendingFaculty": pending_faculty,
        "totalActivities": total_activities,
        "approvedActivities": approved_activities,
        "totalCertificates": total_certificates,
        "asOf": None,
    }


@router.get("/category-progress")
async def category_progress(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    # Group by activity type (as "category")
    stmt = (
        select(
            ActivityType.name.label("label"),
            func.count(ActivitySession.id).label("submitted"),
            func.sum(
                case((ActivitySession.status == ActivitySessionStatus.APPROVED, 1), else_=0)
            ).label("approved"),
        )
        .select_from(ActivitySession)
        .join(ActivityType, ActivityType.id == ActivitySession.activity_type_id)
        .group_by(ActivityType.name)
        .order_by(ActivityType.name.asc())
    )

    rows = (await db.execute(stmt)).all()

    # You can map color by name or keep default
    def color_for(name: str) -> str:
        n = (name or "").lower()
        if "nss" in n or "volunteer" in n:
            return "emerald"
        if "sports" in n:
            return "amber"
        if "culture" in n:
            return "pink"
        return "blue"

    return [
        {
            "label": r.label,
            "color": color_for(r.label),
            "submitted": int(r.submitted or 0),
            "approved": int(r.approved or 0),
        }
        for r in rows
    ]


@router.get("/student-progress")
async def student_progress(
    limit: int = Query(12, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    # activities per student + certificates per student
    # (simple version: count sessions + count certificates)
    act_stmt = (
        select(
            Student.id.label("id"),
            Student.name.label("name"),
            func.count(ActivitySession.id).label("activities"),
        )
        .select_from(Student)
        .join(ActivitySession, ActivitySession.student_id == Student.id, isouter=True)
        .group_by(Student.id, Student.name)
        .order_by(func.count(ActivitySession.id).desc())
        .limit(limit)
    )
    act_rows = (await db.execute(act_stmt)).all()

    student_ids = [r.id for r in act_rows]
    cert_map = {}
    if student_ids:
        cert_stmt = (
            select(Certificate.student_id, func.count(Certificate.id))
            .where(Certificate.student_id.in_(student_ids))
            .group_by(Certificate.student_id)
        )
        cert_rows = (await db.execute(cert_stmt)).all()
        cert_map = {sid: int(cnt or 0) for sid, cnt in cert_rows}

    return [
        {
            "id": r.id,
            "name": r.name,
            "activities": int(r.activities or 0),
            "certificates": cert_map.get(r.id, 0),
        }
        for r in act_rows
    ]


@router.get("/recent-submissions")
async def recent_submissions(
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    stmt = (
        select(
            ActivitySession.id,
            Student.name.label("student"),
            ActivityType.name.label("category"),
            ActivitySession.description.label("title"),
            ActivitySession.submitted_at.label("submittedOn"),
            ActivitySession.status.label("status"),
        )
        .select_from(ActivitySession)
        .join(Student, Student.id == ActivitySession.student_id)
        .join(ActivityType, ActivityType.id == ActivitySession.activity_type_id)
        .where(ActivitySession.submitted_at.isnot(None))
        .order_by(ActivitySession.submitted_at.desc(), ActivitySession.id.desc())
        .limit(limit)
    )

    rows = (await db.execute(stmt)).all()

    # certificate exists?
    ids = [r.id for r in rows]
    cert_set = set()
    if ids:
        cert_rows = await db.execute(select(Certificate.session_id).where(Certificate.session_id.in_(ids)))
        cert_set = set([x[0] for x in cert_rows.all()])

    return [
        {
            "id": r.id,
            "student": r.student,
            "title": (r.title or "Activity Submission"),
            "category": r.category,
            "submittedOn": r.submittedOn.isoformat() if r.submittedOn else None,
            "status": str(r.status),
            "certificate": (r.id in cert_set),
        }
        for r in rows
    ]