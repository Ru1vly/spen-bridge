"""Validation shared by stored settings and runtime device settings."""
import math
import re
import ipaddress

BUTTON_ACTIONS = frozenset({
    "right_click", "middle_click", "left_click", "eraser", "undo",
    "stylus", "stylus2", "none",
})
PRESSURE_CURVES = frozenset({"linear", "soft", "firm", "sigmoid", "custom"})


def text(value, name, *, empty=False, limit=256):
    if not isinstance(value, str) or (not empty and not value.strip()) or len(value) > limit:
        raise ValueError(f"{name} must be {'a nonempty' if not empty else 'a'} string of at most {limit} characters")
    if any(ord(c) < 32 for c in value):
        raise ValueError(f"{name} cannot contain control characters")
    return value


def boolean(value, name):
    if type(value) is not bool:
        raise ValueError(f"{name} must be true or false")
    return value


def bind_address(value):
    text(value, "Server bind address", limit=253)
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        labels = value.rstrip(".").split(".")
        if (not any(c.isalpha() for c in value)
                or not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                           for label in labels)):
            raise ValueError("Server bind address must be an IP address or hostname, without a URL scheme or spaces")
        return value


def number(value, name, minimum, maximum, *, integer=False):
    if (type(value) not in ((int,) if integer else (int, float))
            or not minimum <= value <= maximum or not math.isfinite(value)):
        raise ValueError(f"{name} must be {'an integer' if integer else 'a finite number'} between {minimum} and {maximum}")
    return value


def choice(value, name, values):
    if not isinstance(value, str) or value not in values:
        raise ValueError(f"Invalid {name}: expected one of {', '.join(sorted(values))}")
    return value


def dimensions(value, name, *, rectangle=False):
    length = 4 if rectangle else 2
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ValueError(f"{name} must contain {length} integers")
    for i, part in enumerate(value):
        minimum = -100000 if rectangle and i < 2 else 1
        number(part, name, minimum, 100000, integer=True)
    return tuple(value)


def aspect_ratio(value):
    if not isinstance(value, str) or not re.fullmatch(r"[1-9]\d{0,3}:[1-9]\d{0,3}", value):
        raise ValueError("Tablet aspect ratio must be positive width:height, for example 16:10")
    width, height = map(int, value.split(":"))
    return width / height
