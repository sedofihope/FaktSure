from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID
from zipfile import BadZipFile

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.runtime_settings import get_runtime_settings
from app.core.exceptions import NotFoundError
from app.core.permissions import require_roles
from app.db.session import get_db
from app.models.product import Product
from app.models.product_price import ProductPrice
from app.models.tax_rule import TaxRule
from app.models.user import User
from app.schemas.reference import (
    ProductPriceCreate, ProductPriceResponse,
    TaxRuleCreate, TaxRuleResponse,
)
from app.schemas.documentation import ReferenceImportResponse

router = APIRouter(tags=["references"])


@router.get("/tax-rules", response_model=list[TaxRuleResponse])
def list_tax_rules(db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT", "VALIDATOR"))):
    return list(db.scalars(select(TaxRule).order_by(TaxRule.id)))


@router.post("/tax-rules", response_model=TaxRuleResponse, status_code=201)
def create_tax_rule(payload: TaxRuleCreate, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN"))):
    rule = TaxRule(**payload.model_dump())
    db.add(rule); db.commit(); db.refresh(rule)
    return rule


@router.get("/products/{product_id}/prices", response_model=list[ProductPriceResponse])
def list_prices(product_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT", "VALIDATOR"))):
    product = db.scalar(select(Product).where(Product.public_id == product_id))
    if product is None:
        raise NotFoundError("Product not found")
    return list(db.scalars(select(ProductPrice).where(ProductPrice.product_id == product.id).order_by(ProductPrice.valid_from.desc())))


@router.post("/products/{product_id}/prices", response_model=ProductPriceResponse, status_code=201)
def create_price(product_id: UUID, payload: ProductPriceCreate, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN"))):
    product = db.scalar(select(Product).where(Product.public_id == product_id))
    if product is None:
        raise NotFoundError("Product not found")
    price = ProductPrice(product_id=product.id, **payload.model_dump())
    db.add(price); db.commit(); db.refresh(price)
    return price


@router.post("/references/import", response_model=ReferenceImportResponse)
async def import_references(file: UploadFile, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN"))):
    """Import reference rows from a CSV or XLSX file with line-level errors."""

    import csv
    import io

    from pydantic import TypeAdapter, ValidationError
    from pydantic.networks import EmailStr
    from openpyxl import load_workbook

    content = await file.read()
    if len(content) > get_runtime_settings().max_upload_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {get_runtime_settings().max_upload_size_mb} MB",
        )
    errors: list[dict] = []
    rows: list[dict[str, str]] = []
    filename = (file.filename or "").lower()
    try:
        if filename.endswith(".csv"):
            reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
            if not reader.fieldnames or not {"name"}.issubset({name.strip().lower() for name in reader.fieldnames if name}):
                raise HTTPException(status_code=422, detail="A name column is required")
            rows = [
                {str(key).strip().lower(): (value or "").strip() for key, value in row.items() if key}
                for row in reader
            ]
        elif filename.endswith(".xlsx"):
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            sheet = workbook.active
            values = sheet.iter_rows(values_only=True)
            header_row = next(values, None)
            if not header_row:
                raise HTTPException(status_code=422, detail="Spreadsheet is empty")
            headers = [str(value).strip().lower() if value is not None else "" for value in header_row]
            if "name" not in headers:
                raise HTTPException(status_code=422, detail="A name column is required")
            rows = [
                {
                    headers[index]: "" if value is None else str(value).strip()
                    for index, value in enumerate(values_row)
                    if index < len(headers) and headers[index]
                }
                for values_row in values
            ]
            workbook.close()
        else:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Only CSV and XLSX files are supported",
            )
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="CSV must be UTF-8 encoded") from exc
    except (OSError, ValueError, BadZipFile) as exc:
        raise HTTPException(status_code=422, detail="Reference file could not be parsed") from exc

    imported = 0
    from app.models.client import Client

    for line, row in enumerate(rows, start=2):
        if not any(value.strip() for value in row.values()):
            continue
        kind = (row.get("type") or row.get("kind") or "product").lower()
        try:
            with db.begin_nested():
                if not row.get("name"):
                    raise ValueError("name is required")
                if kind == "client":
                    email = row.get("email") or None
                    if email:
                        TypeAdapter(EmailStr).validate_python(email)
                    entity = Client(
                        name=row["name"],
                        tax_identifier=row.get("tax_identifier") or None,
                        rccm=row.get("rccm") or None,
                        address=row.get("address") or None,
                        email=email,
                        phone=row.get("phone") or None,
                    )
                elif kind == "tax":
                    rate = Decimal(row["rate"])
                    valid_from = date.fromisoformat(row["valid_from"])
                    valid_until = date.fromisoformat(row["valid_until"]) if row.get("valid_until") else None
                    if rate < 0 or rate > 100:
                        raise ValueError("rate must be between 0 and 100")
                    if valid_until and valid_until < valid_from:
                        raise ValueError("valid_until must not precede valid_from")
                    entity = TaxRule(
                        name=row["name"],
                        rate=rate,
                        calculation_type=row.get("calculation_type") or "PERCENTAGE",
                        valid_from=valid_from,
                        valid_until=valid_until,
                    )
                elif kind == "product":
                    entity = Product(
                        sku=row.get("sku") or None,
                        name=row["name"],
                        description=row.get("description") or None,
                        unit=row.get("unit") or "unit",
                    )
                else:
                    raise ValueError("type must be client, product or tax")
                db.add(entity)
                db.flush()
            imported += 1
        except (ValueError, KeyError, InvalidOperation, ValidationError, IntegrityError) as exc:
            errors.append({
                "line": line,
                "error": "Duplicate or invalid row" if isinstance(exc, IntegrityError) else str(exc),
            })
    db.commit()
    return {"imported": imported, "errors": errors}
