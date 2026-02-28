import hmac, hashlib
from app.core.config import settings

def sign_cert(cert_id: int) -> str:
    key = settings.CERT_SIGNING_SECRET.encode("utf-8")
    msg = str(cert_id).encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()

def verify_sig(cert_id: int, sig: str) -> bool:
    return hmac.compare_digest(sign_cert(cert_id), sig)