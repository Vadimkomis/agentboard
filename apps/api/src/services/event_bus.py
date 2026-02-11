import asyncio
import json
from typing import AsyncGenerator

import redis.asyncio as redis

from src.config import settings

_redis: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def publish_event(channel: str, event_type: str, data: dict) -> None:
    r = await get_redis()
    message = json.dumps({"type": event_type, "data": data})
    await r.publish(channel, message)


async def subscribe_events(channel: str) -> AsyncGenerator[str, None]:
    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                yield message["data"]
            else:
                # Send keepalive
                yield ""
                await asyncio.sleep(1)
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
