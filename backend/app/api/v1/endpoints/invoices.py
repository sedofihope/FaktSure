from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_roles
from app.db.session import get_db
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.invoice import InvoiceCreate, InvoiceResponse, InvoiceUpdate
from app.services.invoice_service import InvoiceService
from app.storage.manager import StorageManager

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.post(
    "",
    response_model=InvoiceResponse,
    status_code=201,
    summary="Create an invoice draft from a reviewed document",
    description=(
        "Send document_id only to create a draft using the reviewed extracted fields. "
        "The active client is matched by RCCM/tax identifier, or by exact name when "
        "no identifier is present. The invoice date defaults to today; the due date "
        "is left empty unless provided. Add client_id, issue_date, due_date or currency "
        "when you need to supply or override a value. Provide items only to override extracted lines."
    ),
)
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT"))):
    try:
        return InvoiceService().create_draft(db, payload, _user.id)
    except LookupError as exc:
        raise NotFoundError(str(exc))
    except ValueError as exc:
        raise ConflictError(str(exc))


@router.get("", response_model=list[InvoiceResponse])
def list_invoices(db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT", "VALIDATOR"))):
    return list(db.scalars(select(Invoice).order_by(Invoice.id.desc())))


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(invoice_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT", "VALIDATOR"))):
    invoice = db.scalar(select(Invoice).where(Invoice.public_id == invoice_id))
    if invoice is None:
        raise NotFoundError("Invoice not found")
    return invoice


@router.put("/{invoice_id}", response_model=InvoiceResponse)
def update_invoice(invoice_id: UUID, payload: InvoiceUpdate, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT"))):
    invoice = db.scalar(select(Invoice).where(Invoice.public_id == invoice_id))
    if invoice is None:
        raise NotFoundError("Invoice not found")
    if invoice.status not in {"DRAFT", "PENDING_VALIDATION"}:
        raise ConflictError("A validated invoice cannot be modified")
    if payload.due_date is not None:
        invoice.due_date = payload.due_date
    db.commit(); db.refresh(invoice)
    return invoice


@router.post("/{invoice_id}/validate", response_model=InvoiceResponse)
def validate_invoice(invoice_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "VALIDATOR"))):
    invoice = db.scalar(select(Invoice).where(Invoice.public_id == invoice_id))
    if invoice is None:
        raise NotFoundError("Invoice not found")
    try:
        return InvoiceService().validate(db, invoice, user.id)
    except ValueError as exc:
        raise ConflictError(str(exc))


@router.get("/{invoice_id}/pdf")
def invoice_pdf(invoice_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT", "VALIDATOR"))):
    invoice = db.scalar(select(Invoice).where(Invoice.public_id == invoice_id))
    if invoice is None:
        raise NotFoundError("Invoice not found")
    service = InvoiceService()
    backend, key, digest = service.ensure_pdf(db, invoice)
    content = StorageManager().read(backend, key, digest)
    filename = quote(f"{invoice.invoice_number}.pdf", safe="")
    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
        },
    )
