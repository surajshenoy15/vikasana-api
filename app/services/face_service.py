import cv2
import numpy as np
import base64
import io
from pathlib import Path
from PIL import Image, ImageOps  # ✅ add pillow

MODEL_DIR        = Path(__file__).parent.parent / "models" / "face"
DETECTOR_MODEL   = str(MODEL_DIR / "face_detection_yunet_2023mar.onnx")
RECOGNIZER_MODEL = str(MODEL_DIR / "face_recognition_sface_2021dec.onnx")

COSINE_THRESHOLD = 0.3
L2_THRESHOLD     = 1.1

# ✅ Tunables
YUNET_SCORE_THRESHOLD = 0.45   # was 0.6 (too strict for many phone photos)
YUNET_NMS_THRESHOLD   = 0.3
YUNET_TOP_K           = 5000
MAX_DETECT_WIDTH      = 960    # ✅ downscale large phone images for stable detection


def _decode_image(image_b64: str) -> np.ndarray:
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]

    decoded = base64.b64decode(image_b64)
    if not decoded:
        raise ValueError("Image data is empty after base64 decode.")

    # ✅ Fix EXIF orientation (very important on mobile)
    try:
        pil = Image.open(io.BytesIO(decoded))
        pil = ImageOps.exif_transpose(pil)
        pil = pil.convert("RGB")
        img_rgb = np.array(pil)  # RGB
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        return img_bgr
    except Exception:
        # fallback to OpenCV decode
        buf = np.frombuffer(decoded, np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Cannot decode image. Send a valid JPEG or PNG.")
        return img


def _resize_for_detection(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    if w <= MAX_DETECT_WIDTH:
        return img
    scale = MAX_DETECT_WIDTH / float(w)
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _detect_faces(img_bgr: np.ndarray):
    # ✅ Stabilize detection on mobile photos
    det_img = _resize_for_detection(img_bgr)
    h, w = det_img.shape[:2]

    detector = cv2.FaceDetectorYN.create(
        DETECTOR_MODEL, "", (w, h),
        score_threshold=YUNET_SCORE_THRESHOLD,
        nms_threshold=YUNET_NMS_THRESHOLD,
        top_k=YUNET_TOP_K,
    )

    # ✅ Ensure detector input size matches current frame
    detector.setInputSize((w, h))

    _, faces = detector.detect(det_img)
    if faces is None or len(faces) == 0:
        return None, det_img, (w, h)

    return faces, det_img, (w, h)


def _get_recognizer():
    return cv2.FaceRecognizerSF.create(RECOGNIZER_MODEL, "")


def _scale_face_box_to_original(face_row, det_img, orig_img):
    """
    YuNet returns [x,y,w,h, ...] in det_img coordinates.
    If we resized, scale box back to orig image.
    """
    x, y, bw, bh = face_row[:4]
    det_h, det_w = det_img.shape[:2]
    orig_h, orig_w = orig_img.shape[:2]

    sx = orig_w / float(det_w)
    sy = orig_h / float(det_h)

    return np.array([x * sx, y * sy, bw * sx, bh * sy], dtype=np.float32)


def extract_embedding(image_b64: str) -> list:
    orig = _decode_image(image_b64)
    faces, det_img, _ = _detect_faces(orig)

    if faces is None or len(faces) == 0:
        raise ValueError("No face detected. Ensure good lighting and a clear front-facing photo.")

    # ✅ choose largest face
    largest = faces[np.argmax(faces[:, 2] * faces[:, 3])]

    # ✅ scale bbox back to original coordinates (important if resized)
    bbox = _scale_face_box_to_original(largest, det_img, orig)

    recognizer = _get_recognizer()

    # FaceRecognizerSF expects [x,y,w,h,...] style row; we can create a compatible row:
    # We only need first 4 values for alignCrop.
    face_row = np.zeros((15,), dtype=np.float32)
    face_row[:4] = bbox

    aligned   = recognizer.alignCrop(orig, face_row)
    embedding = recognizer.feature(aligned).flatten().tolist()
    return embedding


def average_embeddings(embeddings: list) -> list:
    arr  = np.array(embeddings, dtype=np.float32)
    avg  = arr.mean(axis=0)
    norm = np.linalg.norm(avg)
    return (avg / norm if norm > 0 else avg).tolist()


def match_in_group(group_image_b64: str, stored_embedding: list) -> dict:
    orig = _decode_image(group_image_b64)
    faces, det_img, _ = _detect_faces(orig)

    if faces is None or len(faces) == 0:
        return {
            "matched":          False,
            "reason":           "No faces detected in the group photo.",
            "cosine_score":     None,
            "l2_score":         None,
            "matched_face_box": None,
            "total_faces":      0,
        }

    recognizer  = _get_recognizer()
    stored      = np.array(stored_embedding, dtype=np.float32).reshape(1, -1)

    best_cosine = -1.0
    best_l2     = float("inf")
    best_box    = None

    for f in faces:
        try:
            bbox = _scale_face_box_to_original(f, det_img, orig)
            face_row = np.zeros((15,), dtype=np.float32)
            face_row[:4] = bbox

            aligned = recognizer.alignCrop(orig, face_row)
            emb     = recognizer.feature(aligned)

            cosine  = recognizer.match(stored, emb, cv2.FaceRecognizerSF_FR_COSINE)
            l2      = recognizer.match(stored, emb, cv2.FaceRecognizerSF_FR_NORM_L2)

            if cosine > best_cosine:
                best_cosine = float(cosine)
                best_l2     = float(l2)
                best_box    = bbox.astype(int).tolist()
        except Exception:
            continue

    matched = (best_cosine >= COSINE_THRESHOLD) and (best_l2 <= L2_THRESHOLD)

    return {
        "matched":          matched,
        "cosine_score":     round(best_cosine, 4) if best_cosine != -1.0 else None,
        "l2_score":         round(best_l2, 4) if best_l2 != float("inf") else None,
        "cosine_threshold": COSINE_THRESHOLD,
        "matched_face_box": best_box if matched else None,
        "total_faces":      int(len(faces)),
        "reason":           "Match found" if matched else f"Best cosine {best_cosine:.4f} < threshold {COSINE_THRESHOLD}",
    }