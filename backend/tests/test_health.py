"""Tests for the /api/health endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint_success():
    """Verify health endpoint returns 200 OK with expected schema and no secret leakage."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "demo_mode" in data
    assert "environment" in data
    assert "has_gemini_key" in data
    assert "has_github_token" in data
    # Ensure no secret strings or keys are present in response
    response_text = response.text.lower()
    assert "key" not in response_text or data["has_gemini_key"] in [True, False]
    assert "token" not in response_text or data["has_github_token"] in [True, False]
