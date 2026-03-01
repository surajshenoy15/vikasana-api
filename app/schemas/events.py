# =========================================================
# app/schemas/events.py  ✅ FULL UPDATED (WITH LOCATION + ACTIVITY TYPES)
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

    venue_name: Optional[str] = None
    maps_url: Optional[str] = None

    # ✅ accept multiple frontend field names
    activity_type_ids: List[int] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "activity_type_ids",
            "activityTypeIds",
            "activityTypes",
            "activity_types",
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_activity_ids(cls, data: Any):
        if not isinstance(data, dict):
            return data

        raw = (
            data.get("activity_type_ids")
            or data.get("activityTypeIds")
            or data.get("activityTypes")
            or data.get("activity_types")
            or []
        )

        # supports [{id: 6}, {id: 7}]
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            raw = [x.get("id") for x in raw]

        # supports "6,7"
        if isinstance(raw, str):
            raw = [x.strip() for x in raw.split(",") if x.strip()]

        ids: List[int] = []
        if isinstance(raw, list):
            for x in raw:
                try:
                    v = int(x)
                    if v > 0:
                        ids.append(v)
                except Exception:
                    pass

        data["activity_type_ids"] = sorted(set(ids))
        return data


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

    # NOTE:
    # We don't force EventOut to include activity_type_ids,
    # because Event table doesn't store it directly (mapping table does).
    # If you want it in response, we can create a separate EventOutAdmin schema.

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

    # ✅ Face/flag meta
    face_matched: Optional[bool] = None
    face_reason: Optional[str] = None
    cosine_score: Optional[float] = None
    flag_reason: Optional[str] = None

    class Config:
        from_attributes = True


class RejectIn(BaseModel):
    reason: str