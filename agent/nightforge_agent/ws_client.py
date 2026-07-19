"""
WebSocket client — persistent outbound connection to the control-plane.
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
from typing import Any, Awaitable, Callable, Optional

import certifi
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatus

from .config import AgentConfig

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict], Awaitable[None]]
ConfigProvider = Callable[[], Optional[AgentConfig]]


def _ssl_context_for(url: str) -> ssl.SSLContext | bool | None:
    """
    Build an SSL context for WSS connections (required for PyInstaller on Windows).

    Args:
        url: Target WebSocket URL.

    Returns:
        SSL settings for ``websockets.connect``.
    """
    if not url.startswith("wss://"):
        return None
    return ssl.create_default_context(cafile=certifi.where())


class WsClient:
    """Manages the persistent agent WebSocket with auto-reconnect."""

    def __init__(self, config_provider: ConfigProvider, on_message: MessageHandler) -> None:
        """
        Initialize the client.

        Args:
            config_provider: Returns fresh config before each connect (reloads agent.json).
            on_message: Async callback invoked for each server message.
        """
        self._config_provider = config_provider
        self._on_message = on_message
        # websockets≥14: ClientConnection; keep Any for legacy/new API compatibility.
        self._ws: Optional[Any] = None
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
            config = self._config_provider()
            if config is None:
                logger.info("No agent token yet — waiting for provisioning")
                await asyncio.sleep(5)
                continue

            try:
                logger.info("Connecting to control-plane at %s", config.api_base)
                async with websockets.connect(
                    config.ws_url,
                    ssl=_ssl_context_for(config.ws_url),
                ) as ws:
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
            except ConnectionClosed as exc:
                if exc.code == 4401:
                    logger.warning("Authentication rejected (4401) — reloading token from agent.json")
                    backoff = 1
                else:
                    logger.warning("WS closed (%s); retrying in %ss", exc, backoff)
            except InvalidStatus as exc:
                logger.warning(
                    "WebSocket rejected (HTTP %s) — token invalide ou API inaccessible; "
                    "vérifie agent.json et supprime NF_AGENT_TOKEN des variables Windows",
                    exc.response.status_code,
                )
                backoff = min(backoff * 2, 30)
            except Exception as exc:  # noqa: BLE001
                logger.warning("WS disconnected (%s); retrying in %ss", exc, backoff)
            finally:
                self._ws = None
                self._connected.clear()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
