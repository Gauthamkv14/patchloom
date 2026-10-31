"""Model providers package — provider selection factory."""

from typing import Optional

from app.providers.base import ModelProvider
from app.providers.gemini import GeminiProvider

# Registry of supported provider names → constructor callables.
# Add new providers here when implemented; do not modify callers.
_PROVIDER_REGISTRY: dict[str, type[ModelProvider]] = {
    "gemini": GeminiProvider,
}

# Canonical default provider name (must exist in registry).
DEFAULT_PROVIDER = "gemini"


class UnsupportedProviderError(ValueError):
    """Raised when a requested provider name is not registered."""
    pass


def get_provider(provider_name: Optional[str] = None) -> ModelProvider:
    """
    Return a ModelProvider instance for the requested provider name.

    Resolves in order:
      1. The explicitly requested provider_name (if not None/empty).
      2. The application-configured MODEL_PROVIDER setting.
      3. The hardcoded DEFAULT_PROVIDER ("gemini").

    Raises UnsupportedProviderError if the resolved name is not in the registry.
    This ensures callers fail loudly on configuration mistakes rather than
    silently falling back to an unintended provider.
    """
    from app.config import settings  # deferred to avoid circular import at package init

    resolved = (
        (provider_name or "").strip().lower()
        or (settings.MODEL_PROVIDER or "").strip().lower()
        or DEFAULT_PROVIDER
    )

    provider_cls = _PROVIDER_REGISTRY.get(resolved)
    if provider_cls is None:
        supported = ", ".join(f"'{k}'" for k in sorted(_PROVIDER_REGISTRY))
        raise UnsupportedProviderError(
            f"Provider '{resolved}' is not supported. Supported providers: {supported}. "
            f"To add a new provider, register it in app/providers/__init__.py."
        )

    return provider_cls()
