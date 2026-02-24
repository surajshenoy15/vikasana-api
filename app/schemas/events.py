from pydantic import BaseModel, Field
from typing import Optional


class EventCreateIn(BaseModel):
    title: str
    description: Optional[str] = None
    required_photos: int = Field(3, ge=3, le=5)


class EventOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    required_photos: int
    is_active: bool

    class Config:
        from_attributes = True


class RegisterOut(BaseModel):
    submission_id: int
    status: str


class PhotoOut(BaseModel):
    id: int
    submission_id: int
    seq_no: int
    image_url: str

    class Config:
        from_attributes = True


class FinalSubmitIn(BaseModel):
    description: str


class SubmissionOut(BaseModel):
    id: int
    event_id: int
    status: str
    description: Optional[str]

    class Config:
        from_attributes = True