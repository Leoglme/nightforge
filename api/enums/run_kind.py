"""
Run kind — night (Composer) vs quick (on-the-fly from the queue).
"""
from enum import Enum


class RunKind(str, Enum):
    """How the run was created / should be displayed."""

    NIGHT = "night"
    QUICK = "quick"
