from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_roles
from app.db.session import get_db
from app.models.product import Product
from app.models.user import User
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate

router = APIRouter(prefix="/products", tags=["products"])

@router.get("", response_model=list[ProductResponse])
def list_products(db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT", "VALIDATOR"))):
    return list(db.scalars(select(Product).order_by(Product.id)))

@router.post("", response_model=ProductResponse, status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN"))):
    product = Product(**payload.model_dump())
    db.add(product)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A product with this SKU already exists") from exc
    db.refresh(product)
    return product

@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT", "VALIDATOR"))):
    product = db.scalar(select(Product).where(Product.public_id == product_id))
    if product is None:
        raise NotFoundError("Product not found")
    return product

@router.put("/{product_id}", response_model=ProductResponse)
def update_product(product_id: UUID, payload: ProductUpdate, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN"))):
    product = db.scalar(select(Product).where(Product.public_id == product_id))
    if product is None:
        raise NotFoundError("Product not found")
    for name, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, name, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A product with this SKU already exists") from exc
    db.refresh(product)
    return product

@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN"))):
    product = db.scalar(select(Product).where(Product.public_id == product_id))
    if product is None:
        raise NotFoundError("Product not found")
    product.is_active = False
    db.commit()
