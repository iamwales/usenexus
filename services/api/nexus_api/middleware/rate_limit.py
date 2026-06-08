"""
RateLimitMiddleware — per-API-key sliding window rate limiting via Redis.

Uses a Redis sorted set per key:
  Key:   ratelimit:{org_id}
  Score: unix timestamp in ms
  Value: unique request ID

Window: 60 seconds
Limit: fetched from request.state.rate_limit_rpm (set by auth middleware)
Default: 60 rpm (starter plan)
"""

from __future__ import annotations

import time
import uuid

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from nexus_core.logging import get_logger
from starlette.middleware.base import BaseHTTPMiddleware

logger = get_logger(__name__)

_WINDOW_MS = 60_000  # 60 second window
_DEFAULT_RPM = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip if not authenticated yet (auth middleware handles 401)
        if not hasattr(request.state, "org_id"):
            return await call_next(request)

        org_id: str = request.state.org_id
        limit = getattr(request.state, "rate_limit_rpm", _DEFAULT_RPM)
        redis = request.app.state.redis

        now_ms = int(time.time() * 1000)
        window_start = now_ms - _WINDOW_MS
        key = f"ratelimit:{org_id}"

        # Lua script for atomic sliding window check
        lua_script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local window_start = tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        local request_id = ARGV[4]

        -- Remove entries older than the window
        redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

        -- Count current window
        local count = redis.call('ZCARD', key)

        if count >= limit then
            return {count, 0}  -- 0 = rejected
        end

        -- Add this request
        redis.call('ZADD', key, now, request_id)
        redis.call('EXPIRE', key, 120)  -- TTL safety net

        return {count + 1, 1}  -- 1 = allowed
        """

        result = await redis.eval(
            lua_script,
            1,
            key,
            str(now_ms),
            str(window_start),
            str(limit),
            str(uuid.uuid4()),
        )
        current_count, allowed = result

        if not allowed:
            logger.warning("rate_limit.exceeded", org_id=org_id, count=current_count)
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded", "retry_after": 60},
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - current_count))
        return response
