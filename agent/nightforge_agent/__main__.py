"""
Agent entry point — ``python -m nightforge_agent``.
"""
from __future__ import annotations

import asyncio
import logging

from .config import load_config
from .worker import Worker


def main() -> None:
    """Load the config (waiting for provisioning if needed) and start the worker loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    config = load_config(wait=True)
    worker = Worker(config)
    try:
        asyncio.run(worker.start())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
