"""
User role enumeration for authorization.
"""
from enum import Enum


class UserRole(str, Enum):
    """
    User role enumeration.

    Attributes:
        USER: Standard user role.
        ADMIN: Administrator role.
    """

    USER = "USER"
    ADMIN = "ADMIN"
