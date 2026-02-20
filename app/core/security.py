from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.context import CryptContext
from app.core.config import settings

# ── Bcrypt Password Hashing ───────────────────────────────────────────
# "deprecated=auto" → old hashes are silently re-hashed on next login
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """
    Hash a plaintext password with bcrypt.
    bcrypt automatically generates a unique salt — same password gives
    a different hash each time, which is correct and expected.
    """
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """
    Timing-safe comparison.
    Takes the same time whether the password is right or wrong.
    This prevents attackers from measuring response time to guess passwords.
    """
    return pwd_context.verify(plain, hashed)


# ── JWT Token ─────────────────────────────────────────────────────────
def create_access_token(admin_id: int, email: str) -> str:
    """
    Creates a signed JWT. Change SECRET_KEY in .env to invalidate all tokens.
    Change ACCESS_TOKEN_EXPIRE_MINUTES in .env to adjust session length.

    Payload contains:
      sub   — admin ID (standard JWT claim)
      email — for frontend display
      type  — guards against using wrong token types
      iat   — issued at
      exp   — expiry (set by ACCESS_TOKEN_EXPIRE_MINUTES in .env)
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub":   str(admin_id),
        "email": email,
        "type":  "access",
        "iat":   now,
        "exp":   now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decodes and verifies JWT signature + expiry.
    Raises jose.JWTError on any failure.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
