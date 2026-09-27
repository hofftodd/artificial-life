"""Shared fixtures for the artificial life test suite."""
import random

import simcore
from simcore import Gene, Organism, World, RadiationField, SpatialGrid, Emitter


def make_rng(seed=1234):
    return random.Random(seed)


def make_gene(**overrides):
    base = dict(
        absorption_spectrum=50,
        absorption=1.0,
        parasitism=0.0,
        predation=0.0,
        movement_ability=1.0,
        radiation_sensing=1.0,
        organism_sensing=1.0,
    )
    base.update(overrides)
    return Gene(**base)


def make_organism(x, y, rng, genes=None, generation=0):
    return Organism(x, y, rng, genes=genes, generation=generation)


def make_world(seed=1234, num_emitters=1, start_population=0, width=600, height=400):
    return World(width=width, height=height, seed=seed,
                 num_emitters=num_emitters, start_population=start_population)


def single_emitter_world(seed=1234, ex=300, ey=200, spectrum=50, width=600, height=400):
    w = make_world(seed=seed, num_emitters=0, width=width, height=height)
    e = Emitter(ex, ey, w.rng, spectrum=spectrum)
    w.emitters.append(e)
    w.grid = SpatialGrid()
    w.field = RadiationField(w.width, w.height, w.emitters, w.organisms, w.grid)
    return w


def build_field(world):
    world.grid.build(world.organisms)
    world.field = RadiationField(world.width, world.height,
                                 world.emitters, world.organisms, world.grid)
    return world.field
