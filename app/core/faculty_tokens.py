import os
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from itsdangerous import URLSafeTimedSerializer


def _serializer() -> URLSafeTimedSerializer:
    secret = os.getenv("ACTIVATION_TOKEN_SECRET", "change-me")
    return URLSafeTimedSerializer(secret_key=secret, salt="faculty-activation")


def create_activation_token(email: str) -> str:
    s = _serializer()
    return s.dumps({"email": email})


def hash_token(token: str) -> str:
    # Store only hash in DB
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, max_age_seconds: int) -> dict:
    s = _serializer()
    return s.loads(token, max_age=max_age_seconds)


def activation_expiry_dt() -> datetime:
    hours = int(os.getenv("ACTIVATION_TOKEN_EXPIRE_HOURS", "48"))
    return datetime.now(timezone.utc) + timedelta(hours=hours)