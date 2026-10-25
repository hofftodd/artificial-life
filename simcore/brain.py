"""
The evolved movement controller (Rules.movement == "brain"): the
per-strategy seed weights and the hunger-modulated weight lookups.
"""
import math

from .constants import BRAIN_CLAMP, BRAIN_INPUTS, BRAIN_SEED_NOISE, BRAIN_SEEDS
from .utils import clamp

def _brain_from_seed(strategy, rng=None):
    seed = BRAIN_SEEDS[strategy]
    jitter = (lambda: rng.gauss(0, BRAIN_SEED_NOISE)) if rng is not None else (lambda: 0.0)
    w = []
    for name in BRAIN_INPUTS:
        base, hunger = seed.get(name, (0.0, 0.0))
        w.append(base + jitter())
        w.append(hunger + jitter())
    w.extend(t + jitter() for t in seed["throttle"])
    return tuple(clamp(x, -BRAIN_CLAMP, BRAIN_CLAMP) for x in w)


def seed_brain(strategy, rng):
    """A founder's controller: the strategy's seed weights plus noise."""
    return _brain_from_seed(strategy, rng)


_DEFAULT_BRAINS = {}


def default_brain(strategy):
    """The noise-free seed, used when a genome has no controller."""
    if strategy not in _DEFAULT_BRAINS:
        _DEFAULT_BRAINS[strategy] = _brain_from_seed(strategy)
    return _DEFAULT_BRAINS[strategy]


def brain_weight(brain, name, hunger):
    """Effective steering weight of an input at a given hunger (0..1)."""
    i = 2 * BRAIN_INPUTS.index(name)
    return brain[i] + brain[i + 1] * hunger


def brain_throttle(brain, hunger, light):
    t = brain[-3] + brain[-2] * hunger + brain[-1] * light
    return 1.0 / (1.0 + math.exp(-t))
