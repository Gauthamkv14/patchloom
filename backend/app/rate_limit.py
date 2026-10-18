"""In-memory sliding-window rate limiter for FastAPI endpoints."""

import re
import threading
import time
from collections import defaultdict
from typing import Callable, Optional
from fastapi import HTTPException, Request, status
from app.config import settings


def parse_rate_limit(rule: str) -> tuple[int, int]:
    """
    Parse a rate limit rule into (max_requests, window_seconds).
    Supported formats:
      - "10/10minutes" -> (10, 600)
      - "60/minute" -> (60, 60)
      - "5/second" -> (5, 1)
      - "100/hour" -> (100, 3600)
      - "10/600s" -> (10, 600)
    """
    rule = rule.strip().lower()
    match = re.match(r"^(\d+)\s*/\s*(\d*)\s*([a-z]+)$", rule)
    if not match:
        raise ValueError(f"Invalid rate limit format: '{rule}'. Expected e.g. '10/10minutes' or '60/minute'.")

    count = int(match.group(1))
    multiplier = int(match.group(2)) if match.group(2) else 1
    unit = match.group(3)

    if unit in ("s", "sec", "second", "seconds"):
        window = multiplier * 1
    elif unit in ("m", "min", "minute", "minutes"):
        window = multiplier * 60
    elif unit in ("h", "hr", "hour", "hours"):
        window = multiplier * 3600
    elif unit in ("d", "day", "days"):
        window = multiplier * 86400
    else:
        raise ValueError(f"Unknown time unit '{unit}' in rate limit rule '{rule}'")

    return count, max(1, window)


def is_ip_trusted(immediate_ip: str, trusted_list: list[str]) -> bool:
    """Check if immediate peer IP matches any trusted proxy IP or CIDR network."""
    import ipaddress
    for item in trusted_list:
        if item == immediate_ip:
            return True
        if "/" in item:
            try:
                if ipaddress.ip_address(immediate_ip) in ipaddress.ip_network(item, strict=False):
                    return True
            except ValueError:
                continue
    return False


def get_client_identifier(request: Request, trusted_proxies: Optional[list[str]] = None) -> str:
    """
    Safely determine client identity without trusting spoofed proxy headers.
    
    Security Policy:
    - Never trust forwarded headers ('X-Real-IP' or 'X-Forwarded-For') unless the
      immediate peer IP (request.client.host) matches an IP or CIDR block explicitly
      listed in settings.TRUSTED_PROXIES.
    - If running without trusted proxies configured or if peer is untrusted, use request.client.host.
    - When direct peer is a trusted proxy, prefer 'X-Real-IP' (sanitized edge IP)
      or the canonical client IP from 'X-Forwarded-For'.
    """
    trusted = trusted_proxies if trusted_proxies is not None else settings.TRUSTED_PROXIES
    immediate_ip = request.client.host if request.client else "127.0.0.1"

    # Only inspect forwarded headers if immediate peer is in trusted proxies
    if trusted and is_ip_trusted(immediate_ip, trusted):
        real_ip = request.headers.get("x-real-ip")
        if real_ip and real_ip.strip():
            return real_ip.strip()
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            parts = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
            if parts:
                return parts[0]

    return immediate_ip


class InMemoryRateLimiter:
    """Thread-safe, sliding-window in-memory rate limiter."""

    def __init__(self):
        self._lock = threading.Lock()
        self._records: dict[str, list[float]] = defaultdict(list)
        self.enabled: bool = True

    def check(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int]:
        """
        Check if a request is allowed under the sliding window.
        Returns (is_allowed, retry_after_seconds).
        """
        if not self.enabled or not settings.ENABLE_RATE_LIMIT:
            return True, 0

        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            # Filter timestamps within current sliding window
            valid_timestamps = [ts for ts in self._records[key] if ts > window_start]

            if len(valid_timestamps) >= max_requests:
                # Earliest timestamp in current window defines when next token becomes available
                oldest_timestamp = valid_timestamps[0]
                retry_after = max(1, int(oldest_timestamp + window_seconds - now) + 1)
                self._records[key] = valid_timestamps
                return False, retry_after

            valid_timestamps.append(now)
            self._records[key] = valid_timestamps
            return True, 0

    def reset(self):
        """Reset all rate limiter records (used in tests)."""
        with self._lock:
            self._records.clear()


limiter = InMemoryRateLimiter()


def rate_limit(endpoint_name: str, limit_rule_getter: Callable[[], str]):
    """FastAPI dependency factory enforcing rate limits on an endpoint."""

    async def dependency(request: Request):
        if not limiter.enabled or not settings.ENABLE_RATE_LIMIT:
            return

        rule = limit_rule_getter()
        try:
            max_reqs, window_secs = parse_rate_limit(rule)
        except Exception:
            # Fallback to conservative default if misconfigured
            max_reqs, window_secs = 10, 600

        client_id = get_client_identifier(request)
        key = f"{endpoint_name}:{client_id}"

        allowed, retry_after = limiter.check(key, max_reqs, window_secs)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {endpoint_name}. Please try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency
