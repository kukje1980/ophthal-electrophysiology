"""Test configuration: an isolated database, backup and log directory per
run, and logged-in API clients.

Settings are read at import time, so the environment is prepared before the
application is imported.
"""
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="oep-test-")
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_TMP}/test.db",
    "BACKUP_DIR": f"{_TMP}/backups",
    "BACKUP_MIRROR_DIR": f"{_TMP}/mirror",
    "BACKUP_ENABLED": "0",          # scheduler off; tests call the API directly
    "BACKUP_MIN_FREE_MB": "1",
    "LOG_DIR": f"{_TMP}/logs",
    "SECRET_KEY": "test-secret",
    "ADMIN_PASSWORD": "admin1234",
})
os.chdir(ROOT)  # templates/ and static/ are resolved relative to the CWD

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def tmp_root():
    yield _TMP
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def client(tmp_root):
    """Admin client (session-scoped: the DB is shared across tests)."""
    with TestClient(app) as c:
        r = c.post("/login", data={"username": "admin", "password": "admin1234"},
                   follow_redirects=False)
        assert r.status_code == 303
        yield c


@pytest.fixture
def make_patient(client):
    def _make(**extra):
        body = {"mrn": f"T-{uuid.uuid4().hex[:10]}", "name": "테스트", **extra}
        r = client.post("/api/patients", json=body)
        assert r.status_code == 201, r.text
        return r.json()
    return _make


@pytest.fixture(scope="session")
def protocol_key(client):
    return next(iter(client.get("/api/protocols/all").json()))


def login_as(username, password):
    c = TestClient(app)
    r = c.post("/login", data={"username": username, "password": password},
               follow_redirects=False)
    assert r.status_code == 303, r.text
    return c


@pytest.fixture(scope="session")
def staff(client):
    """Create one user per role and return logged-in clients keyed by role."""
    users = {
        "clinician": ("dr_kim", "clinic1234"),
        "technician": ("tech_lee", "tech12345"),
        "viewer": ("view_park", "view12345"),
    }
    for role, (u, pw) in users.items():
        r = client.post("/api/users", json={"username": u, "password": pw,
                                            "full_name": role, "role": role})
        assert r.status_code in (200, 201), r.text
    return {role: login_as(u, pw) for role, (u, pw) in users.items()}


_mrn = [0]


@pytest.fixture
def patient(client):
    _mrn[0] += 1
    r = client.post("/api/patients", json={
        "mrn": f"T{_mrn[0]:04d}", "name": "테스트환자", "sex": "F",
        "birth_date": "1975-05-05",
    })
    assert r.status_code == 201, r.text
    return r.json()


def run_exam(client, patient_id, protocol="VEP_pattern_reversal", eyes=("OD", "OS")):
    r = client.post("/api/exams", json={"patient_id": patient_id,
                                        "protocol": protocol, "eyes": list(eyes)})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def vep_exam(client, patient):
    return run_exam(client, patient["id"])
