import csv
import io
from typing import List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.student import Student
from app.schemas.student import StudentCreate


def _clean(v: str) -> str:
    return (v or "").strip()


async def create_student(db: AsyncSession, payload: StudentCreate) -> Student:
    # check duplicate by USN
    existing = await db.execute(select(Student).where(Student.usn == payload.usn))
    if existing.scalar_one_or_none():
        raise ValueError(f"Duplicate USN: {payload.usn}")

    s = Student(
        name=payload.name.strip(),
        usn=payload.usn.strip(),
        branch=payload.branch.strip(),
        passout_year=payload.passout_year,
        admitted_year=payload.admitted_year,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def create_students_from_csv(
    db: AsyncSession,
    csv_bytes: bytes,
    skip_duplicates: bool = True,
) -> Tuple[int, int, int, int, List[str]]:
    """
    Returns:
      total_rows, inserted, skipped_duplicates, invalid_rows, errors
    CSV headers expected:
      name, usn, branch, passout_year, admitted_year
    """
    errors: List[str] = []
    inserted = 0
    skipped = 0
    invalid = 0

    # read csv safely
    try:
        text = csv_bytes.decode("utf-8-sig")  # handles UTF-8 with BOM also
    except Exception:
        text = csv_bytes.decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    required = {"name", "usn", "branch", "passout_year", "admitted_year"}

    if not reader.fieldnames:
        return (0, 0, 0, 0, ["CSV has no headers. Required headers: name, usn, branch, passout_year, admitted_year"])

    missing = required - set([h.strip() for h in reader.fieldnames])
    if missing:
        return (0, 0, 0, 0, [f"Missing headers: {', '.join(sorted(missing))}"])

    rows = list(reader)
    total_rows = len(rows)

    for idx, row in enumerate(rows, start=2):  # 1 is header row
        try:
            name = _clean(row.get("name"))
            usn = _clean(row.get("usn"))
            branch = _clean(row.get("branch"))
            passout_year = int(_clean(row.get("passout_year")))
            admitted_year = int(_clean(row.get("admitted_year")))

            if not name or not usn or not branch:
                raise ValueError("name/usn/branch cannot be empty")

            # duplicate check
            res = await db.execute(select(Student).where(Student.usn == usn))
            if res.scalar_one_or_none():
                if skip_duplicates:
                    skipped += 1
                    continue
                raise ValueError(f"Duplicate USN: {usn}")

            s = Student(
                name=name,
                usn=usn,
                branch=branch,
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