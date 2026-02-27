# =========================================================
# app/schemas/events.py  ✅ FULL UPDATED (WITH LOCATION)
# =========================================================
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date, time


# ------------------ EVENTS ------------------

class EventCreateIn(BaseModel):
    title: str
    description: Optional[str] = None
    required_photos: int = Field(3, ge=3, le=5)
    event_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    thumbnail_url: Optional[str] = None

    # ✅ NEW (Location)
    venue_name: Optional[str] = None
    maps_url: Optional[str] = None


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

    # ✅ NEW (Location)
    venue_name: Optional[str] = None
    maps_url: Optional[str] = None

    class Config:
        from_attributes = True


class ThumbnailUploadUrlIn(BaseModel):
    filename: str
    content_type: str


class ThumbnailUploadUrlOut(BaseModel):
    upload_url: str
    public_url: str


# ------------------ REGISTRATION ------------------

class RegisterOut(BaseModel):
    submission_id: int
    status: str


# ------------------ PHOTOS ------------------

class PhotoOut(BaseModel):
    id: int
    session_id: int
    student_id: int
    seq_no: int
    image_url: str
    captured_at: datetime
    lat: float
    lng: float

    class Config:
        from_attributes = True


class PhotosUploadOut(BaseModel):
    session_id: int
    photos: List[PhotoOut]


# ------------------ SUBMISSION ------------------

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

    # ✅ ADD THESE
    face_matched: Optional[bool] = None
    face_reason: Optional[str] = None
    cosine_score: Optional[float] = None
    flag_reason: Optional[str] = None

    class Config:
        from_attributes = True


class RejectIn(BaseModel):
    reason: str