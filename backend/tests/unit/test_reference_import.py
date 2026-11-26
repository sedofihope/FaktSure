import asyncio
from io import BytesIO

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.datastructures import UploadFile

from app.api.v1.endpoints.references import import_references
from app.db.base import Base
from app.models import Client, Product
from app.models.user import User


def test_reference_csv_import_keeps_valid_rows_and_reports_duplicate_sku():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with sessions() as db:
            db.add(Product(sku="DUP-1", name="Existing"))
            db.commit()
            upload = UploadFile(
                filename="products.csv",
                file=BytesIO(
                    b"type,sku,name,unit\n"
                    b"product,NEW-1,Valid product,unit\n"
                    b"product,DUP-1,Duplicate product,unit\n"
                    b"wrong,,Unknown type,unit\n"
                ),
            )
            result = asyncio.run(import_references(upload, db, User()))

            assert result["imported"] == 1
            assert [error["line"] for error in result["errors"]] == [3, 4]
            assert db.scalar(select(Product).where(Product.sku == "NEW-1")) is not None
            assert db.scalar(select(Product).where(Product.name == "Duplicate product")) is None
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_reference_csv_imports_client_rccm():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with sessions() as db:
            upload = UploadFile(
                filename="clients.csv",
                file=BytesIO(
                    b"TYPE,NAME,TAX_IDENTIFIER,RCCM\n"
                    b"client,Example SARL,TAX-123,SN-DKR-2026-B-00001\n"
                ),
            )
            result = asyncio.run(import_references(upload, db, User()))

            assert result == {"imported": 1, "errors": []}
            client = db.scalar(select(Client).where(Client.name == "Example SARL"))
            assert client is not None
            assert client.tax_identifier == "TAX-123"
            assert client.rccm == "SN-DKR-2026-B-00001"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
