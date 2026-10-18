"""Security utilities for log redaction and sensitive data masking."""

import logging
import re
from typing import Optional
from app.config import settings

# Regex patterns for sensitive credentials
SENSITIVE_PATTERNS = [
    # Google AI / Gemini API Keys (typically AIzaSy...)
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    # GitHub classic personal access tokens (ghp_...)
    re.compile(r"ghp_[0-9A-Za-z]{36}"),
    # GitHub fine-grained personal access tokens (github_pat_...)
    re.compile(r"github_pat_[0-9A-Za-z_]{20,}"),
    # Authorization header Bearer tokens
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-_.~+/]+=*"),
    # URL query parameter keys (e.g. key=... or token=...)
    re.compile(r"(?i)(key|token|api_key|secret)=([A-Za-z0-9\-_.~+/]+)"),
]


def redact_sensitive_string(text: str) -> str:
    """Mask any discovered secrets or tokens in an arbitrary string."""
    if not isinstance(text, str) or not text:
        return text

    redacted = text

    # Redact exact configured values if set
    if settings.GEMINI_API_KEY and len(settings.GEMINI_API_KEY) > 4:
        redacted = redacted.replace(settings.GEMINI_API_KEY, "[REDACTED_GEMINI_KEY]")
    if settings.GITHUB_TOKEN and len(settings.GITHUB_TOKEN) > 4:
        redacted = redacted.replace(settings.GITHUB_TOKEN, "[REDACTED_GITHUB_TOKEN]")

    # Redact generic patterns
    redacted = re.sub(r"AIza[0-9A-Za-z\-_]{35}", "[REDACTED_API_KEY]", redacted)
    redacted = re.sub(r"ghp_[0-9A-Za-z]{36}", "[REDACTED_GITHUB_TOKEN]", redacted)
    redacted = re.sub(r"github_pat_[0-9A-Za-z_]{20,}", "[REDACTED_GITHUB_PAT]", redacted)
    redacted = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9\-_.~+/]+=*", r"\1[REDACTED_TOKEN]", redacted)
    redacted = re.sub(r"(?i)(key|token|api_key|secret)=([A-Za-z0-9\-_.~+/]+)", r"\1=[REDACTED]", redacted)

    return redacted


class SecretRedactionFilter(logging.Filter):
    """Logging filter that scrubs sensitive credentials from all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_sensitive_string(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact_sensitive_string(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_sensitive_string(a) if isinstance(a, str) else a
                    for a in record.args
                )
        return True


def setup_secure_logging():
    """Install the SecretRedactionFilter on the root logger and framework loggers."""
    redaction_filter = SecretRedactionFilter()

    # Root logger
    root_logger = logging.getLogger()
    if redaction_filter not in root_logger.filters:
        root_logger.addFilter(redaction_filter)

    # Uvicorn, FastAPI, and app loggers
    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi", "app"):
        target_logger = logging.getLogger(logger_name)
        if redaction_filter not in target_logger.filters:
            target_logger.addFilter(redaction_filter)
