"""
WebSocket client — persistent outbound connection to the control-plane.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable, Optional

import websockets

from .config import AgentConfig

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict], Awaitable[None]]


class WsClient:
    """Manages the persistent agent WebSocket with auto-reconnect."""

    def __init__(self, config: AgentConfig, on_message: MessageHandler) -> None:
        """
        Initialize the client.

        Args:
            config: Agent configuration.
            on_message: Async callback invoked for each server message.
        """
        self._config = config
        self._on_message = on_message
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = asyncio.Event()

    async def send(self, message: dict) -> None:
        """
        Send a JSON message if connected.

        Args:
            message: JSON-serializable message.
        """
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps(message))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to send message: %s", exc)

    async def run_forever(self) -> None:
        """Connect and re-connect forever, dispatching incoming messages."""
        backoff = 1
        while True:
            try:
                async with websockets.connect(self._config.ws_url) as ws:
                    self._ws = ws
                    self._connected.set()
                    backoff = 1
                    logger.info("Connected to control-plane")
                    await self.send(
                        {"type": "hello", "agent_version": "0.1.0", "claude_version": None}
                    )
                    async for raw in ws:
                        try:
                            message = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        await self._on_message(message)
            except Exception as exc:  # noqa: BLE001
                logger.warning("WS disconnected (%s); retrying in %ss", exc, backoff)
            finally:
                self._ws = None
                self._connected.clear()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
