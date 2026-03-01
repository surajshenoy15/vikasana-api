# =========================================================
# app/schemas/events.py  ✅ FULL UPDATED (WITH LOCATION + ACTIVITY TYPES)
# =========================================================


from typing import Optional, List
from datetime import datetime, date, time
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Any
from datetime import date, time
from pydantic.config import ConfigDict


# ------------------ EVENTS ------------------

class EventCreateIn(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    title: str
    description: Optional[str] = None
    required_photos: int = Field(3, ge=3, le=5)
    event_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    thumbnail_url: Optional[str] = None

    venue_name: Optional[str] = None
    maps_url: Optional[str] = None

    # ✅ Always end up as List[int]
    activity_type_ids: List[int] = Field(default_factory=list)

    # ✅ Pull ids from alternate frontend keys BEFORE validation
    @model_validator(mode="before")
    @classmethod
    def _normalize_activity_keys(cls, data: Any):
        if not isinstance(data, dict):
            return data

        # If frontend sends activityTypeIds / activityTypes / activity_types etc.
        if "activity_type_ids" not in data or not data.get("activity_type_ids"):
            for k in ["activityTypeIds", "activityTypes", "activity_types", "activity_type_id", "activity_list"]:
                if k in data and data.get(k) is not None:
                    data["activity_type_ids"] = data.get(k)
                    break

        return data

    # ✅ Convert any shape -> List[int]
    @field_validator("activity_type_ids", mode="before")
    @classmethod
    def _coerce_activity_type_ids(cls, v: Any):
        if v is None:
            return []

        # "6,7"
        if isinstance(v, str):
            parts = [x.strip() for x in v.split(",") if x.strip()]
            out = []
            for x in parts:
                try:
                    out.append(int(x))
                except Exception:
                    pass
            return out

        # single int
        if isinstance(v, int):
            return [v]

        # list of dicts: [{id: 6}, {id: 7}]
        if isinstance(v, list) and v and isinstance(v[0], dict):
            out = []
            for obj in v:
                try:
                    out.append(int(obj.get("id")))
                except Exception:
                    pass
            return out

        # list of strings/ints: ["6","7"] or [6,7]
        if isinstance(v, list):
            out = []
            for x in v:
                try:
                    out.append(int(x))
                except Exception:
                    pass
            return out

        return []

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