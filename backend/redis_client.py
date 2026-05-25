from redis import asyncio as aioredis

from config import get_settings

_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis | None:
    global _client
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return None
    if _client is None:
        _client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def ping_redis() -> bool:
    client = await get_redis()
    if client is None:
        return False
    try:
        return await client.ping()
    except Exception:
        return False
