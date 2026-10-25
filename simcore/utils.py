"""
Small shared helpers.
"""
from .constants import RADIATION_DANGER

def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def spectral_match(a, b):
    return 1.0 - abs(a - b) / 99.0


def radiation_effect(intensity, match, efficiency):
    """Net energy gained (or lost, when intensity exceeds RADIATION_DANGER)."""
    return intensity * match * efficiency * (1.0 - (intensity / RADIATION_DANGER) ** 2)
