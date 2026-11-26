from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import require_roles
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.documentation import AuditEntryResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEntryResponse])
def list_audit(db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN"))):
    logs = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(500))
    return [{
        "public_id": log.public_id,
        "user_public_id": log.user.public_id if log.user else None,
        "action": log.action,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "previous_value": log.previous_value,
        "new_value": log.new_value,
        "created_at": log.created_at,
    } for log in logs]
