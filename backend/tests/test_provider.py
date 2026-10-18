"""Unit tests for ModelProvider and GeminiProvider error handling (Mocked, Offline)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel, Field

from app.providers.base import (
    AuthenticationError,
    QuotaExceededError,
    SafetyBlockedError,
    ModelTimeoutError,
    InvalidModelOutputError,
    ModelNotFoundError,
)
from app.providers.gemini import GeminiProvider
from google.genai import errors as genai_errors


class DummyResponseSchema(BaseModel):
    fit_score: int = Field(..., ge=0, le=100)
    reason: str


@pytest.mark.asyncio
async def test_gemini_missing_api_key_raises_auth_error():
    """Verify missing API key raises AuthenticationError without network call."""
    provider = GeminiProvider(api_key="")
    with pytest.raises(AuthenticationError) as exc_info:
        await provider.generate_json(
            task_name="test",
            system_instruction=None,
            user_prompt="test",
            output_schema=DummyResponseSchema,
        )
    assert "GEMINI_API_KEY is missing" in str(exc_info.value)


@pytest.mark.asyncio
async def test_gemini_quota_exceeded_error_mapping():
    """Verify 429 / RESOURCE_EXHAUSTED maps to QuotaExceededError."""
    provider = GeminiProvider(api_key="fake-test-key")
    mock_client = MagicMock()
    mock_error = genai_errors.ClientError(
        code=429,
        response_json={"error": {"code": 429, "message": "RESOURCE_EXHAUSTED: quota reached", "status": "RESOURCE_EXHAUSTED"}}
    )
    mock_client.aio.models.generate_content = AsyncMock(side_effect=mock_error)

    with patch.object(provider, "_get_client", return_value=mock_client):
        with pytest.raises(QuotaExceededError):
            await provider.generate_json(
                task_name="test",
                system_instruction=None,
                user_prompt="test",
                output_schema=DummyResponseSchema,
            )


@pytest.mark.asyncio
async def test_gemini_auth_error_mapping():
    """Verify 401/403 maps to AuthenticationError."""
    provider = GeminiProvider(api_key="fake-test-key")
    mock_client = MagicMock()
    mock_error = genai_errors.ClientError(
        code=403,
        response_json={"error": {"code": 403, "message": "PERMISSION_DENIED: API_KEY_INVALID", "status": "PERMISSION_DENIED"}}
    )
    mock_client.aio.models.generate_content = AsyncMock(side_effect=mock_error)

    with patch.object(provider, "_get_client", return_value=mock_client):
        with pytest.raises(AuthenticationError):
            await provider.generate_json(
                task_name="test",
                system_instruction=None,
                user_prompt="test",
                output_schema=DummyResponseSchema,
            )


@pytest.mark.asyncio
async def test_gemini_invalid_json_output_mapping():
    """Verify non-JSON response maps to InvalidModelOutputError."""
    provider = GeminiProvider(api_key="fake-test-key")
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "This is not valid JSON at all."
    mock_resp.parsed = None
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    with patch.object(provider, "_get_client", return_value=mock_client):
        with pytest.raises(InvalidModelOutputError):
            await provider.generate_json(
                task_name="test",
                system_instruction=None,
                user_prompt="test",
                output_schema=DummyResponseSchema,
            )
