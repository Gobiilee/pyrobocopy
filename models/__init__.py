# models/__init__.py

"""
The Models package contains all core business logic and data structures.
It is entirely independent of the UI layer.
"""

from .copier import RoboCopier, CopyResult

# The __all__ variable restricts what gets imported if someone uses `from models import *`
__all__ = [
    "RoboCopier",
    "CopyResult"
]