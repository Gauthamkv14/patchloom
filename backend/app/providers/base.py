"""Abstract base model provider interface and provider exceptions."""

from abc import ABC, abstractmethod
from typing import Any, Optional, Type
from pydantic import BaseModel


class ModelProviderError(Exception):
    """Base exception for all model provider failures."""
    pass


class AuthenticationError(ModelProviderError):
    """Raised when API key is missing, invalid, or unauthorized."""
    pass


class QuotaExceededError(ModelProviderError):
    """Raised when provider quota or rate limit is exhausted (do not retry in loops)."""
    pass


class SafetyBlockedError(ModelProviderError):
    """Raised when input or output is blocked by safety filters."""
    pass


class ModelTimeoutError(ModelProviderError):
    """Raised when generation exceeds the bounded timeout."""
    pass


class InvalidModelOutputError(ModelProviderError):
    """Raised when model returns non-JSON or schema-invalid content."""
    pass


class ModelNotFoundError(ModelProviderError):
    """Raised when the specified model ID does not exist or is unsupported on the platform."""
    pass


class ModelProvider(ABC):
    """Minimal interface for AI reasoning providers."""

    @abstractmethod
    async def generate_json(
        self,
        task_name: str,
        system_instruction: Optional[str],
        user_prompt: str,
        output_schema: Type[BaseModel],
        timeout_seconds: float = 60.0,
    ) -> tuple[BaseModel, str]:
        """
        Execute JSON generation bounded by output_schema.

        Returns:
            tuple[BaseModel, str]: (validated_pydantic_instance, actual_model_id_used)
        """
        pass
