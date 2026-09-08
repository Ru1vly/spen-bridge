"""
S Pen Bridge: tablet backend package.
Public surface: `from server.backends import create_tablet_backend, TabletBackendBase`.
"""

from server.backends.base import TabletBackendBase
from server.backends.factory import create_tablet_backend

__all__ = ["TabletBackendBase", "create_tablet_backend"]
