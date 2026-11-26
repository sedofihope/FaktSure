from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""

    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""

    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str) -> str:
    """Create a signed JWT access token for a user id."""

    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    """Decode a JWT and return its subject or raise JWTError."""

    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    subject = payload.get("sub")
    if not subject:
        raise JWTError("Token has no subject")
    return str(subject)
