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


@pytest.mark.asyncio
async def test_gemini_transient_503_retry_success():
    """Verify transient 503 error retries and succeeds on attempt 2."""
    from app.providers.base import ModelProviderError
    provider = GeminiProvider(api_key="fake-test-key")
    mock_client = MagicMock()

    mock_error = genai_errors.ServerError(
        503,
        {"error": {"code": 503, "message": "This model is currently experiencing high demand.", "status": "UNAVAILABLE"}},
        MagicMock(),
    )
    mock_resp = MagicMock()
    mock_resp.text = '{"fit_score": 85, "reason": "Good match"}'
    mock_resp.parsed = None

    # First attempt fails with 503, second attempt succeeds
    mock_client.aio.models.generate_content = AsyncMock(side_effect=[mock_error, mock_resp])

    with patch.object(provider, "_get_client", return_value=mock_client), patch("asyncio.sleep", new_callable=AsyncMock):
        res, model = await provider.generate_json(
            task_name="fit_analysis",
            system_instruction=None,
            user_prompt="test",
            output_schema=DummyResponseSchema,
        )
    assert res.fit_score == 85
    assert res.reason == "Good match"
    assert mock_client.aio.models.generate_content.call_count == 2


@pytest.mark.asyncio
async def test_gemini_persistent_500_raises_provider_error():
    """Verify persistent 500 error exhausts bounded retry and raises ModelProviderError."""
    from app.providers.base import ModelProviderError
    provider = GeminiProvider(api_key="fake-test-key")
    mock_client = MagicMock()

    mock_error = genai_errors.ServerError(
        500,
        {"error": {"code": 500, "message": "Internal error encountered.", "status": "INTERNAL"}},
        MagicMock(),
    )
    mock_client.aio.models.generate_content = AsyncMock(side_effect=mock_error)

    with patch.object(provider, "_get_client", return_value=mock_client), patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(ModelProviderError) as exc_info:
            await provider.generate_json(
                task_name="fit_analysis",
                system_instruction=None,
                user_prompt="test",
                output_schema=DummyResponseSchema,
            )
    assert "Gemini API error (500)" in str(exc_info.value)
    assert mock_client.aio.models.generate_content.call_count == 3


def test_plan_model_output_schema_has_no_additional_properties():
    """Verify PlanModelOutput generates clean schema without rejected additionalProperties."""
    from app.prompts import PlanModelOutput
    from google.genai import _transformers
    schema = _transformers.t_schema(None, PlanModelOutput)
    # Ensure neither steps items nor guidance has additional_properties
    steps_schema = schema.properties["steps"]
    assert steps_schema.items.additional_properties is None
    assert schema.properties["setup_guidance"].additional_properties is None
    assert schema.properties["test_guidance"].additional_properties is None


def test_batched_fit_schema_has_no_min_max_constraints():
    """Verify BatchedFitResponse generates clean schema without minimum/maximum constraints that crash Gemma 4."""
    from app.prompts import BatchedFitResponse, IssueFitAssessment
    from google.genai import _transformers
    schema = _transformers.t_schema(None, BatchedFitResponse)
    assessment_schema = schema.properties["assessments"].items
    # Ensure fit_score has no minimum/maximum in generated schema
    assert getattr(assessment_schema.properties["fit_score"], "minimum", None) is None
    assert getattr(assessment_schema.properties["fit_score"], "maximum", None) is None
    # Verify local Pydantic validator clamps score
    valid = IssueFitAssessment(
        issue_number=1,
        fit_score=150,
        reason="Test",
    )
    assert valid.fit_score == 100
    valid_neg = IssueFitAssessment(
        issue_number=2,
        fit_score=-10,
        reason="Test",
    )
    assert valid_neg.fit_score == 0

