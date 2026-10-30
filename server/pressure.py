"""One pressure transfer function for device output and its GUI preview."""
import math


def pressure_output(raw, curve="linear", gamma=1.0, minimum=0.0, maximum=1.0):
    if not math.isfinite(raw):
        raise ValueError("Pressure must be finite")
    if raw <= minimum:
        return 0.0
    norm = min(1.0, (raw - minimum) / max(.001, maximum - minimum))
    if curve == "soft":
        return norm ** .65
    if curve == "firm":
        return norm ** 1.6
    if curve == "sigmoid":
        return norm * norm * (3 - 2 * norm)
    if curve == "custom":
        return norm ** gamma
    return norm
