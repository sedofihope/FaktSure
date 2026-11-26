from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_roles
from app.core.security import hash_password
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles("ADMIN")),
):
    """List users without exposing password hashes."""

    return list(db.scalars(select(User).order_by(User.id)))


@router.post("", response_model=UserResponse, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("ADMIN")),
):
    """Create an account; public registration is intentionally disabled."""

    user = User(
        full_name=payload.full_name.strip(),
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        db.flush()
        db.add(AuditLog(
            user_id=admin.id,
            action="USER_CREATED",
            entity_type="User",
            entity_id=str(user.public_id),
            new_value=f"role={user.role}",
        ))
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A user with this email already exists") from exc
    return user


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles("ADMIN")),
):
    user = db.scalar(select(User).where(User.public_id == user_id))
    if user is None:
        raise NotFoundError("User not found")
    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("ADMIN")),
):
    user = db.scalar(select(User).where(User.public_id == user_id))
    if user is None:
        raise NotFoundError("User not found")
    changes = payload.model_dump(exclude_unset=True)
    if user.id == admin.id and changes.get("is_active") is False:
        raise ConflictError("An administrator cannot deactivate their own account")
    if any(value is None for value in changes.values()):
        raise ConflictError("User update values cannot be null")

    resulting_role = changes.get("role", user.role)
    resulting_active = changes.get("is_active", user.is_active)
    if user.role == "ADMIN" and user.is_active and (
        resulting_role != "ADMIN" or not resulting_active
    ):
        active_admins = db.scalar(
            select(func.count(User.id)).where(User.role == "ADMIN", User.is_active.is_(True))
        )
        if active_admins <= 1:
            raise ConflictError("The last active administrator cannot be removed")

    previous_value = f"role={user.role},active={user.is_active}"
    for field, value in changes.items():
        setattr(user, field, value)
    db.add(AuditLog(
        user_id=admin.id,
        action="USER_UPDATED",
        entity_type="User",
        entity_id=str(user.public_id),
        previous_value=previous_value,
        new_value=f"role={user.role},active={user.is_active}",
    ))
    db.commit()
    db.refresh(user)
    return user
