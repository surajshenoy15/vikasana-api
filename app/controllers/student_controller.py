import os
import csv
import io
from typing import List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.student import Student, StudentType
from app.schemas.student import StudentCreate
from app.core.email_service import send_student_welcome_email


def _clean(v: str) -> str:
    return (v or "").strip()


def _parse_student_type(v: str) -> StudentType:
    x = (v or "").strip().upper()
    if x in ("DIPLOMA", "DIPLOMA_SCHEME", "DIPLOMA SCHEME"):
        return StudentType.DIPLOMA
    return StudentType.REGULAR


async def create_student(db: AsyncSession, payload: StudentCreate, faculty_college: str) -> Student:
    faculty_college = (faculty_college or "").strip()
    if not faculty_college:
        raise ValueError("Faculty college is missing. Please set faculty.college.")

    # ✅ duplicate by USN within same college
    existing = await db.execute(
        select(Student).where(Student.usn == payload.usn, Student.college == faculty_college)
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"Duplicate USN in this college: {payload.usn}")

    # ✅ duplicate by email within same college (only if provided)
    if payload.email:
        e2 = await db.execute(
            select(Student).where(Student.email == str(payload.email), Student.college == faculty_college)
        )
        if e2.scalar_one_or_none():
            raise ValueError(f"Duplicate Email in this college: {payload.email}")

    s = Student(
        college=faculty_college,  # ✅ enforce from faculty, not from client
        name=payload.name.strip(),
        usn=payload.usn.strip(),
        branch=payload.branch.strip(),
        email=str(payload.email) if payload.email else None,
        student_type=StudentType(payload.student_type),
        passout_year=payload.passout_year,
        admitted_year=payload.admitted_year,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)

    # ✅ Send welcome email (non-blocking failure)
    if s.email:
        try:
            app_url = os.getenv("STUDENT_APP_DOWNLOAD_URL", "https://vikasana.org/app")
            await send_student_welcome_email(to_email=s.email, to_name=s.name, app_download_url=app_url)
        except Exception as e:
            print(f"[WARN] Student welcome email not sent for {s.email}: {e}")

    return s


async def create_students_from_csv(
    db: AsyncSession,
    csv_bytes: bytes,
    skip_duplicates: bool = True,
    *,
    faculty_college: str,
) -> Tuple[int, int, int, int, List[str]]:
    """
    CSV headers expected (required):
      name, usn, branch, passout_year, admitted_year
    Optional:
      email, student_type
    """
    faculty_college = (faculty_college or "").strip()
    if not faculty_college:
        return (0, 0, 0, 0, ["Faculty college is missing. Please set faculty.college."])

    errors: List[str] = []
    inserted = 0
    skipped = 0
    invalid = 0

    try:
        text = csv_bytes.decode("utf-8-sig")
    except Exception:
        text = csv_bytes.decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    required = {"name", "usn", "branch", "passout_year", "admitted_year"}

    if not reader.fieldnames:
        return (0, 0, 0, 0, ["CSV has no headers. Required: name, usn, branch, passout_year, admitted_year"])

    headers = set([h.strip() for h in reader.fieldnames])
    missing = required - headers
    if missing:
        return (0, 0, 0, 0, [f"Missing headers: {', '.join(sorted(missing))}"])

    rows = list(reader)
    total_rows = len(rows)

    for idx, row in enumerate(rows, start=2):
        try:
            name = _clean(row.get("name"))
            usn = _clean(row.get("usn"))
            branch = _clean(row.get("branch"))
            passout_year = int(_clean(row.get("passout_year")))
            admitted_year = int(_clean(row.get("admitted_year")))

            email = _clean(row.get("email")) if "email" in headers else ""
            stype = _clean(row.get("student_type")) if "student_type" in headers else ""

            if not name or not usn or not branch:
                raise ValueError("name/usn/branch cannot be empty")

            # ✅ dup USN within same college
            res = await db.execute(
                select(Student).where(Student.usn == usn, Student.college == faculty_college)
            )
            if res.scalar_one_or_none():
                if skip_duplicates:
                    skipped += 1
                    continue
                raise ValueError(f"Duplicate USN in this college: {usn}")

            # ✅ dup Email within same college
            if email:
                res2 = await db.execute(
                    select(Student).where(Student.email == email, Student.college == faculty_college)
                )
                if res2.scalar_one_or_none():
                    if skip_duplicates:
                        skipped += 1
                        continue
                    raise ValueError(f"Duplicate Email in this college: {email}")

            s = Student(
                college=faculty_college,  # ✅ enforce from faculty
                name=name,
                usn=usn,
                branch=branch,
                email=email or None,
                student_type=_parse_student_type(stype),
                passout_year=passout_year,
                admitted_year=admitted_year,
            )
            db.add(s)
            inserted += 1

        except Exception as e:
            invalid += 1
            errors.append(f"Row {idx}: {str(e)}")

    await db.commit()
    return (total_rows, inserted, skipped, invalid, errors)