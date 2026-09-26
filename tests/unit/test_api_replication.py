import pytest
from starlette.testclient import TestClient
from vault.services.api.main import app
import httpx
from unittest.mock import patch, AsyncMock

client = TestClient(app)

@pytest.fixture
def mock_httpx_post():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        yield mock_post

@pytest.fixture
def mock_httpx_get():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        yield mock_get

def test_upload_quorum_success(mock_httpx_post):
    mock_response = httpx.Response(200, json={"checksum": "fake-checksum"}, request=httpx.Request("POST", "http://test"))
    mock_httpx_post.return_value = mock_response
    
    response = client.put("/objects/my-file.txt", content=b"hello world")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["replicas"]) == 3
    assert data["object_key"] == "my-file.txt"

def test_upload_quorum_partial_success(mock_httpx_post):
    call_count = 0
    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            raise httpx.RequestError("Connection timeout")
        return httpx.Response(200, json={"checksum": "fake-checksum"}, request=httpx.Request("POST", "http://test"))
        
    mock_httpx_post.side_effect = side_effect
    
    response = client.put("/objects/partial.txt", content=b"partial data")
    assert response.status_code == 200
    data = response.json()
    assert len(data["replicas"]) == 2

def test_upload_quorum_failure(mock_httpx_post):
    call_count = 0
    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise httpx.RequestError("Connection timeout")
        return httpx.Response(200, json={"checksum": "fake-checksum"}, request=httpx.Request("POST", "http://test"))
        
    mock_httpx_post.side_effect = side_effect
    
    response = client.put("/objects/fail.txt", content=b"fail data")
    assert response.status_code == 503

def test_get_object(mock_httpx_get):
    call_count = 0
    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.RequestError("Connection error")
        return httpx.Response(200, content=b"recovered data", request=httpx.Request("GET", "http://test"))
        
    mock_httpx_get.side_effect = side_effect
    
    response = client.get("/objects/my-file.txt?object_id=test-id-1")
    assert response.status_code == 200
    assert response.content == b"recovered data"
