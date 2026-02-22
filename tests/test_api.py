import pytest
from app.core.config import settings

def test_health_check(client, mock_db):
    mock_db.collection().document().set.return_value = None
    response = client.get(f"{settings.API_V1_STR}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Welcome" in response.json()["message"]

# --- Reports Tests ---
def test_reports_access_denied(client):
    response = client.get(f"{settings.API_V1_STR}/reports/")
    assert response.status_code == 403

def test_reports_access_allowed(client, override_patient, mock_db):
    mock_db.collection().where().stream.return_value = []
    response = client.get(f"{settings.API_V1_STR}/reports/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_upload_url_logic(client, override_patient, mock_db):
    mock_db.collection().document().set.return_value = None
    with pytest.MonkeyPatch.context() as m:
        async def mock_get_url(bucket, path):
            return {"signedURL": "https://signed.url"}
        m.setattr("app.services.storage_service.storage_service.get_upload_url", mock_get_url)
        response = client.post(f"{settings.API_V1_STR}/reports/upload-url?file_name=test.pdf")
        assert response.status_code == 200
        assert response.json()["upload_url"] == "https://signed.url"

# --- Patient Tests ---
def test_patient_me(client, override_patient):
    response = client.get(f"{settings.API_V1_STR}/patient/me")
    assert response.status_code == 200
    assert response.json()["uid"] == "p-123"

def test_patient_me_denied_to_doctor(client, override_doctor):
    response = client.get(f"{settings.API_V1_STR}/patient/me")
    assert response.status_code == 403

# --- Doctor Tests ---
def test_doctor_dashboard(client, override_doctor):
    response = client.get(f"{settings.API_V1_STR}/doctor/dashboard")
    assert response.status_code == 200
    assert "stats" in response.json()

def test_doctor_access_denied_to_patient(client, override_patient):
    response = client.get(f"{settings.API_V1_STR}/doctor/dashboard")
    assert response.status_code == 403

# --- Appointments Tests ---
def test_appointments_list(client, override_patient):
    response = client.get(f"{settings.API_V1_STR}/appointments/")
    assert response.status_code == 200
    assert "appointments" in response.json()

# --- Messages Tests ---
def test_messages_conversations(client, override_patient):
    response = client.get(f"{settings.API_V1_STR}/messages/conversations")
    assert response.status_code == 200
    assert "conversations" in response.json()
