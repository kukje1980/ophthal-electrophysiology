"""Test fixtures: a fresh SQLite database and a logged-in admin client."""
import os
import tempfile
import uuid

import pytest

_DB = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ.setdefault("SECRET_KEY", "test-secret")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        r = c.post("/login", data={"username": settings.ADMIN_USERNAME,
                                   "password": settings.ADMIN_PASSWORD},
                   follow_redirects=False)
        assert r.status_code == 303
        yield c


@pytest.fixture
def exam(client):
    p = client.post("/api/patients", json={"name": "Test Patient",
                                           "mrn": uuid.uuid4().hex[:8]}).json()
    r = client.post("/api/exams", json={"patient_id": p["id"],
                                        "protocol": "ffERG_standard"})
    assert r.status_code == 201, r.text
    return r.json()
