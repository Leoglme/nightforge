"""
Ensure only one NightForge agent worker runs per Windows user session.
"""
from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

_MUTEX_NAME = "Local\\NightForgeAgentSingleton"


def acquire_singleton_or_exit() -> None:
    """
    Exit quietly when another agent instance already holds the mutex.
    """
    if sys.platform != "win32":
        return

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
        if not handle:
            return
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            logger.info("Another NightForge agent is already running — exiting duplicate")
            raise SystemExit(0)
    except OSError as exc:
        logger.debug("Could not create agent singleton mutex: %s", exc)
