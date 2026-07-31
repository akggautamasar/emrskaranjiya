import hmac
import os

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme123")

COOKIE_NAME = "payroll_admin_session"
MAX_AGE_SECONDS = 60 * 60 * 8  # 8 hours

_serializer = URLSafeTimedSerializer(SECRET_KEY)


def check_password(password: str) -> bool:
    return hmac.compare_digest(password or "", ADMIN_PASSWORD)


def create_session_token() -> str:
    return _serializer.dumps({"admin": True})


def is_admin(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    try:
        data = _serializer.loads(token, max_age=MAX_AGE_SECONDS)
        return bool(data.get("admin"))
    except (BadSignature, SignatureExpired):
        return False
