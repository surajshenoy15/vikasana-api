from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime 
from datetime import date, time
from typing import List


class EventCreateIn(BaseModel):
    title: str
    description: Optional[str] = None
    required_photos: int = Field(3, ge=3, le=5)
    event_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    thumbnail_url: Optional[str] = None


class EventOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    required_photos: int
    is_active: bool
    event_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    thumbnail_url: Optional[str] = None

    class Config:
        from_attributes = True

class ThumbnailUploadUrlIn(BaseModel):
    filename: str
    content_type: str

class ThumbnailUploadUrlOut(BaseModel):
    upload_url: str
    public_url: str


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

class AdminSubmissionOut(BaseModel):
    id: int
    event_id: int
    student_id: int
    status: str
    description: Optional[str] = None
    submitted_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None

    class Config:
        from_attributes = True


class RejectIn(BaseModel):
    reason: str


class PhotosUploadOut(BaseModel):
    session_id: int
    photos: List[PhotoOut]