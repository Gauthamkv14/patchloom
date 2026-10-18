from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Configuration settings for PatchLoom."""

    model_config = SettingsConfigDict(
        env_file=(str(ENV_FILE), ".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = Field(default="development")
    DEMO_MODE: bool = Field(default=False)
    MODEL_PROVIDER: str = Field(default="gemini")
    GEMINI_API_KEY: Optional[str] = Field(default=None)
    GEMMA_MODEL: str = Field(default="gemma-4-31b-it")
    GEMMA_FALLBACK_MODEL: str = Field(default="gemma-4-26b-a4b-it")
    GITHUB_TOKEN: Optional[str] = Field(default=None)
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434")
    OLLAMA_MODEL: str = Field(default="gemma4:e4b")
    REQUEST_TIMEOUT_SECONDS: int = Field(default=20)
    MODEL_TIMEOUT_SECONDS: int = Field(default=60)
    MAX_PROMPT_CHARS: int = Field(default=60000)
    MAX_CANDIDATES: int = Field(default=12)
    MAX_CONCURRENT_MODEL_REQUESTS: int = Field(default=2)
    MAX_REQUEST_BODY_BYTES: int = Field(default=32768)
    ANALYZE_RATE_LIMIT: str = Field(default="10/10minutes")
    PLAN_RATE_LIMIT: str = Field(default="10/10minutes")
    HEALTH_RATE_LIMIT: str = Field(default="60/minute")
    TRUSTED_PROXIES: list[str] = Field(default_factory=list)
    ENABLE_RATE_LIMIT: bool = Field(default=True)

    @property
    def has_gemini_key(self) -> bool:
        """Check if GEMINI_API_KEY is present without leaking value."""
        return bool(self.GEMINI_API_KEY and self.GEMINI_API_KEY.strip())

    @property
    def has_github_token(self) -> bool:
        """Check if GITHUB_TOKEN is present without leaking value."""
        return bool(self.GITHUB_TOKEN and self.GITHUB_TOKEN.strip())


settings = Settings()
