import pytest
from unittest.mock import MagicMock, patch
import sys

# Mock firebase_admin and firestore before any app code is imported
mock_firebase_admin = MagicMock()
mock_firestore = MagicMock()
mock_credentials = MagicMock()

sys.modules["firebase_admin"] = mock_firebase_admin
sys.modules["firebase_admin.credentials"] = mock_credentials
sys.modules["firebase_admin.firestore"] = mock_firestore
sys.modules["firebase_admin.auth"] = MagicMock()

# Mock the entire firebase core module to avoid initialization issues
mock_db_client = MagicMock()
mock_firebase_core = MagicMock()
mock_firebase_core.db = mock_db_client
sys.modules["app.core.firebase"] = mock_firebase_core

from fastapi.testclient import TestClient
from app.main import app
from app.core.security import get_current_user, get_current_patient, get_current_doctor

@pytest.fixture
def mock_db():
    return mock_db_client

@pytest.fixture
def patient_user():
    return {"uid": "p-123", "email": "patient@test.com", "role": "patient"}

@pytest.fixture
def doctor_user():
    return {"uid": "d-456", "email": "doctor@test.com", "role": "doctor"}

@pytest.fixture
def override_patient(patient_user):
    app.dependency_overrides[get_current_user] = lambda: patient_user
    app.dependency_overrides[get_current_patient] = lambda: patient_user
    yield patient_user
    app.dependency_overrides.clear()

@pytest.fixture
def override_doctor(doctor_user):
    app.dependency_overrides[get_current_user] = lambda: doctor_user
    app.dependency_overrides[get_current_doctor] = lambda: doctor_user
    yield doctor_user
    app.dependency_overrides.clear()

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
