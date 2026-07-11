"""
Agent entry point — ``python -m nightforge_agent``.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from nightforge_agent.config import load_config
from nightforge_agent.oauth_setup import ensure_api_key_helper_configured
from nightforge_agent.worker import Worker


def main() -> None:
    """Load the config (waiting for provisioning if needed) and start the worker loop."""
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
    ensure_api_key_helper_configured()
    worker = Worker(config)
    try:
        asyncio.run(worker.start())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
