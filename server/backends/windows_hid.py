"""
Windows virtual tablet backend.

Placeholder for Phase 2 of Windows support: a KMDF virtual HID digitizer
driver (see docs/WINDOWS_DRIVER_PROTOCOL.md once it exists) that this class
will talk to via DeviceIoControl. Until that driver exists, construction
fails loudly and specifically rather than the process crashing on a missing
`evdev` import - see server.backends.factory for why the import of this
module itself must stay cheap and side-effect-free.
"""

import logging
from typing import Optional

from server.backends.base import TabletBackendBase
from server.protocol import PenEvent

logger = logging.getLogger("SPenTablet")


class WindowsHidTablet(TabletBackendBase):
    """Emulates a drawing tablet via a Windows virtual HID driver (not yet implemented)."""

    # Matches the SPENVHID_REPORT HID report descriptor's logical range (see
    # docs/WINDOWS_DRIVER_PROTOCOL.md) - deliberately not Linux's 65535/4095,
    # see the Phase 2 design's "Logical range choices" rationale.
    COORD_MAX = 32767
    PRESSURE_MAX = 32767

    def _setup_device(self):
        raise NotImplementedError(
            "Windows HID backend not yet implemented - see Phase 2 of the "
            "Windows support plan (docs/WINDOWS_DRIVER_PROTOCOL.md)."
        )

    def handle_event(self, ev: PenEvent):
        raise NotImplementedError

    def _release_touch(self):
        pass

    def close(self):
        pass
