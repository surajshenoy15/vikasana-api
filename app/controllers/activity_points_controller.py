from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_photo import ActivityPhoto
from app.models.activity_session import ActivitySession, ActivitySessionStatus
from app.models.activity_type import ActivityType
from app.models.student import Student
from app.models.student_activity_progress import StudentActivityProgress


async def award_points_for_session(db: AsyncSession, session_id: int) -> dict:
    # 1) Load + lock session (prevents double-award in concurrent calls)
    res = await db.execute(
        select(ActivitySession)
        .where(ActivitySession.id == session_id)
        .with_for_update()
    )
    session = res.scalar_one_or_none()
    if not session:
        raise ValueError("Session not found")

    # Only award when session is SUBMITTED or APPROVED
    if session.status not in {ActivitySessionStatus.SUBMITTED, ActivitySessionStatus.APPROVED}:
        return {"awarded": 0, "reason": f"Session status is {session.status}, not eligible"}

    # 2) Get photos seq 1 and seq 5
    q = (
        select(ActivityPhoto)
        .where(
            ActivityPhoto.session_id == session_id,
            ActivityPhoto.seq_no.in_([1, 5]),
        )
    )
    rows = (await db.execute(q)).scalars().all()
    p1 = next((p for p in rows if p.seq_no == 1), None)
    p5 = next((p for p in rows if p.seq_no == 5), None)

    if not p1 or not p5:
        return {"awarded": 0, "reason": "Missing seq 1 or seq 5 photo"}

    t1 = p1.captured_at or p1.created_at
    t5 = p5.captured_at or p5.created_at

    if not t1 or not t5 or t5 <= t1:
        return {"awarded": 0, "reason": "Invalid timestamps for duration"}

    # 3) Duration in minutes
    duration_minutes = int((t5 - t1).total_seconds() // 60)
    if duration_minutes <= 0:
        return {"awarded": 0, "reason": "Duration too small"}

    # Store duration in session (optional but useful)
    session.duration_hours = round(duration_minutes / 60.0, 2)

    # 4) Load activity rule
    activity_type = await db.get(ActivityType, session.activity_type_id)
    if not activity_type or not getattr(activity_type, "is_active", True):
        return {"awarded": 0, "reason": "Activity type not active"}

    unit_minutes = int(activity_type.hours_per_unit * 60)
    unit_points = int(activity_type.points_per_unit)
    max_points = int(activity_type.max_points)

    if unit_minutes <= 0 or unit_points <= 0:
        return {"awarded": 0, "reason": "Invalid activity rule config"}

    # 5) Get or create progress row (lock it)
    prog_q = (
        select(StudentActivityProgress)
        .where(
            StudentActivityProgress.student_id == session.student_id,
            StudentActivityProgress.activity_type_id == session.activity_type_id,
        )
        .with_for_update()
    )
    prog = (await db.execute(prog_q)).scalars().first()

    if not prog:
        prog = StudentActivityProgress(
            student_id=session.student_id,
            activity_type_id=session.activity_type_id,
            total_minutes=0,
            points_awarded=0,
        )
        db.add(prog)
        await db.flush()

    prog.total_minutes = int(prog.total_minutes or 0) + duration_minutes

    # 6) Compute points that should exist after update (respect max_points)
    should_have = (prog.total_minutes // unit_minutes) * unit_points
    if should_have > max_points:
        should_have = max_points

    new_points = should_have - int(prog.points_awarded or 0)
    if new_points < 0:
        new_points = 0

    # 7) Apply delta to student total (lock student row too)
    if new_points > 0:
        stu_q = select(Student).where(Student.id == session.student_id).with_for_update()
        student = (await db.execute(stu_q)).scalars().first()
        if not student:
            raise ValueError("Student not found")

        student.total_points_earned = int(student.total_points_earned or 0) + int(new_points)
        prog.points_awarded = should_have

    # ✅ DO NOT COMMIT HERE — caller (admin_approve_session) commits

    return {
        "awarded": int(new_points),
        "duration_minutes": duration_minutes,
        "total_minutes": int(prog.total_minutes),
        "points_awarded_total_for_activity": int(prog.points_awarded),
        "student_total_points": None,  # you can return student.total_points_earned if you want
    }