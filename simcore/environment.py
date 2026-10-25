"""
World furniture: emitters, rocks and carcasses, plus the rock
geometry helpers (push_out, in_cover).
"""
import math

from .constants import EMITTER_MARGIN, EMITTER_RANGE, RADIATION_ENERGY
from .utils import clamp

class Carcass:
    """Energy left where an organism died, for scavengers."""

    def __init__(self, x, y, energy):
        self.x = float(x)
        self.y = float(y)
        self.energy = energy


class Rock:
    """A solid circle: casts a shadow, can't be entered, gives cover."""

    def __init__(self, x, y, r):
        self.x = float(x)
        self.y = float(y)
        self.r = float(r)


def push_out(x, y, rocks, margin=0.0):
    """Move a point that ended up inside a rock to just outside its edge."""
    for rock in rocks:
        dx, dy = x - rock.x, y - rock.y
        d = math.hypot(dx, dy)
        limit = rock.r + margin
        if d < limit:
            if d < 1e-9:
                dx, dy, d = 1.0, 0.0, 1.0
            x = rock.x + dx / d * limit
            y = rock.y + dy / d * limit
    return x, y


def in_cover(x, y, rocks, cover_range):
    for rock in rocks:
        if math.hypot(x - rock.x, y - rock.y) - rock.r <= cover_range:
            return True
    return False


class Emitter:
    def __init__(self, x, y, rng, spectrum=None):
        self.x = float(x)
        self.y = float(y)
        self.spectrum = spectrum if spectrum is not None else rng.randint(1, 100)
        self.phase = rng.uniform(0, math.pi * 2)
        self.strength = 1.0      # seasonal output multiplier (see advance)

    def radiation_at(self, x, y, tail_strength=0.0, tail_range=0.0):
        d = math.hypot(x - self.x, y - self.y)
        if not tail_strength:
            if d < EMITTER_RANGE:
                return RADIATION_ENERGY * (1.0 - d / EMITTER_RANGE) * self.strength
            return 0.0
        # a dim, wide second cone on top of the core
        v = RADIATION_ENERGY * (1.0 - d / EMITTER_RANGE) if d < EMITTER_RANGE else 0.0
        if d < tail_range:
            v += tail_strength * (1.0 - d / tail_range)
        return v * self.strength

    def apply_season(self, rules, tick):
        if rules.pulse_period and rules.pulse_depth:
            season = 0.5 - 0.5 * math.cos(2 * math.pi * tick / rules.pulse_period + self.phase)
            self.strength = 1.0 - rules.pulse_depth * season

    def advance(self, world):
        """Apply one tick of the world's emitter dynamics (pulse, drift)."""
        rules = world.rules
        self.apply_season(rules, world.tick)
        if rules.spectrum_drift:
            self.spectrum = clamp(self.spectrum + world.rng.gauss(0, rules.spectrum_drift),
                                  1, 100)
        if rules.emitter_drift:
            x = self.x + world.rng.gauss(0, rules.emitter_drift)
            y = self.y + world.rng.gauss(0, rules.emitter_drift)
            x, y = push_out(x, y, world.rocks, margin=5)
            self.x = clamp(x, EMITTER_MARGIN, world.width - EMITTER_MARGIN)
            self.y = clamp(y, EMITTER_MARGIN, world.height - EMITTER_MARGIN)
