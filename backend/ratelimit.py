import time
import uuid

from fastapi import HTTPException, Request, status

from config import get_settings
from redis_client import get_redis


class RateLimiter:
    """Redis sliding-window rate limiter using a sorted set per key."""

    def __init__(self, key: str, limit: int, window_seconds: int):
        self.key = f"rl:{key}"
        self.limit = limit
        self.window_seconds = window_seconds

    async def check(self) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return

        redis = await get_redis()
        if redis is None:
            return

        now = time.time()
        window_start = now - self.window_seconds
        member = f"{now}:{uuid.uuid4().hex}"

        pipe = redis.pipeline()
        pipe.zremrangebyscore(self.key, 0, window_start)
        pipe.zadd(self.key, {member: now})
        pipe.zcard(self.key)
        pipe.expire(self.key, self.window_seconds + 1)
        _, _, count, _ = await pipe.execute()

        if count > self.limit:
            retry_after = max(1, int(self.window_seconds))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )


async def rate_limit_auth(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    settings = get_settings()
    await RateLimiter(
        f"auth:{client_ip}",
        settings.auth_requests_per_minute,
        60,
    ).check()


async def rate_limit_chat_user(user_id: int) -> None:
    settings = get_settings()
    await RateLimiter(
        f"chat:user:{user_id}",
        settings.chat_requests_per_minute,
        60,
    ).check()


async def rate_limit_history_user(user_id: int) -> None:
    settings = get_settings()
    await RateLimiter(
        f"history:user:{user_id}",
        settings.chat_history_requests_per_minute,
        60,
    ).check()
