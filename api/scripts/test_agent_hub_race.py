"""Regression: stale agent disconnect must not wipe a newer live socket."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from services.agent_hub import AgentHub


class AgentHubRaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_unregister_keeps_newer_agent_online(self) -> None:
        hub = AgentHub()
        old_ws = MagicMock()
        old_ws.close = AsyncMock()
        new_ws = MagicMock()
        new_ws.close = AsyncMock()

        await hub.register_agent(9, old_ws)
        self.assertTrue(hub.is_online(9))

        await hub.register_agent(9, new_ws)
        self.assertTrue(hub.is_online(9))
        old_ws.close.assert_awaited()

        cleared = await hub.unregister_agent(9, old_ws)
        self.assertFalse(cleared)
        self.assertTrue(hub.is_online(9))

        cleared = await hub.unregister_agent(9, new_ws)
        self.assertTrue(cleared)
        self.assertFalse(hub.is_online(9))

    async def test_disconnect_agent_closes_socket(self) -> None:
        hub = AgentHub()
        ws = MagicMock()
        ws.close = AsyncMock()
        await hub.register_agent(3, ws)
        await hub.disconnect_agent(3)
        self.assertFalse(hub.is_online(3))
        ws.close.assert_awaited()


if __name__ == "__main__":
    unittest.main()
