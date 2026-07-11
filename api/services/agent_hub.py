"""
Agent hub — in-memory registry of connected agent WebSockets.

Agents connect out to the control-plane and stay connected. The hub lets routes push
commands to a specific machine and lets the WebSocket route broadcast run events to the
dashboard clients. This is intentionally simple (single-process); scale later if needed.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class AgentHub:
    """Tracks live agent and dashboard WebSocket connections."""

    def __init__(self) -> None:
        """Initialize empty connection maps."""
        self._agents: Dict[int, WebSocket] = {}
        self._dashboards: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._pending: Dict[str, asyncio.Future] = {}

    async def register_agent(self, machine_id: int, ws: WebSocket) -> None:
        """
        Register a connected agent for a machine.

        Args:
            machine_id: The machine id.
            ws: The agent WebSocket.
        """
        async with self._lock:
            self._agents[machine_id] = ws
        logger.info("Agent connected: machine=%s", machine_id)

    async def unregister_agent(self, machine_id: int) -> None:
        """
        Remove an agent connection.

        Args:
            machine_id: The machine id.
        """
        async with self._lock:
            self._agents.pop(machine_id, None)
        logger.info("Agent disconnected: machine=%s", machine_id)

    def is_online(self, machine_id: int) -> bool:
        """
        Whether an agent is currently connected for a machine.

        Args:
            machine_id: The machine id.

        Returns:
            True if connected.
        """
        return machine_id in self._agents

    async def send_to_agent(self, machine_id: int, message: dict) -> bool:
        """
        Send a JSON command to a specific agent.

        Args:
            machine_id: Target machine id.
            message: JSON-serializable command.

        Returns:
            True if the agent was connected and the message was sent.
        """
        ws = self._agents.get(machine_id)
        if ws is None:
            return False
        await ws.send_json(message)
        return True

    async def request_agent(
        self, machine_id: int, message: dict, timeout: float = 15.0
    ) -> Optional[dict]:
        """
        Send a command to an agent and wait for its correlated response.

        Args:
            machine_id: Target machine id.
            message: JSON command (``request_id`` is added automatically).
            timeout: Seconds to wait before giving up.

        Returns:
            The agent response payload, or None on timeout / offline.
        """
        if not self.is_online(machine_id):
            return None

        request_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future
        try:
            sent = await self.send_to_agent(machine_id, {**message, "request_id": request_id})
            if not sent:
                return None
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            logger.info("Agent request timed out machine=%s type=%s", machine_id, message.get("type"))
            return None
        finally:
            self._pending.pop(request_id, None)

    def resolve_request(self, request_id: Optional[str], payload: dict) -> bool:
        """
        Complete a pending agent request.

        Args:
            request_id: Correlation id from the agent response.
            payload: Response body.

        Returns:
            True if a waiter was resolved.
        """
        if not request_id:
            return False
        future = self._pending.get(request_id)
        if future is None or future.done():
            return False
        future.set_result(payload)
        return True

    async def register_dashboard(self, ws: WebSocket) -> None:
        """
        Register a dashboard client for live updates.

        Args:
            ws: The dashboard WebSocket.
        """
        async with self._lock:
            self._dashboards.add(ws)

    async def unregister_dashboard(self, ws: WebSocket) -> None:
        """
        Remove a dashboard client.

        Args:
            ws: The dashboard WebSocket.
        """
        async with self._lock:
            self._dashboards.discard(ws)

    async def broadcast_dashboard(self, message: dict) -> None:
        """
        Broadcast a message to all dashboard clients.

        Args:
            message: JSON-serializable message.
        """
        dead: Set[WebSocket] = set()
        for ws in list(self._dashboards):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001
                dead.add(ws)
        for ws in dead:
            await self.unregister_dashboard(ws)


# Global singleton hub
agent_hub = AgentHub()
