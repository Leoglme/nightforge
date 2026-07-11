"""
Queue item (prompt) status.
"""
from enum import Enum


class QueueItemStatus(str, Enum):
    """
    Status of a single prompt in a project's queue.

    Attributes:
        PENDING: Not yet processed.
        RUNNING: Currently being executed by Claude.
        DONE: Completed successfully.
        FAILED: Failed after retries.
        SKIPPED: Skipped (e.g. stopped before execution).
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
