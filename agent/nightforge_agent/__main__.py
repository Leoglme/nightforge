"""
Agent entry point — ``python -m nightforge_agent``.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from nightforge_agent.agent_singleton import acquire_singleton_or_exit
from nightforge_agent.config import load_config
from nightforge_agent.oauth_setup import remove_nightforge_api_key_helper
from nightforge_agent.worker import Worker

logger = logging.getLogger(__name__)


def main() -> None:
    """Load the config (waiting for provisioning if needed) and start the worker loop."""
    # NoDriver / Chrome need a Proactor loop on Windows (subprocess pipes).
    if sys.platform.startswith("win"):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass

    acquire_singleton_or_exit()
    log_dir = Path.home() / ".nightforge"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "agent.log", encoding="utf-8"),
        ],
    )
    config = load_config(wait=True)
    remove_nightforge_api_key_helper()
    worker = Worker(config)

    async def _run() -> None:
        loop = asyncio.get_running_loop()
        stop = asyncio.Event()

        def _request_stop() -> None:
            stop.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _request_stop)
            except (NotImplementedError, RuntimeError, ValueError):
                # Windows / limited environments: fall back to KeyboardInterrupt.
                pass

        run_task = asyncio.create_task(worker.start())
        stop_task = asyncio.create_task(stop.wait())
        try:
            done, pending = await asyncio.wait(
                {run_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if stop_task in done:
                logger.info("Shutdown signal — flushing quotas")
                await worker.flush_quotas()
            if run_task in done and run_task.exception():
                raise run_task.exception()  # type: ignore[misc]
        except asyncio.CancelledError:
            logger.info("Cancelled — flushing quotas")
            await worker.flush_quotas()
            raise
        finally:
            if not run_task.done():
                run_task.cancel()
                try:
                    await run_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — flushing quotas")
        try:
            asyncio.run(worker.flush_quotas())
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
