"""Distributed Redis Event Bus for real-time task log/command fan-out across API replicas."""

import json
import asyncio
from typing import Optional, Dict, Any, AsyncGenerator
import redis.asyncio as redis
from .settings import settings


def normalize_redis_url(url: Optional[str]) -> str:
    """Sanitizes and normalizes Redis connection strings."""
    if not url:
        return "redis://localhost:6379/0"
    cleaned = url.strip().strip("'\"")
    if "-u " in cleaned:
        cleaned = cleaned.split("-u ")[-1].split(" ")[0].strip("'\"")
    elif " " in cleaned:
        for part in cleaned.split():
            if part.startswith(("redis://", "rediss://")):
                cleaned = part.strip("'\"")
                break
    if not cleaned.startswith(("redis://", "rediss://")):
        return "redis://localhost:6379/0"
    return cleaned


class RedisEventBus:
    """Manages Redis Pub/Sub channels and Streams for task execution flight telemetry."""

    def __init__(self):
        self._redis: Optional[redis.Redis] = None

    def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            clean_url = normalize_redis_url(settings.REDIS_URL)
            self._redis = redis.from_url(
                clean_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0
            )
        return self._redis

    async def publish_event(self, task_id: int, event_type: str, payload_dict: Dict[str, Any], timestamp: Optional[str] = None):
        """
        Publishes a flight event to Redis Pub/Sub channel and appends to the task's Redis Stream.
        """
        event_data = {
            "task_id": task_id,
            "type": event_type,
            "payload": json.dumps(payload_dict) if isinstance(payload_dict, dict) else str(payload_dict),
            "timestamp": timestamp or ""
        }
        json_str = json.dumps(event_data)

        try:
            r = self._get_redis()
            channel_name = f"nimbus:events:task:{task_id}"
            stream_name = f"nimbus:stream:task:{task_id}"

            # 1. Publish to real-time pub/sub channel
            await r.publish(channel_name, json_str)

            # 2. Append to persistent Redis stream (capped to last 500 events)
            await r.xadd(stream_name, {"event": json_str}, maxlen=500, approximate=True)
        except Exception as e:
            print(f"[RedisEventBus] Notice: Failed to publish to Redis ({e})")

    async def subscribe_task(self, task_id: int) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Subscribes to a task's Redis Pub/Sub channel and yields incoming events.
        """
        r = self._get_redis()
        pubsub = r.pubsub()
        channel_name = f"nimbus:events:task:{task_id}"
        await pubsub.subscribe(channel_name)

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        yield data
                    except Exception:
                        pass
        finally:
            await pubsub.unsubscribe(channel_name)
            await pubsub.close()

    async def close(self):
        """Gracefully closes Redis connection pool."""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None


event_bus = RedisEventBus()
