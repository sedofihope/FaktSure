import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import Client, Product, ProductPrice, TaxRule, User


def main() -> None:
    """Seed clearly fictitious demo records in development only."""

    settings = get_settings()
    password = os.getenv("DEMO_PASSWORD", "")
    if settings.app_env.lower() != "development":
        raise SystemExit("Demo seeding is permitted only with APP_ENV=development")
    if len(password) < 12:
        raise SystemExit("Set DEMO_PASSWORD to a unique password of at least 12 characters")

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for role, name in (
            ("ADMIN", "FaktSure Demo Admin"),
            ("ACCOUNTANT", "FaktSure Demo Accountant"),
            ("VALIDATOR", "FaktSure Demo Validator"),
        ):
            email = f"{role.lower()}@demo.faktsure.com"
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                db.add(User(
                    full_name=name,
                    email=email,
                    password_hash=hash_password(password),
                    role=role,
                ))

        client = db.scalar(select(Client).where(Client.name == "Client Démo Fictif"))
        if client is None:
            db.add(Client(
                name="Client Démo Fictif",
                tax_identifier="DEMO-TAX-001",
                rccm="SN-DKR-2026-B-00001",
                address="Adresse fictive, Dakar",
                email="client@demo.faktsure.com",
            ))
        product = db.scalar(select(Product).where(Product.sku == "DEMO-SKU-001"))
        if product is None:
            product = Product(
                sku="DEMO-SKU-001",
                name="Produit Démo Fictif",
                description="Produit de démonstration sans valeur commerciale",
                unit="unit",
            )
            db.add(product)
            db.flush()
        price = db.scalar(select(ProductPrice).where(ProductPrice.product_id == product.id))
        if price is None:
            db.add(ProductPrice(
                product_id=product.id,
                unit_price=1000,
                currency="XOF",
                valid_from=date.today(),
            ))
        tax = db.scalar(select(TaxRule).where(TaxRule.name == "DEMO-TAX-18"))
        if tax is None:
            db.add(TaxRule(
                name="DEMO-TAX-18",
                rate=18,
                calculation_type="PERCENTAGE",
                valid_from=date.today(),
            ))
        db.commit()
    print("Fictitious demo records created (password supplied through DEMO_PASSWORD)")


if __name__ == "__main__":
    main()