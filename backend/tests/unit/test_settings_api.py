from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.runtime_settings import get_runtime_settings, reset_settings_overrides
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app, configure_cors
from app.models.app_setting import AppSetting
from app.models.audit_log import AuditLog
from app.models.user import User


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_admin_can_update_persist_and_audit_issuer_settings():
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
    reset_settings_overrides()
    with test_sessions() as db:
        db.add(User(
            full_name="Admin",
            email="admin-settings@example.com",
            password_hash=hash_password("very-secure-password"),
            role="ADMIN",
        ))
        db.add(User(
            full_name="Comptable",
            email="accountant-settings@example.com",
            password_hash=hash_password("very-secure-password"),
            role="ACCOUNTANT",
        ))
        db.commit()

    try:
        with TestClient(app) as client:
            admin_headers = _login(client, "admin-settings@example.com", "very-secure-password")
            accountant_headers = _login(client, "accountant-settings@example.com", "very-secure-password")

            denied = client.put(
                "/api/settings/issuer",
                headers=accountant_headers,
                json={"name": "FaktSure SARL"},
            )
            assert denied.status_code == 403

            updated = client.put(
                "/api/settings/issuer",
                headers=admin_headers,
                json={
                    "name": "FaktSure SARL",
                    "email": "facturation@example.com",
                    "rccm": "RB/COT/24 B 1234",
                    "payment_terms": None,
                },
            )
            assert updated.status_code == 200
            assert updated.json()["issuer"] == {
                "name": "FaktSure SARL",
                "address": "",
                "tax_identifier": "",
                "rccm": "RB/COT/24 B 1234",
                "phone": "",
                "email": "facturation@example.com",
                "payment_terms": "",
            }

            with test_sessions() as db:
                stored = {
                    row.key: row.value
                    for row in db.scalars(
                        select(AppSetting).where(AppSetting.key.in_([
                            "issuer_name",
                            "issuer_email",
                            "issuer_rccm",
                            "issuer_payment_terms",
                        ]))
                    )
                }
                assert stored == {
                    "issuer_name": "FaktSure SARL",
                    "issuer_email": "facturation@example.com",
                    "issuer_rccm": "RB/COT/24 B 1234",
                    "issuer_payment_terms": "",
                }
                audit = db.scalar(
                    select(AuditLog).where(AuditLog.action == "ISSUER_SETTINGS_UPDATED")
                )
                assert audit is not None
                assert '"issuer_name": "FaktSure SARL"' in audit.new_value
                assert '"issuer_name": ""' in audit.previous_value

                reset_settings_overrides()
                from app.core.runtime_settings import load_settings_overrides

                load_settings_overrides(db)
                assert get_runtime_settings().issuer_name == "FaktSure SARL"
                assert get_runtime_settings().issuer_payment_terms == ""

            assert client.get("/api/settings", headers=admin_headers).json()["issuer"]["name"] == "FaktSure SARL"
            assert client.put(
                "/api/settings/issuer",
                headers=admin_headers,
                json={},
            ).status_code == 422
            assert client.put(
                "/api/settings/issuer",
                headers=admin_headers,
                json={"email": "not-an-email"},
            ).status_code == 422
    finally:
        app.dependency_overrides.pop(get_db, None)
        reset_settings_overrides()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_cors_preflight_allows_only_configured_frontend_origins():
    test_app = FastAPI()
    configure_cors(
        test_app,
        Settings(cors_allowed_origins="https://frontend.example, http://localhost:3000"),
    )

    @test_app.get("/resource")
    def read_resource():
        return {"ok": True}

    with TestClient(test_app) as client:
        preflight = client.options(
            "/resource",
            headers={
                "Origin": "https://frontend.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "https://frontend.example"

        rejected = client.options(
            "/resource",
            headers={
                "Origin": "https://other.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert rejected.status_code == 400


def test_cors_rejects_wildcard_origins():
    try:
        Settings(cors_allowed_origins="https://frontend.example,*")
    except ValueError as exc:
        assert "wildcard" in str(exc)
    else:
        raise AssertionError("A wildcard origin must not be accepted")


def test_cors_origins_must_be_origins_without_paths():
    try:
        Settings(cors_allowed_origins="https://frontend.example/app")
    except ValueError as exc:
        assert "without paths" in str(exc)
    else:
        raise AssertionError("A URL path must not be accepted as a CORS origin")
