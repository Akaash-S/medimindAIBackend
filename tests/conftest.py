import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from app.main import app
from app.core.security import get_current_user

# Global mock for Firebase Auth
@pytest.fixture
def mock_firebase_auth():
    with patch("app.core.security.auth.verify_id_token") as mock:
        mock.return_value = {
            "uid": "test-user-id",
            "email": "test@example.com"
        }
        yield mock

# Global mock for Firestore
@pytest.fixture
def mock_db():
    with patch("app.core.firebase.db") as mock:
        yield mock

# Mock current user dependency
@pytest.fixture
def override_get_current_user():
    user_data = {
        "uid": "test-user-id",
        "email": "test@example.com",
        "role": "patient"
    }
    app.dependency_overrides[get_current_user] = lambda: user_data
    yield user_data
    app.dependency_overrides.clear()

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
