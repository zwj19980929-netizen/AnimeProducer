"""WebSocket manager for real-time job status updates."""

import asyncio
import json
import logging
from typing import Dict, Set
from contextlib import asynccontextmanager

from fastapi import WebSocket, WebSocketDisconnect
import redis.asyncio as aioredis

from config import settings
from core.metrics import record_websocket_connect, record_websocket_disconnect, record_websocket_message

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and Redis pub/sub for real-time updates."""

    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {}  # project_id -> websockets
        self._job_connections: Dict[str, Set[WebSocket]] = {}  # job_id -> websockets
        self._redis: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None
        self._listener_task: asyncio.Task | None = None

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            try:
                self._redis = await asyncio.wait_for(
                    aioredis.from_url(
                        settings.REDIS_URL,
                        encoding="utf-8",
                        decode_responses=True,
                        socket_connect_timeout=5,
                        socket_timeout=None  # No timeout for pub/sub listening
                    ),
                    timeout=5.0
                )
                # Test connection
                await self._redis.ping()
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
                self._redis = None
                raise
        return self._redis

    async def start_listener(self):
        """Start the Redis pub/sub listener."""
        if self._listener_task is not None:
            return

        try:
            redis = await self._get_redis()
            self._pubsub = redis.pubsub()
            await self._pubsub.psubscribe("job:*", "project:*")
            self._listener_task = asyncio.create_task(self._listen_redis())
            logger.info("WebSocket Redis listener started")
        except Exception as e:
            logger.warning(f"WebSocket Redis listener failed to start (Redis unavailable): {e}")
            logger.info("WebSocket will work without Redis pub/sub - falling back to polling")

    async def stop_listener(self):
        """Stop the Redis pub/sub listener."""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()
            self._pubsub = None

        if self._redis:
            await self._redis.close()
            self._redis = None

        logger.info("WebSocket Redis listener stopped")

    async def _listen_redis(self):
        """Listen for Redis pub/sub messages and broadcast to WebSocket clients."""
        try:
            async for message in self._pubsub.listen():
                if message["type"] == "pmessage":
                    channel = message["channel"]
                    data = message["data"]

                    try:
                        payload = json.loads(data) if isinstance(data, str) else data
                    except json.JSONDecodeError:
                        payload = {"raw": data}

                    # Parse channel: job:{job_id}:status or project:{project_id}:status
                    parts = channel.split(":")
                    if len(parts) >= 2:
                        entity_type = parts[0]
                        entity_id = parts[1]

                        if entity_type == "job":
                            await self._broadcast_to_job(entity_id, payload)
                            # Also broadcast to project if project_id is in payload
                            if "project_id" in payload:
                                await self._broadcast_to_project(payload["project_id"], payload)
                        elif entity_type == "project":
                            await self._broadcast_to_project(entity_id, payload)

        except asyncio.CancelledError:
            logger.info("Redis listener cancelled")
        except Exception as e:
            logger.error(f"Redis listener error: {e}")
            # Try to reconnect after error
            self._listener_task = None
            await asyncio.sleep(5)
            try:
                await self.start_listener()
            except Exception:
                logger.warning("Failed to restart Redis listener")

    async def connect_project(self, websocket: WebSocket, project_id: str):
        """Connect a WebSocket to receive project updates."""
        await websocket.accept()
        if project_id not in self._connections:
            self._connections[project_id] = set()
        self._connections[project_id].add(websocket)
        record_websocket_connect("project")
        logger.debug(f"WebSocket connected for project: {project_id}")

    async def connect_job(self, websocket: WebSocket, job_id: str):
        """Connect a WebSocket to receive job updates."""
        await websocket.accept()
        if job_id not in self._job_connections:
            self._job_connections[job_id] = set()
        self._job_connections[job_id].add(websocket)
        record_websocket_connect("job")
        logger.debug(f"WebSocket connected for job: {job_id}")

    def disconnect_project(self, websocket: WebSocket, project_id: str):
        """Disconnect a WebSocket from project updates."""
        if project_id in self._connections:
            self._connections[project_id].discard(websocket)
            if not self._connections[project_id]:
                del self._connections[project_id]
        record_websocket_disconnect("project")
        logger.debug(f"WebSocket disconnected for project: {project_id}")

    def disconnect_job(self, websocket: WebSocket, job_id: str):
        """Disconnect a WebSocket from job updates."""
        if job_id in self._job_connections:
            self._job_connections[job_id].discard(websocket)
            if not self._job_connections[job_id]:
                del self._job_connections[job_id]
        record_websocket_disconnect("job")
        logger.debug(f"WebSocket disconnected for job: {job_id}")

    async def _broadcast_to_project(self, project_id: str, message: dict):
        """Broadcast message to all WebSocket clients subscribed to a project."""
        if project_id not in self._connections:
            return

        dead_connections = set()
        for websocket in self._connections[project_id]:
            try:
                await websocket.send_json(message)
            except Exception:
                dead_connections.add(websocket)

        # Clean up dead connections
        for ws in dead_connections:
            self._connections[project_id].discard(ws)

    async def _broadcast_to_job(self, job_id: str, message: dict):
        """Broadcast message to all WebSocket clients subscribed to a job."""
        if job_id not in self._job_connections:
            return

        dead_connections = set()
        for websocket in self._job_connections[job_id]:
            try:
                await websocket.send_json(message)
            except Exception:
                dead_connections.add(websocket)

        # Clean up dead connections
        for ws in dead_connections:
            self._job_connections[job_id].discard(ws)

    async def send_personal_message(self, websocket: WebSocket, message: dict):
        """Send a message to a specific WebSocket client."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")


# Global connection manager instance
manager = ConnectionManager()


async def publish_job_update(job_id: str, project_id: str, data: dict):
    """Publish a job update to Redis for broadcasting."""
    try:
        redis = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
        payload = {
            "type": "job_update",
            "job_id": job_id,
            "project_id": project_id,
            **data
        }
        await redis.publish(f"job:{job_id}:status", json.dumps(payload))
        await redis.close()
    except Exception as e:
        logger.error(f"Failed to publish job update: {e}")


async def publish_project_update(project_id: str, data: dict):
    """Publish a project update to Redis for broadcasting."""
    try:
        redis = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
        payload = {
            "type": "project_update",
            "project_id": project_id,
            **data
        }
        await redis.publish(f"project:{project_id}:status", json.dumps(payload))
        await redis.close()
    except Exception as e:
        logger.error(f"Failed to publish project update: {e}")


def publish_job_update_sync(job_id: str, project_id: str, data: dict):
    """Synchronous version of publish_job_update for use in Celery tasks."""
    import redis
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        payload = {
            "type": "job_update",
            "job_id": job_id,
            "project_id": project_id,
            **data
        }
        r.publish(f"job:{job_id}:status", json.dumps(payload))
        r.close()
    except Exception as e:
        logger.error(f"Failed to publish job update (sync): {e}")


def publish_shot_render_update_sync(render_id: str, job_id: str, project_id: str, data: dict):
    """Publish shot render update synchronously."""
    import redis
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        payload = {
            "type": "shot_render_update",
            "render_id": render_id,
            "job_id": job_id,
            "project_id": project_id,
            **data
        }
        r.publish(f"job:{job_id}:status", json.dumps(payload))
        r.close()
    except Exception as e:
        logger.error(f"Failed to publish shot render update (sync): {e}")
