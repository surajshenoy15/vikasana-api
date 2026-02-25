from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import base64
import cv2
import numpy as np

from app.core.database import get_db
from app.models.student import Student
from app.models.student_face_embedding import StudentFaceEmbedding
from app.models.activity_session import ActivitySession, ActivitySessionStatus
from app.models.activity_photo import ActivityPhoto

# rename to avoid confusion with "service layer"
from app.services import face_service as cv_face_service


router = APIRouter(prefix="/face", tags=["Face Recognition"])


def file_to_b64(file_bytes: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(file_bytes).decode()


def draw_box(image_bytes: bytes, face_box: list | None, matched: bool) -> bytes:
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
# ENROLL FACE (CURRENT: 3-5 selfies averaged)
# NOTE: if you need strict 5 angles, tell me — I'll change API to pose-based.
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
            detail=f"Only {len(embeddings)} valid faces found.",
        )

    avg_embedding = cv_face_service.average_embeddings(embeddings)

    stmt = select(StudentFaceEmbedding).where(StudentFaceEmbedding.student_id == student_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if record:
        record.set_embedding(avg_embedding)
        record.photo_count = len(embeddings)
    else:
        record = StudentFaceEmbedding(
            student_id=student_id,
            photo_count=len(embeddings),
        )
        record.set_embedding(avg_embedding)
        db.add(record)

    student.face_enrolled = True
    student.face_enrolled_at = datetime.utcnow()

    return {
        "success": True,
        "photos_processed": len(embeddings),
        "photos_failed": failed,
    }


# --------------------------------------------------
# VERIFY ACTIVITY SESSION (flags session on mismatch)
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

    stmt = select(ActivityPhoto).where(ActivityPhoto.session_id == session_id).order_by(ActivityPhoto.captured_at.desc())
    result = await db.execute(stmt)
    photo = result.scalars().first()
    if not photo:
        raise HTTPException(status_code=400, detail="No activity photo found.")

    # YOU implement this
    image_bytes = await read_image_bytes(photo.image_url)

    match = cv_face_service.match_in_group(
        file_to_b64(image_bytes),
        record.get_embedding(),
    )

    # Create annotated image bytes (for admin view)
    annotated_bytes = draw_box(
        image_bytes,
        match.get("matched_face_box") if match.get("matched") else None,
        bool(match.get("matched")),
    )

    # OPTIONAL: store annotated image and save its URL for admin (recommended)
    # annotated_url = await save_processed_image_and_get_url(annotated_bytes, session_id, photo.id)
    # (add to DB via ActivityFaceCheck model later)

    if match["matched"]:
        return {
            "matched": True,
            "cosine_score": match.get("cosine_score"),
            "l2_score": match.get("l2_score"),
            "total_faces": match.get("total_faces"),
        }

    session.status = ActivitySessionStatus.FLAGGED
    session.flag_reason = f"Face mismatch: {match.get('reason')}"

    return {
        "matched": False,
        "reason": match.get("reason"),
        "cosine_score": match.get("cosine_score"),
        "l2_score": match.get("l2_score"),
        "total_faces": match.get("total_faces"),
    }


async def read_image_bytes(image_url: str) -> bytes:
    """
    Implement based on your storage (MinIO/S3/local).
    """
    raise NotImplementedError