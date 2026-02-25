from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import base64
import uuid
from io import BytesIO
import anyio

from minio import Minio

from app.core.database import get_db
from app.core.config import settings
from app.models.student import Student
from app.models.student_face_embedding import StudentFaceEmbedding
from app.models.activity_session import ActivitySession, ActivitySessionStatus
from app.models.activity_photo import ActivityPhoto
from app.models.activity_face_check import ActivityFaceCheck

# OpenCV face recognition module
from app.services import face_service as cv_face_service


router = APIRouter(prefix="/face", tags=["Face Recognition"])


# -----------------------------
# MinIO Client (sync client, called in thread)
# -----------------------------
minio_client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_SECURE,
)


# -----------------------------
# Helpers
# -----------------------------
def file_to_b64(file_bytes: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(file_bytes).decode()


def _extract_object_key(image_url: str) -> str:
    """
    Accepts:
    - "folder/file.jpg" (preferred)
    - "http://host:9000/bucket/folder/file.jpg"
    - "bucket/folder/file.jpg"
    Returns "folder/file.jpg" key.
    """
    s = (image_url or "").strip()
    if not s:
        raise ValueError("Empty image_url")

    s = s.replace("\\", "/")

    # If full URL, remove protocol+domain
    if "://" in s:
        # split after domain
        parts = s.split("://", 1)[1].split("/", 1)
        if len(parts) == 2:
            s = parts[1]  # now "bucket/key..."

    # If starts with bucket name, strip it
    for b in [getattr(settings, "MINIO_BUCKET_ACTIVITIES", ""), getattr(settings, "MINIO_FACE_BUCKET", "")]:
        if b and (s == b or s.startswith(b + "/")):
            s = s[len(b):].lstrip("/")
            break

    return s


async def read_image_bytes_from_minio(object_key_or_url: str) -> bytes:
    bucket = settings.MINIO_BUCKET_ACTIVITIES  # your activity-uploads
    object_name = _extract_object_key(object_key_or_url)

    def _read():
        resp = minio_client.get_object(bucket, object_name)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    return await anyio.to_thread.run_sync(_read)


async def save_boxed_image_to_minio(image_bytes: bytes, session_id: int, photo_id: int) -> str:
    """
    Saves annotated image into MINIO_FACE_BUCKET and returns object key.
    """
    bucket = settings.MINIO_FACE_BUCKET  # face-verification
    object_name = f"{session_id}/{photo_id}_boxed_{uuid.uuid4().hex}.jpg"

    def _put():
        minio_client.put_object(
            bucket,
            object_name,
            BytesIO(image_bytes),
            length=len(image_bytes),
            content_type="image/jpeg",
        )

    await anyio.to_thread.run_sync(_put)
    return object_name


def draw_box(image_bytes: bytes, face_box: list | None, matched: bool) -> bytes:
    import cv2
    import numpy as np

    np_arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if img is None:
        return image_bytes

    if matched and face_box:
        x, y, w, h = face_box
        color = (0, 255, 0)
        label = "STUDENT"

        cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
        (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(img, (x, y - text_h - 10), (x + text_w, y), color, -1)
        cv2.putText(img, label, (x, y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    elif not matched:
        cv2.putText(img, "STUDENT NOT FOUND", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    _, buffer = cv2.imencode(".jpg", img)
    return buffer.tobytes()


# --------------------------------------------------
# ENROLL FACE (3–5 selfies averaged)
# --------------------------------------------------
@router.post("/enroll/{student_id}")
async def enroll_face(
    student_id: int,
    images: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    if len(images) < 3 or len(images) > 5:
        raise HTTPException(status_code=422, detail="Upload 3 to 5 selfies.")

    student = await db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    embeddings = []
    failed = 0

    for img in images:
        contents = await img.read()
        if not contents:
            failed += 1
            continue
        try:
            emb = cv_face_service.extract_embedding(file_to_b64(contents))
            embeddings.append(emb)
        except Exception:
            failed += 1

    if len(embeddings) < 3:
        raise HTTPException(
            status_code=422,
            detail=f"Only {len(embeddings)} valid faces found (need >= 3). Failed={failed}.",
        )

    avg_embedding = cv_face_service.average_embeddings(embeddings)

    stmt = select(StudentFaceEmbedding).where(StudentFaceEmbedding.student_id == student_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if record:
        record.set_embedding(avg_embedding)
        record.photo_count = len(embeddings)
        record.updated_at = datetime.utcnow()
    else:
        record = StudentFaceEmbedding(student_id=student_id, photo_count=len(embeddings))
        record.set_embedding(avg_embedding)
        db.add(record)

    student.face_enrolled = True
    student.face_enrolled_at = datetime.utcnow()

    # ✅ persist
    await db.commit()
    await db.refresh(student)

    return {
        "success": True,
        "student_id": student_id,
        "photos_processed": len(embeddings),
        "photos_failed": failed,
    }

# --------------------------------------------------
# VERIFY ACTIVITY SESSION (downloads from MinIO, saves boxed to MinIO)
# --------------------------------------------------
@router.post("/verify-session/{session_id}")
async def verify_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(ActivitySession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    student = await db.get(Student, session.student_id)
    if not student or not student.face_enrolled:
        raise HTTPException(status_code=400, detail="Student face not enrolled.")

    stmt = select(StudentFaceEmbedding).where(StudentFaceEmbedding.student_id == student.id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="No face record found.")

    stmt = (
        select(ActivityPhoto)
        .where(ActivityPhoto.session_id == session_id)
        .order_by(ActivityPhoto.captured_at.desc())
    )
    result = await db.execute(stmt)
    photo = result.scalars().first()
    if not photo:
        raise HTTPException(status_code=400, detail="No activity photo found.")

    # ✅ Strong validation (optional but recommended)
    if hasattr(photo, "student_id") and photo.student_id is not None and photo.student_id != session.student_id:
        raise HTTPException(status_code=400, detail="photo.student_id does not match session.student_id")

    # 1) Download original photo from activity bucket
    try:
        image_bytes = await read_image_bytes_from_minio(photo.image_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read activity image from MinIO: {str(e)}")

    # 2) Match
    match = cv_face_service.match_in_group(
        file_to_b64(image_bytes),
        record.get_embedding(),
    )

    matched = bool(match.get("matched"))
    face_box = match.get("matched_face_box") if matched else None

    # 3) Create boxed image (always create)
    boxed_bytes = draw_box(image_bytes, face_box, matched)

    # 4) Save boxed image to MINIO_FACE_BUCKET
    processed_object = None
    try:
        processed_object = await save_boxed_image_to_minio(
            boxed_bytes, session_id=session.id, photo_id=photo.id
        )
    except Exception:
        processed_object = None

    # ✅ 5) UPSERT RESULT INTO DB (activity_face_checks)
    existing_stmt = select(ActivityFaceCheck).where(
        ActivityFaceCheck.session_id == session.id,
        ActivityFaceCheck.photo_id == photo.id,
    )
    existing_res = await db.execute(existing_stmt)
    face_check = existing_res.scalar_one_or_none()

    if face_check:
        # update existing
        face_check.student_id = session.student_id  # ✅ REQUIRED
        face_check.matched = matched
        face_check.cosine_score = match.get("cosine_score")
        face_check.l2_score = match.get("l2_score")
        face_check.total_faces = match.get("total_faces")
        face_check.processed_object = processed_object
        face_check.reason = match.get("reason")
    else:
        # create new
        face_check = ActivityFaceCheck(
            student_id=session.student_id,  # ✅ FIXED (no more NULL)
            session_id=session.id,
            photo_id=photo.id,
            matched=matched,
            cosine_score=match.get("cosine_score"),
            l2_score=match.get("l2_score"),
            total_faces=match.get("total_faces"),
            processed_object=processed_object,
            reason=match.get("reason"),
        )
        db.add(face_check)
        await db.flush()  # get face_check.id

    # OPTIONAL: only if you added latest_face_check_id column in activity_sessions
    if hasattr(session, "latest_face_check_id"):
        session.latest_face_check_id = face_check.id

    # If failed → FLAG SESSION
    if not matched:
        session.status = ActivitySessionStatus.FLAGGED
        session.flag_reason = f"Face mismatch: {match.get('reason')}"

    # ✅ Commit changes
    await db.commit()
    await db.refresh(face_check)

    return {
        "matched": matched,
        "cosine_score": match.get("cosine_score"),
        "l2_score": match.get("l2_score"),
        "total_faces": match.get("total_faces"),
        "processed_object": processed_object,
        "face_check_id": face_check.id,
        "reason": match.get("reason"),
    }