"""Gemini & Gemma model provider using official google-genai SDK."""

import asyncio
import json
import logging
from typing import Any, Optional, Type
from pydantic import BaseModel, ValidationError
from google import genai
from google.genai import errors as genai_errors

from app.config import settings
from app.providers.base import (
    AuthenticationError,
    InvalidModelOutputError,
    ModelNotFoundError,
    ModelProvider,
    ModelProviderError,
    ModelTimeoutError,
    QuotaExceededError,
    SafetyBlockedError,
)

logger = logging.getLogger(__name__)


class GeminiProvider(ModelProvider):
    """Provider for hosted Gemma 4 models accessed via the Gemini API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        fallback_model: Optional[str] = None,
    ):
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.default_model = default_model or settings.GEMMA_MODEL
        self.fallback_model = fallback_model or settings.GEMMA_FALLBACK_MODEL
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        if not self.api_key or not self.api_key.strip():
            raise AuthenticationError("GEMINI_API_KEY is missing or unconfigured. AI features require a valid key.")
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key.strip())
        return self._client

    def _normalize_model_id(self, model_id: str) -> str:
        """Ensure canonical model identifier format."""
        if not model_id.startswith("models/") and "/" not in model_id:
            return f"models/{model_id}"
        return model_id

    async def generate_json(
        self,
        task_name: str,
        system_instruction: Optional[str],
        user_prompt: str,
        output_schema: Type[BaseModel],
        timeout_seconds: float = 60.0,
    ) -> tuple[BaseModel, str]:
        """
        Execute JSON generation using Gemma 4 with bounded timeout and safe error translation.
        Attempts default model; strictly falls back to fallback_model only if default is NOT_FOUND.
        """
        client = self._get_client()

        # Try default model first, fallback only if model not found
        models_to_try = [self._normalize_model_id(self.default_model)]
        if self.fallback_model and self.fallback_model != self.default_model:
            models_to_try.append(self._normalize_model_id(self.fallback_model))

        last_error: Optional[Exception] = None

        for model_id in models_to_try:
            try:
                return await self._call_model(
                    client=client,
                    model_id=model_id,
                    task_name=task_name,
                    system_instruction=system_instruction,
                    user_prompt=user_prompt,
                    output_schema=output_schema,
                    timeout_seconds=timeout_seconds,
                )
            except ModelNotFoundError as exc:
                last_error = exc
                logger.warning("Configured model '%s' not found. Attempting fallback if configured.", model_id)
                continue
            except Exception as exc:
                # Quota, safety, auth, timeout, or validation errors do not trigger fallback model
                raise exc

        if last_error:
            raise last_error
        raise ModelProviderError("No model could be evaluated.")

    async def _call_model(
        self,
        client: genai.Client,
        model_id: str,
        task_name: str,
        system_instruction: Optional[str],
        user_prompt: str,
        output_schema: Type[BaseModel],
        timeout_seconds: float,
    ) -> tuple[BaseModel, str]:
        """Execute single model call with structured output decoding."""
        # Per M3 smoke test finding: Gemma 4 on Gemini API returns 500 when system_instruction
        # is passed in config. As required by §8 and Approved Decision 6, fixed instructions
        # are prepended directly into the user message.
        combined_prompt = ""
        if system_instruction and system_instruction.strip():
            combined_prompt = f"{system_instruction.strip()}\n\n---\n\n{user_prompt}"
        else:
            combined_prompt = user_prompt

        config: dict[str, Any] = {
            "response_mime_type": "application/json",
            "response_schema": output_schema,
            "temperature": 0.1,
            "max_output_tokens": 4096,
        }

        max_transient_attempts = 3
        backoff_delays = [2.0, 4.0]
        response = None
        for t_attempt in range(max_transient_attempts):
            try:
                async with asyncio.timeout(timeout_seconds):
                    response = await client.aio.models.generate_content(
                        model=model_id,
                        contents=combined_prompt,
                        config=config,
                    )
                break
            except TimeoutError:
                raise ModelTimeoutError(f"Model generation timed out after {timeout_seconds} seconds")
            except genai_errors.ClientError as exc:
                msg = str(exc)
                status_code = getattr(exc, "code", None)
                if status_code in (401, 403) or "API_KEY_INVALID" in msg or "PERMISSION_DENIED" in msg:
                    raise AuthenticationError("Invalid or unauthorized GEMINI_API_KEY") from exc
                if status_code == 429 or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
                    raise QuotaExceededError("Gemini API rate limit or quota exhausted") from exc
                if status_code == 404 or "NOT_FOUND" in msg or "is not found" in msg.lower():
                    raise ModelNotFoundError(f"Model '{model_id}' was not found on the Gemini API") from exc
                if "SAFETY" in msg or "BLOCKED" in msg:
                    raise SafetyBlockedError("Model request was blocked by safety guidelines") from exc
                # If 400 with unsupported response_schema or system_instruction, attempt prompt-based JSON mode
                if status_code == 400 and ("response_schema" in msg or "system_instruction" in msg or "schema" in msg):
                    return await self._fallback_prompt_mode(
                        client=client,
                        model_id=model_id,
                        system_instruction=system_instruction,
                        user_prompt=user_prompt,
                        output_schema=output_schema,
                        timeout_seconds=timeout_seconds,
                    )
                raise ModelProviderError(f"Gemini API client error: {msg}") from exc
            except genai_errors.APIError as exc:
                msg = str(exc)
                status_code = getattr(exc, "code", None)
                if "RESOURCE_EXHAUSTED" in msg or status_code == 429:
                    raise QuotaExceededError("Gemini API quota exhausted") from exc
                if status_code in (500, 503) and t_attempt < max_transient_attempts - 1:
                    delay = backoff_delays[t_attempt] if t_attempt < len(backoff_delays) else 4.0
                    logger.warning(
                        "Transient Gemini API error %s during %s on '%s' (attempt %d/%d). Retrying in %.1fs...",
                        status_code, task_name, model_id, t_attempt + 1, max_transient_attempts, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise ModelProviderError(f"Gemini API error ({status_code or '5xx'}): {msg}") from exc
            except Exception as exc:
                raise ModelProviderError(f"Unexpected provider error: {exc}") from exc

        if response is None:
            raise ModelProviderError(f"No response received from model '{model_id}'")

        # Parse and validate response
        return self._parse_and_validate(response, output_schema, model_id)

    async def _fallback_prompt_mode(
        self,
        client: genai.Client,
        model_id: str,
        system_instruction: Optional[str],
        user_prompt: str,
        output_schema: Type[BaseModel],
        timeout_seconds: float,
    ) -> tuple[BaseModel, str]:
        """Fallback mode: Pass JSON schema requirement inside the prompt if SDK schema config is unsupported."""
        schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
        combined_prompt = ""
        if system_instruction:
            combined_prompt += f"{system_instruction}\n\n"
        combined_prompt += (
            f"{user_prompt}\n\n"
            f"You MUST respond ONLY with valid JSON strictly conforming to this JSON schema:\n"
            f"```json\n{schema_json}\n```\n"
        )

        config = {
            "response_mime_type": "application/json",
            "temperature": 0.1,
        }

        try:
            async with asyncio.timeout(timeout_seconds):
                response = await client.aio.models.generate_content(
                    model=model_id,
                    contents=combined_prompt,
                    config=config,
                )
        except TimeoutError:
            raise ModelTimeoutError(f"Model generation timed out after {timeout_seconds} seconds")
        except Exception as exc:
            raise ModelProviderError(f"Gemini fallback prompt generation failed: {exc}") from exc

        return self._parse_and_validate(response, output_schema, model_id)

    def _parse_and_validate(
        self, response: Any, output_schema: Type[BaseModel], model_id: str
    ) -> tuple[BaseModel, str]:
        """Parse raw response text or parsed object and validate against output_schema."""
        # 1. Check if SDK parsed object is directly available
        if hasattr(response, "parsed") and response.parsed is not None:
            if isinstance(response.parsed, output_schema):
                return response.parsed, model_id
            if isinstance(response.parsed, dict):
                try:
                    return output_schema.model_validate(response.parsed), model_id
                except ValidationError as ve:
                    raise InvalidModelOutputError(f"Validation error in parsed response: {ve}") from ve

        # 2. Parse text attribute
        raw_text = getattr(response, "text", None)
        if not raw_text and hasattr(response, "candidates") and response.candidates:
            parts = response.candidates[0].content.parts
            raw_text = "".join(getattr(p, "text", "") for p in parts if hasattr(p, "text"))

        if not raw_text or not raw_text.strip():
            raise InvalidModelOutputError("Model returned an empty response")

        clean_text = raw_text.strip()
        # Strip markdown fence if present
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

        try:
            parsed_data = json.loads(clean_text)
        except json.JSONDecodeError as jde:
            raise InvalidModelOutputError(f"Model output is not valid JSON: {jde}") from jde

        try:
            validated = output_schema.model_validate(parsed_data)
            return validated, model_id
        except ValidationError as ve:
            raise InvalidModelOutputError(f"Model JSON failed Pydantic schema validation: {ve}") from ve
