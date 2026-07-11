"""
Machine (agent) runtime status.
"""
from enum import Enum


class MachineStatus(str, Enum):
    """
    Agent state as seen by the control-plane.

    Attributes:
        OFFLINE: No active agent connection.
        IDLE: Connected, not working.
        WORKING: Currently running a queue item.
        WAITING_QUOTA: Blocked waiting for a Claude quota reset.
        ERROR: Agent reported an error.
    """

    OFFLINE = "OFFLINE"
    IDLE = "IDLE"
    WORKING = "WORKING"
    WAITING_QUOTA = "WAITING_QUOTA"
    ERROR = "ERROR"
