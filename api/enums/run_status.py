"""
Night run lifecycle status.
"""
from enum import Enum


class RunStatus(str, Enum):
    """
    Lifecycle of a scheduled night run.

    Attributes:
        SCHEDULED: Created, waiting for its start time / an available agent.
        RUNNING: Actively draining the queue.
        WAITING_QUOTA: Paused until the Claude quota resets.
        COMPLETED: Finished (queue drained or quota budget reached).
        STOPPED: Manually stopped (kill switch).
        FAILED: Aborted after the error budget was exhausted.
    """

    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    WAITING_QUOTA = "WAITING_QUOTA"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
