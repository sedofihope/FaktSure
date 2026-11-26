import atexit
import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

TEST_DATABASE = os.path.join(
    tempfile.gettempdir(),
    f"faktsure-tests-{os.getpid()}-{uuid.uuid4().hex}.db",
)
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE}"


def _remove_test_database() -> None:
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(TEST_DATABASE + suffix)
        except FileNotFoundError:
            pass


atexit.register(_remove_test_database)

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Provide a test client for API integration tests."""

    with TestClient(app) as test_client:
        yield test_client
