"""Capability contract used by backends and the profile editor."""
from server.validation import BUTTON_ACTIONS


def available_actions(platform, mode):
    actions = set(BUTTON_ACTIONS)
    if platform == "win32":
        actions.discard("stylus2")  # Installed descriptor has one barrel switch.
    elif mode == "pointer":
        actions -= {"eraser", "stylus", "stylus2"}
    return frozenset(actions)


def validate_actions(platform, mode, primary, secondary):
    allowed = available_actions(platform, mode)
    for action in (primary, secondary):
        if action not in allowed:
            raise ValueError(f"Button action '{action}' is unavailable in {mode} mode on {platform}")
