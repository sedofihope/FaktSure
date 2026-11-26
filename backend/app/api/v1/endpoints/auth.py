from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.core.permissions import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Authenticate an active user and issue a JWT."""

    normalized_email = payload.email.lower()
    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None or not verify_password(payload.password, user.password_hash):
        db.add(AuditLog(
            user_id=user.id if user else None,
            action="LOGIN_FAILED",
            entity_type="User",
            entity_id=str(user.public_id) if user else normalized_email,
        ))
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        db.add(AuditLog(
            user_id=user.id,
            action="LOGIN_FAILED",
            entity_type="User",
            entity_id=str(user.public_id),
            new_value="inactive account",
        ))
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    db.add(AuditLog(
        user_id=user.id,
        action="LOGIN_SUCCEEDED",
        entity_type="User",
        entity_id=str(user.public_id),
    ))
    db.commit()
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> User:
    """Return the currently authenticated user."""

    return user
