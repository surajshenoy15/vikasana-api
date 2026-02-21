from typing import Annotated, Literal
from pydantic import BaseModel, Field, StringConstraints, EmailStr


NameStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
USNStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=30)]
BranchStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]

StudentTypeStr = Literal["REGULAR", "DIPLOMA"]


class StudentCreate(BaseModel):
    name: NameStr
    usn: USNStr
    branch: BranchStr

    email: EmailStr | None = None
    student_type: StudentTypeStr = "REGULAR"

    passout_year: int = Field(..., ge=1990, le=2100)
    admitted_year: int = Field(..., ge=1990, le=2100)


class StudentOut(BaseModel):
    id: int
    name: str
    usn: str
    branch: str

    email: str | None
    student_type: str

    passout_year: int
    admitted_year: int

    model_config = {"from_attributes": True}


class BulkUploadResult(BaseModel):
    total_rows: int
    inserted: int
    skipped_duplicates: int
    invalid_rows: int
    errors: list[str] = []