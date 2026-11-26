from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User


@pytest.fixture
def admin_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        with test_sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with test_sessions() as db:
        db.add(User(
            full_name="Admin",
            email="admin@example.com",
            password_hash=hash_password("very-secure-password"),
            role="ADMIN",
        ))
        db.commit()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_user_management_requires_admin_and_never_returns_password_hash(admin_client):
    denied = admin_client.post(
        "/api/users",
        json={
            "full_name": "Accountant",
            "email": "accountant@example.com",
            "password": "another-secure-password",
            "role": "ACCOUNTANT",
        },
    )
    assert denied.status_code == 401

    login = admin_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "very-secure-password"},
    )
    assert login.status_code == 200
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}

    created = admin_client.post(
        "/api/users",
        headers=headers,
        json={
            "full_name": "Accountant",
            "email": "accountant@example.com",
            "password": "another-secure-password",
            "role": "ACCOUNTANT",
        },
    )
    assert created.status_code == 201
    assert created.json()["role"] == "ACCOUNTANT"
    assert "password_hash" not in created.json()
    public_id = UUID(created.json()["public_id"])
    fetched = admin_client.get(f"/api/users/{public_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["public_id"] == str(public_id)
    logs = admin_client.get("/api/audit", headers=headers)
    assert logs.status_code == 200
    created_log = next(log for log in logs.json() if log["action"] == "USER_CREATED")
    assert created_log["entity_id"] == str(public_id)
    assert UUID(created_log["user_public_id"])


def test_last_admin_cannot_be_deactivated(admin_client):
    login = admin_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "very-secure-password"},
    )
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    me = admin_client.get("/api/auth/me", headers=headers)
    response = admin_client.put(
        f"/api/users/{me.json()['public_id']}",
        headers=headers,
        json={"is_active": False},
    )

    assert response.status_code == 409


def test_only_admin_can_consult_audit_or_modify_references(admin_client):
    headers = _login(admin_client, "admin@example.com", "very-secure-password")

    users = {}
    for role in ("ACCOUNTANT", "VALIDATOR"):
        response = admin_client.post(
            "/api/users",
            headers=headers,
            json={
                "full_name": role.title(),
                "email": f"{role.lower()}-permissions@example.com",
                "password": "another-secure-password",
                "role": role,
            },
        )
        assert response.status_code == 201
        token = _login(
            admin_client,
            f"{role.lower()}-permissions@example.com",
            "another-secure-password",
        )
        users[role] = token

    assert admin_client.get("/api/audit", headers=users["VALIDATOR"]).status_code == 403
    assert admin_client.get("/api/audit", headers=headers).status_code == 200

    client_id = "00000000-0000-0000-0000-000000000001"
    product_id = "00000000-0000-0000-0000-000000000002"
    denied_requests = [
        ("post", "/api/clients", {"json": {"name": "Client"}}),
        ("put", f"/api/clients/{client_id}", {"json": {"name": "Client modifié"}}),
        ("post", "/api/products", {"json": {"name": "Produit"}}),
        ("put", f"/api/products/{product_id}", {"json": {"name": "Produit modifié"}}),
        (
            "post",
            "/api/tax-rules",
            {
                "json": {
                    "name": "TVA",
                    "rate": "18",
                    "valid_from": "2026-01-01",
                }
            },
        ),
        (
            "post",
            f"/api/products/{product_id}/prices",
            {"json": {"unit_price": "100", "valid_from": "2026-01-01"}},
        ),
    ]

    for method, path, kwargs in denied_requests:
        response = getattr(admin_client, method)(path, headers=users["ACCOUNTANT"], **kwargs)
        assert response.status_code == 403, f"{method.upper()} {path}: {response.text}"

    import_denied = admin_client.post(
        "/api/references/import",
        headers=users["ACCOUNTANT"],
        files={"file": ("clients.csv", b"name\nClient\n", "text/csv")},
    )
    assert import_denied.status_code == 403


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    return {"Authorization": "Bearer " + login.json()["access_token"]}
