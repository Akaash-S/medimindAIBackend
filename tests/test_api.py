import pytest
from app.core.config import settings

def test_health_check(client, mock_db):
    """
    Test the health check endpoint.
    """
    # Mock Firestore set call
    mock_db.collection().document().set.return_value = None
    
    response = client.get(f"{settings.API_V1_STR}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "database" in data

def test_root_endpoint(client):
    """
    Test the root endpoint.
    """
    response = client.get("/")
    assert response.status_code == 200
    assert "Welcome to MediMind AI API" in response.json()["message"]

def test_unauthorized_reports(client):
    """
    Test that reports endpoint returns 403 without authorization header.
    """
    response = client.get(f"{settings.API_V1_STR}/reports")
    assert response.status_code == 403

def test_authorized_reports(client, override_get_current_user, mock_db):
    """
    Test reports endpoint with authorized mock user.
    """
    # Mock Firestore query
    mock_db.collection().where().stream.return_value = []
    
    response = client.get(f"{settings.API_V1_STR}/reports")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_upload_url_logic(client, override_get_current_user, mock_db):
    """
    Test the upload-url generation endpoint.
    """
    # Mock Firestore set
    mock_db.collection().document().set.return_value = None
    
    # Mock storage signed URL (would need to patch storage_service directly for deeper test)
    with pytest.MonkeyPatch.context() as m:
        m.setattr("app.services.storage_service.storage_service.get_upload_url", 
                  lambda b, p: MagicMock(get=lambda k: "https://signed.url"))
        
        response = client.post(
            f"{settings.API_V1_STR}/reports/upload-url?file_name=test.pdf"
        )
        assert response.status_code == 200
        data = response.json()
        assert "upload_url" in data
        assert data["upload_url"] == "https://signed.url"
